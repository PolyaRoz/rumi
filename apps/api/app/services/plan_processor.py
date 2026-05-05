"""
CV-пайплайн V3: AREA-LABEL-ANCHORED.

Изменения от V2:
- OCR площадей запускается ДО полигонизации комнат (был ПОСЛЕ).
- Полигонизация выдаёт ВСЕ кандидаты — фильтрация в anchoring.
- room_anchoring привязывает каждую OCR-метку к содержащему полигону;
  фрагменты без метки и недостаточно крупные → отброшены.
- Классификация типа комнаты по фактической area_m2, не по форме.

Pipeline:
  1. preprocess
  2. extract_wall_mask (структурный)
  3. detect_walls (HoughLinesP)
  4. wall_graph (snap, intersect, outer/inner)
  5. **OCR area labels** ← новое место
  6. polygonize_rooms (raw кандидаты)
  7. **anchor_rooms_to_labels** ← новый этап
  8. estimate_scale_from_areas (по anchored rooms)
  9. find_openings (gap-based)
  10. classify_openings (door | window)
  11. filter_openings (sanity rules)
  12. confidence gating
  13. сборка ApartmentGeometry
"""

from __future__ import annotations

import logging

import numpy as np

from app.schemas.geometry import (
    ApartmentGeometry,
    AreaLabel,
    ConfidenceScores,
    Constraints,
    DebugLayers,
    Opening,
    Point,
    RejectedFragment,
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
from app.services.room_anchoring import anchor_rooms_to_labels
from app.services.room_polygonizer import polygonize_rooms
from app.services.room_recovery import recover_rooms_from_labels
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


def run_pipeline(image: np.ndarray, include_debug: bool = False) -> ApartmentGeometry:
    """Полный CV-пайплайн V3."""
    h_orig, w_orig = image.shape[:2]
    logger.info(f"=== CV PIPELINE V3 START === ({w_orig}x{h_orig})")

    # ── 1. Предобработка ──────────────────────────────────────────────────
    plan: PreprocessedPlan = preprocess(image)
    h, w = plan.binary.shape
    img_area = h * w

    # ── 2. Structural wall mask ───────────────────────────────────────────
    structural_mask, mask_stats = extract_wall_mask(plan.binary)
    plan.walls_mask = structural_mask
    logger.info(f"[1-2] preprocess + wall_mask: accepted={mask_stats.get('accepted')}")

    # ── 3. Wall vectorization ─────────────────────────────────────────────
    walls, wall_conf = detect_walls(plan)
    logger.info(f"[3] walls: {len(walls)}, conf={wall_conf:.2f}")

    # ── 4. Wall graph ─────────────────────────────────────────────────────
    graph = build_wall_graph(walls, w, h)
    walls = [edge.wall for edge in graph.edges.values()]
    has_outer = any(w.type == WallType.outer for w in walls)
    logger.info(f"[4] graph: {len(graph.nodes)} nodes, has_outer={has_outer}")

    # ── 5. OCR площадей (ДО полигонизации!) ──────────────────────────────
    ocr_areas: list[OcrArea] = extract_area_labels_from_image(plan.gray)
    logger.info(f"[5] OCR labels: {len(ocr_areas)} → "
                f"{sorted([round(a.value_m2, 1) for a in ocr_areas])}")

    # ── 6. Полигонизация (raw кандидаты) ──────────────────────────────────
    candidate_rooms, closed_mask = polygonize_rooms(
        structural_mask, walls, px_per_meter=None,
    )
    logger.info(f"[6] room candidates (pre-anchor): {len(candidate_rooms)}")

    # ── 7. Анкоринг к OCR-меткам ──────────────────────────────────────────
    rooms, unresolved_labels, rejected_fragments = anchor_rooms_to_labels(
        candidate_rooms, ocr_areas, img_area_px=float(img_area),
    )
    logger.info(
        f"[7] After anchoring: {len(rooms)} rooms "
        f"(labeled={sum(1 for r in rooms if r.area_m2 is not None)}, "
        f"unlabeled={sum(1 for r in rooms if r.area_m2 is None)}), "
        f"unresolved labels={len(unresolved_labels)}, "
        f"rejected fragments={len(rejected_fragments)}"
    )

    # ── 7b. Recovery: для каждой неразрешённой метки запускаем flood fill
    if unresolved_labels:
        recovered, still_unresolved = recover_rooms_from_labels(
            closed_mask=closed_mask,
            unresolved_labels=unresolved_labels,
            existing_rooms=rooms,
            px_per_meter=None,  # ещё не считали
            img_area_px=float(img_area),
        )
        if recovered:
            rooms.extend(recovered)
            # Перенумеруем для красивых ID
            for i, r in enumerate(rooms):
                if not r.id.startswith("room_recovered"):
                    r.id = f"room_{i:03d}"
            logger.info(
                f"[7b] Recovery: +{len(recovered)} комнат, "
                f"unresolved осталось {len(still_unresolved)}"
            )

    # ── 8. Оценка масштаба по anchored rooms ──────────────────────────────
    room_dicts = [
        {
            "id": r.id,
            "area_px2": r.area_px2,
            "centroid": {"x": r.centroid.x, "y": r.centroid.y} if r.centroid else None,
        }
        for r in rooms if r.area_m2 is not None
    ]
    px_per_meter, scale_conf = estimate_scale_from_areas(room_dicts, ocr_areas)

    if px_per_meter and px_per_meter > 0:
        # Заполнить estimated area_m2 для unlabeled rooms
        for room in rooms:
            if room.area_m2 is None and room.area_px2:
                room.area_m2 = round(room.area_px2 / (px_per_meter ** 2), 1)

    logger.info(f"[8] scale: {px_per_meter} px/m, conf={scale_conf:.2f}")

    # ── 9. Openings — gaps в стенах ───────────────────────────────────────
    candidates = find_openings(structural_mask, walls, px_per_meter=px_per_meter)
    logger.info(f"[9] opening candidates: {len(candidates)}")

    # ── 10. Классификация openings ────────────────────────────────────────
    classified = classify_openings(candidates, walls, plan.gray, plan.binary)
    raw_doors = [o for o in classified if o.type.value == "door"]
    raw_windows = [o for o in classified if o.type.value == "window"]
    logger.info(f"[10] classified: doors={len(raw_doors)}, windows={len(raw_windows)}")

    # ── 11. False-positive filter ─────────────────────────────────────────
    filtered_openings, fp_report = filter_openings(classified, walls, rooms)
    final_doors = [o for o in filtered_openings if o.type.value == "door"]
    final_windows = [o for o in filtered_openings if o.type.value == "window"]
    logger.info(
        f"[11] After FP filter: doors={len(final_doors)}, windows={len(final_windows)}"
    )

    # ── 12. Confidence scores с gating ────────────────────────────────────
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
    all_warnings = list(fp_report.sanity_warnings) + list(sanity_warnings)

    # ── 13. Привязка openings к комнатам ──────────────────────────────────
    _assign_openings_to_rooms(rooms, filtered_openings)

    # ── 13b. Собираем detected_area_labels (для UI прозрачности) ─────────
    # Каждая OCR-метка либо привязана к комнате (по совпадению area_m2),
    # либо unresolved (никакая комната не имеет этой площади).
    detected_labels = _build_detected_labels(ocr_areas, rooms)

    # ── 13c. Rejected fragments (отброшенные кандидаты комнат) ────────────
    rejected_fragments_list = [
        RejectedFragment(
            id=room.id or f"frag_{i:03d}",
            polygon=room.polygon,
            area_px2=room.area_px2 or 0,
            centroid=room.centroid,
            reason=reason,
        )
        for i, (room, reason) in enumerate(rejected_fragments)
    ]

    # ── 14. Debug-слои ────────────────────────────────────────────────────
    debug: DebugLayers | None = None
    if include_debug:
        debug = _build_debug_layers(
            plan, walls, rooms, final_doors, final_windows,
            structural_mask, closed_mask,
            ocr_areas=ocr_areas,
        )

    # ── 15. Сборка ApartmentGeometry ──────────────────────────────────────
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
        detected_area_labels=detected_labels,
        rejected_fragments=rejected_fragments_list,
        user_validated=False,
        validation_notes="; ".join(all_warnings) if all_warnings else "",
    )

    scale_str = f"{px_per_meter:.1f}" if px_per_meter else "unknown"
    logger.info(
        f"=== PIPELINE V3 DONE === "
        f"walls={len(walls)}, rooms={len(rooms)} "
        f"({sum(1 for r in rooms if r.area_m2 is not None)} labeled), "
        f"doors={len(final_doors)}, windows={len(final_windows)}, "
        f"scale={scale_str} px/m, "
        f"overall={gated_scores.overall:.2f}"
    )

    return geometry


