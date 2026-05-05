"""
Главный оркестратор CV-пайплайна (V2 — wall-graph-first).

ПОРЯДОК (новая архитектура):
  1. preprocess(image) → PreprocessedPlan
  2. extract_wall_mask → STRUCTURAL wall mask (без текста, иконок, дуг)
  3. detect_walls (Hough на STRUCTURAL mask)
  4. build_wall_graph (snap, intersect, split, classify outer/inner)
  5. polygonize_rooms (close door gaps → flood fill → contours)
  6. find_openings (gaps в найденных стенах — НЕ HoughCircles по всему изобр.)
  7. classify_openings (door/window только на проёмах)
  8. OCR площадей → assign_room_labels
  9. estimate_scale (px/m)
  10. filter_openings (FP filter: дедуп, sanity rules)
  11. confidence gating
  12. сборка ApartmentGeometry

Этот pipeline решает 4 проблемы старой версии:
  - "rooms = 0" → закрытие дверных проёмов перед flood fill
  - "64 двери" → openings ищутся ТОЛЬКО как gap'ы в стенах
  - "windows = 0" → openings на внешних стенах автоматически окна
  - "wall partial" → лучшая фильтрация text/icons в structural_wall_mask
"""

from __future__ import annotations

import logging

import numpy as np

from app.schemas.geometry import (
    ApartmentGeometry,
    ConfidenceScores,
    Constraints,
    DebugLayers,
    Opening,
    Room,
    Scale,
    Wall,
    WallType,
)
from app.services.false_positive_filter import (
    compute_gated_confidence,
    filter_openings,
)
from app.services.opening_classifier import classify_openings
from app.services.opening_detector import find_openings
from app.services.preprocessing import (
    PreprocessedPlan,
    draw_debug_overlay,
    encode_to_base64,
    preprocess,
)
from app.services.room_polygonizer import polygonize_rooms
from app.services.scale_estimator import (
    OcrArea,
    estimate_scale_from_areas,
    extract_area_labels_from_image,
)
from app.services.structural_wall_mask import extract_wall_mask
from app.services.wall_detector import detect_walls
from app.services.wall_graph import build_wall_graph

logger = logging.getLogger(__name__)


VALIDATION_THRESHOLD = 0.55


def run_pipeline(
    image: np.ndarray,
    include_debug: bool = False,
) -> ApartmentGeometry:
    """Полный CV-пайплайн (V2): image → ApartmentGeometry."""
    h_orig, w_orig = image.shape[:2]
    logger.info(f"=== CV PIPELINE V2 START === ({w_orig}x{h_orig})")

    # ── 1. Предобработка ──────────────────────────────────────────────────
    plan: PreprocessedPlan = preprocess(image)
    h, w = plan.binary.shape
    logger.info(f"[1/9] Preprocess: {w}x{h}")

    # ── 2. Structural wall mask (отфильтрованная от текста/дуг/иконок) ───
    structural_mask, mask_stats = extract_wall_mask(plan.binary)
    logger.info(f"[2/9] Structural mask: {mask_stats}")

    # Заменяем wall_mask в plan'е на отфильтрованную
    plan.walls_mask = structural_mask

    # ── 3. Wall vectorization ─────────────────────────────────────────────
    walls, wall_conf = detect_walls(plan)
    logger.info(f"[3/9] Walls: {len(walls)} segments, conf={wall_conf:.2f}")

    # ── 4. Wall graph ─────────────────────────────────────────────────────
    graph = build_wall_graph(walls, w, h)
    walls = [edge.wall for edge in graph.edges.values()]
    has_outer = any(w.type == WallType.outer for w in walls)
    logger.info(f"[4/9] Graph: {len(graph.nodes)} nodes, {len(graph.edges)} edges, "
                f"has_outer={has_outer}")

    # ── 5. Room polygonization (с закрытием дверных проёмов) ──────────────
    rooms, closed_mask = polygonize_rooms(structural_mask, walls, px_per_meter=None)
    logger.info(f"[5/9] Rooms: {len(rooms)} polygons")

    # ── 6. Openings — ищем gap'ы только в найденных стенах ─────────────────
    candidates = find_openings(structural_mask, walls, px_per_meter=None)
    logger.info(f"[6/9] Opening candidates: {len(candidates)}")

    # ── 7. Классификация openings → door | window | unknown ────────────────
    classified = classify_openings(candidates, walls, plan.gray, plan.binary)
    raw_doors = [o for o in classified if o.type.value == "door"]
    raw_windows = [o for o in classified if o.type.value == "window"]
    logger.info(f"[7/9] Classified: doors={len(raw_doors)}, windows={len(raw_windows)}")

    # ── 8. OCR площадей + оценка масштаба ─────────────────────────────────
    ocr_areas: list[OcrArea] = extract_area_labels_from_image(plan.gray)
    room_dicts = [
        {
            "id": r.id,
            "area_px2": r.area_px2,
            "centroid": {"x": r.centroid.x, "y": r.centroid.y} if r.centroid else None,
        }
        for r in rooms
    ]
    px_per_meter, scale_conf = estimate_scale_from_areas(room_dicts, ocr_areas)

    # Обновляем m² для комнат
    if px_per_meter:
        for room in rooms:
            if room.area_px2 and room.area_m2 is None:
                room.area_m2 = round(room.area_px2 / (px_per_meter ** 2), 1)

    logger.info(f"[8/9] Scale: {px_per_meter} px/m (conf={scale_conf:.2f}), "
                f"OCR labels: {len(ocr_areas)}")

    # ── 9. False positive filter ──────────────────────────────────────────
    filtered_openings, fp_report = filter_openings(classified, walls, rooms)
    final_doors = [o for o in filtered_openings if o.type.value == "door"]
    final_windows = [o for o in filtered_openings if o.type.value == "window"]
    logger.info(f"[9/9] After FP filter: doors={len(final_doors)}, "
                f"windows={len(final_windows)}, "
                f"sanity_warnings={len(fp_report.sanity_warnings)}")

    # ── 10. Confidence scores ─────────────────────────────────────────────
    door_conf = (
        sum(o.confidence for o in final_doors) / len(final_doors)
        if final_doors else 0.5
    )
    window_conf = (
        sum(o.confidence for o in final_windows) / len(final_windows)
        if final_windows else 0.3
    )
    room_conf = (
        sum(r.confidence for r in rooms) / len(rooms)
        if rooms else 0.0
    )

    raw_scores = ConfidenceScores(
        wall_confidence=wall_conf,
        room_confidence=room_conf,
        door_confidence=door_conf,
        window_confidence=window_conf,
        scale_confidence=scale_conf,
    )
    gated_scores, sanity_warnings = compute_gated_confidence(
        walls=walls, rooms=rooms,
        doors=final_doors, windows=final_windows,
        raw_scores=raw_scores,
        has_outer_wall=has_outer,
    )

    # Объединяем sanity warnings
    all_warnings = list(fp_report.sanity_warnings) + list(sanity_warnings)

    # ── 11. Привязка openings к комнатам ──────────────────────────────────
    _assign_openings_to_rooms(rooms, filtered_openings)

    # ── 12. Debug-слои ────────────────────────────────────────────────────
    debug: DebugLayers | None = None
    if include_debug:
        debug = _build_debug_layers(
            plan, walls, rooms, final_doors, final_windows, structural_mask, closed_mask,
        )

    # ── 13. Сборка модели ─────────────────────────────────────────────────
    geometry = ApartmentGeometry(
        source_image_width_px=w,
        source_image_height_px=h,
        scale=Scale(
            px_per_meter=px_per_meter,
            source="detected_from_area_labels" if ocr_areas else "unknown",
            confidence=scale_conf,
        ),
        walls=walls,
        openings=filtered_openings,
        rooms=rooms,
        constraints=Constraints(),
        confidence=gated_scores,
        debug=debug,
        user_validated=False,
        validation_notes="; ".join(all_warnings) if all_warnings else "",
    )

    scale_str = f"{px_per_meter:.1f}" if px_per_meter else "unknown"
    logger.info(
        f"=== PIPELINE V2 DONE === "
        f"walls={len(walls)}, rooms={len(rooms)}, "
        f"doors={len(final_doors)}, windows={len(final_windows)}, "
        f"scale={scale_str} px/m, "
        f"overall={gated_scores.overall:.2f}"
    )

    return geometry