# ─── Утилиты ─────────────────────────────────────────────────────────────────


def _build_detected_labels(
    ocr_areas, rooms: list[Room]
) -> list[AreaLabel]:
    """
    Связать каждую OCR-метку с комнатой по area_m2 + проверке is_inside_polygon.

    Если метка попала в полигон комнаты И её area_m2 совпадает — привязана.
    Если метку восстановили через recovery — там тоже area_m2 совпадает.
    Если ни одна комната не имеет этой area_m2 — unresolved.
    """
    from app.services.room_anchoring import _point_in_polygon

    labels: list[AreaLabel] = []
    for ocr in ocr_areas:
        assigned_id = None
        recovered_id = None

        # Приоритет 1: метка лежит ВНУТРИ полигона — точная привязка
        for room in rooms:
            if not room.polygon:
                continue
            if _point_in_polygon(ocr.cx_px, ocr.cy_px, room.polygon):
                if room.area_m2 == ocr.value_m2:
                    if room.id.startswith("room_recovered"):
                        recovered_id = room.id
                    else:
                        assigned_id = room.id
                    break

        # Приоритет 2: точное совпадение area_m2 (метка снаружи polygon
        # из-за неточностей флуд-филла или метка стоит на границе)
        if assigned_id is None and recovered_id is None:
            for room in rooms:
                if room.area_m2 == ocr.value_m2:
                    if room.id.startswith("room_recovered"):
                        recovered_id = room.id
                    else:
                        assigned_id = room.id
                    break

        labels.append(AreaLabel(
            text=ocr.raw_text or str(ocr.value_m2),
            value_m2=ocr.value_m2,
            position=Point(x=ocr.cx_px, y=ocr.cy_px),
            confidence=0.85,
            assigned_room_id=assigned_id,
            recovered_room_id=recovered_id,
        ))
    return labels


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
    ocr_areas: list[OcrArea] | None = None,
) -> DebugLayers:
    """Debug-слои для UI."""
    import cv2

    original_b64 = encode_to_base64(plan.original)
    structural_b64 = encode_to_base64(structural_mask)

    # Стены
    walls_img = plan.original.copy()
    for wall in walls:
        p1 = (int(wall.start.x), int(wall.start.y))
        p2 = (int(wall.end.x), int(wall.end.y))
        color = (200, 60, 20) if wall.type == WallType.outer else (40, 100, 220)
        cv2.line(walls_img, p1, p2, color, 3)
    walls_b64 = encode_to_base64(walls_img)

    # Комнаты с подписями
    rooms_img = plan.original.copy()
    overlay = rooms_img.copy()
    palette = [(100, 220, 100), (100, 180, 220), (220, 180, 100),
               (200, 100, 200), (100, 200, 200), (220, 130, 100)]
    for idx, room in enumerate(rooms):
        color = palette[idx % len(palette)]
        pts = np.array([[int(p.x), int(p.y)] for p in room.polygon], dtype=np.int32)
        cv2.fillPoly(overlay, [pts], color)
        cv2.polylines(rooms_img, [pts], True, color, 2)
        if room.centroid and room.area_m2:
            cv2.putText(rooms_img, f"{room.area_m2}m2",
                        (int(room.centroid.x - 25), int(room.centroid.y)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
    rooms_img = cv2.addWeighted(rooms_img, 0.7, overlay, 0.3, 0)

    # Маркеры OCR-меток
    if ocr_areas:
        for ocr in ocr_areas:
            cv2.circle(rooms_img, (int(ocr.cx_px), int(ocr.cy_px)), 6, (0, 0, 255), -1)
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
    """Жёсткие условия — независимо от среднего confidence."""
    if len(geometry.rooms) == 0:
        return True
    if not geometry.scale.px_per_meter:
        return True
    if len(geometry.walls) < 4:
        return True
    return geometry.confidence.needs_user_validation(VALIDATION_THRESHOLD)