# ─── Утилиты ─────────────────────────────────────────────────────────────────


def _assign_openings_to_rooms(rooms: list[Room], openings: list[Opening]) -> None:
    """Связать проёмы с комнатами через wall_ids."""
    for room in rooms:
        room.opening_ids = []
    for opening in openings:
        for room in rooms:
            if opening.wall_id in (room.wall_ids or []):
                if opening.id not in room.opening_ids:
                    room.opening_ids.append(opening.id)


def _build_debug_layers(
    plan: PreprocessedPlan,
    walls: list[Wall], rooms: list[Room],
    doors: list[Opening], windows: list[Opening],
    structural_mask: np.ndarray, closed_mask: np.ndarray,
) -> DebugLayers:
    """Debug-визуализации для UI."""
    import cv2

    original_b64 = encode_to_base64(plan.original)
    structural_b64 = encode_to_base64(structural_mask)
    closed_b64 = encode_to_base64(closed_mask)

    # Стены
    walls_img = plan.original.copy()
    for wall in walls:
        p1 = (int(wall.start.x), int(wall.start.y))
        p2 = (int(wall.end.x), int(wall.end.y))
        color = (200, 60, 20) if wall.type == WallType.outer else (40, 100, 220)
        cv2.line(walls_img, p1, p2, color, 3)
    walls_b64 = encode_to_base64(walls_img)

    # Комнаты
    rooms_img = plan.original.copy()
    overlay = rooms_img.copy()
    palette = [(100, 220, 100), (100, 180, 220), (220, 180, 100),
               (200, 100, 200), (100, 200, 200), (220, 130, 100)]
    for idx, room in enumerate(rooms):
        color = palette[idx % len(palette)]
        pts = np.array([[int(p.x), int(p.y)] for p in room.polygon], dtype=np.int32)
        cv2.fillPoly(overlay, [pts], color)
        cv2.polylines(rooms_img, [pts], True, color, 2)
    rooms_img = cv2.addWeighted(rooms_img, 0.7, overlay, 0.3, 0)
    rooms_b64 = encode_to_base64(rooms_img)

    # Финальный оверлей
    wall_dicts = [
        {"start": {"x": w.start.x, "y": w.start.y},
         "end":   {"x": w.end.x,   "y": w.end.y}}
        for w in walls
    ]
    room_dicts = [
        {"polygon": [{"x": p.x, "y": p.y} for p in r.polygon]}
        for r in rooms
    ]
    door_dicts = [
        {"position": {"x": d.position.x, "y": d.position.y},
         "width_px": d.width_px}
        for d in doors
    ]
    window_dicts = [
        {"position": {"x": w.position.x, "y": w.position.y},
         "width_px": w.width_px}
        for w in windows
    ]
    final_img = draw_debug_overlay(plan, wall_dicts, room_dicts, door_dicts, window_dicts)
    final_b64 = encode_to_base64(final_img)

    return DebugLayers(
        original=original_b64,
        preprocessed=structural_b64,
        walls_detected=walls_b64,
        rooms_detected=rooms_b64,
        doors_detected=None,
        windows_detected=None,
        final_geometry=final_b64,
    )


def needs_user_validation(geometry: ApartmentGeometry) -> bool:
    """Нужна ли user-валидация геометрии?"""
    # Жёсткие условия — независимо от среднего confidence
    if len(geometry.rooms) == 0:
        return True
    if not geometry.scale.px_per_meter:
        return True
    if len(geometry.walls) < 4:
        return True
    return geometry.confidence.needs_user_validation(VALIDATION_THRESHOLD)
