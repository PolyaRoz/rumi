"""
Главный оркестратор CV-пайплайна.

Порядок вызовов:
1. preprocess(image)          → PreprocessedPlan
2. detect_walls(plan)         → list[Wall] + wall_confidence
3. detect_rooms(plan, walls)  → list[Room] + room_confidence
4. detect_doors(plan, walls)  → list[Opening] + door_confidence
5. detect_windows(plan, walls)→ list[Opening] + window_confidence
6. OCR: extract_area_labels   → list[OcrArea]
7. estimate_scale(rooms, ocr) → (px_per_meter, scale_confidence)
8. assign_room_labels_from_ocr(rooms, ocr_areas) → updated rooms
9. Сборка ApartmentGeometry
10. Debug-оверлей (опционально)

После пайплайна caller может:
- вернуть geometry пользователю для валидации (если confidence < threshold)
- или сразу передать в FurniturePlacementEngine
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from app.schemas.geometry import (
    ApartmentGeometry,
    ConfidenceScores,
    Constraints,
    DebugLayers,
    Opening,
    OpeningType,
    Room,
    Scale,
    Wall,
)
from app.services.door_detector import detect_doors
from app.services.preprocessing import PreprocessedPlan, encode_to_base64, preprocess, draw_debug_overlay
from app.services.room_detector import assign_room_labels_from_ocr, detect_rooms
from app.services.scale_estimator import OcrArea, estimate_scale_from_areas, extract_area_labels_from_image
from app.services.wall_detector import detect_walls
from app.services.window_detector import detect_windows

logger = logging.getLogger(__name__)

# Порог confidence, ниже которого запрашиваем user-валидацию
VALIDATION_THRESHOLD = 0.55


def run_pipeline(
    image: np.ndarray,
    include_debug: bool = False,
) -> ApartmentGeometry:
    """
    Полный CV-пайплайн: image → ApartmentGeometry.

    Args:
        image: BGR numpy array (из cv2.imread или load_image_from_bytes)
        include_debug: добавить ли debug-слои в base64 (для UI)

    Returns:
        ApartmentGeometry — структурированная модель квартиры
    """
    h_orig, w_orig = image.shape[:2]
    logger.info(f"Запуск CV-пайплайна: {w_orig}x{h_orig}")

    # ── 1. Предобработка ──────────────────────────────────────────────────────
    plan: PreprocessedPlan = preprocess(image)
    h, w = plan.walls_mask.shape

    # ── 2. Стены ──────────────────────────────────────────────────────────────
    walls, wall_conf = detect_walls(plan)

    # ── 3. Комнаты (без масштаба — пересчитаем после OCR) ────────────────────
    rooms, room_conf = detect_rooms(plan, walls, px_per_meter=None)

    # ── 4. Двери ──────────────────────────────────────────────────────────────
    doors, door_conf = detect_doors(plan, walls, px_per_meter=None)

    # ── 5. Окна ───────────────────────────────────────────────────────────────
    windows, window_conf = detect_windows(plan, walls, px_per_meter=None)

    # ── 6. OCR площадей ───────────────────────────────────────────────────────
    ocr_areas: list[OcrArea] = extract_area_labels_from_image(plan.gray)

    # ── 7. Масштаб ────────────────────────────────────────────────────────────
    room_dicts = [
        {
            "id": r.id,
            "area_px2": r.area_px2,
            "centroid": {"x": r.centroid.x, "y": r.centroid.y} if r.centroid else None,
        }
        for r in rooms
    ]
    px_per_meter, scale_conf = estimate_scale_from_areas(room_dicts, ocr_areas)

    # ── 8. Обновить площади комнат если масштаб найден ───────────────────────
    if px_per_meter:
        for room in rooms:
            if room.area_px2 and room.area_m2 is None:
                room.area_m2 = round(room.area_px2 / (px_per_meter ** 2), 1)

    # ── 9. Связать OCR-подписи с комнатами ───────────────────────────────────
    if ocr_areas:
        rooms = assign_room_labels_from_ocr(
            rooms,
            [(a.value_m2, a.cx_px, a.cy_px) for a in ocr_areas],
        )

    # ── 10. Связать проёмы с комнатами ───────────────────────────────────────
    _assign_openings_to_rooms(rooms, doors + windows)

    # ── 11. Confidence scores ─────────────────────────────────────────────────
    confidence = ConfidenceScores(
        wall_confidence=wall_conf,
        room_confidence=room_conf,
        door_confidence=door_conf,
        window_confidence=window_conf,
        scale_confidence=scale_conf,
    )

    # ── 12. Масштаб ───────────────────────────────────────────────────────────
    scale = Scale(
        px_per_meter=px_per_meter,
        source="detected_from_area_labels" if ocr_areas else "unknown",
        confidence=scale_conf,
    )

    # ── 13. Debug-слои ────────────────────────────────────────────────────────
    debug: DebugLayers | None = None
    if include_debug:
        debug = _build_debug_layers(
            plan, walls, rooms, doors, windows,
            px_per_meter=px_per_meter,
        )

    # ── 14. Сборка модели ─────────────────────────────────────────────────────
    geometry = ApartmentGeometry(
        source_image_width_px=w,
        source_image_height_px=h,
        scale=scale,
        walls=walls,
        openings=doors + windows,
        rooms=rooms,
        constraints=Constraints(),
        confidence=confidence,
        debug=debug,
        user_validated=False,
    )

    logger.info(
        f"Пайплайн завершён: "
        f"{len(walls)} стен, {len(rooms)} комнат, "
        f"{len(doors)} дверей, {len(windows)} окон, "
        f"scale={px_per_meter:.1f if px_per_meter else 'unknown'} px/m, "
        f"overall_confidence={confidence.overall:.2f}, "
        f"needs_validation={confidence.needs_user_validation(VALIDATION_THRESHOLD)}"
    )

    return geometry


def _assign_openings_to_rooms(
    rooms: list[Room], openings: list[Opening]
) -> None:
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
    walls: list[Wall],
    rooms: list[Room],
    doors: list[Opening],
    windows: list[Opening],
    px_per_meter: float | None,
) -> DebugLayers:
    """Построить base64-изображения для каждого слоя отладки."""
    # Оригинал
    original_b64 = encode_to_base64(plan.original)

    # Бинаризованное
    preprocessed_b64 = encode_to_base64(plan.binary)

    # Стены
    import cv2
    walls_img = plan.original.copy()
    for wall in walls:
        p1 = (int(wall.start.x), int(wall.start.y))
        p2 = (int(wall.end.x), int(wall.end.y))
        color = (200, 60, 20) if wall.type.value == "outer" else (40, 100, 220)
        cv2.line(walls_img, p1, p2, color, 3)
    walls_b64 = encode_to_base64(walls_img)

    # Комнаты
    rooms_img = plan.original.copy()
    room_overlay = rooms_img.copy()
    colors = [(100, 220, 100), (100, 180, 220), (220, 180, 100),
              (200, 100, 200), (100, 200, 200), (220, 130, 100)]
    for idx, room in enumerate(rooms):
        import numpy as np
        color = colors[idx % len(colors)]
        pts = np.array([[int(p.x), int(p.y)] for p in room.polygon], dtype=np.int32)
        cv2.fillPoly(room_overlay, [pts], color)
        cv2.polylines(rooms_img, [pts], True, color, 2)
        if room.centroid:
            label = f"{room.label.value[:3]} {room.area_m2 or '?'}m2"
            cv2.putText(rooms_img, label,
                        (int(room.centroid.x - 20), int(room.centroid.y)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)
    rooms_img = cv2.addWeighted(rooms_img, 0.7, room_overlay, 0.3, 0)
    rooms_b64 = encode_to_base64(rooms_img)

    # Финальный оверлей (все слои)
    wall_dicts = [{"start": {"x": w.start.x, "y": w.start.y},
                   "end": {"x": w.end.x, "y": w.end.y}} for w in walls]
    room_dicts = [{"polygon": [{"x": p.x, "y": p.y} for p in r.polygon]} for r in rooms]
    door_dicts = [{"position": {"x": d.position.x, "y": d.position.y},
                   "width_px": d.width_px} for d in doors]
    window_dicts = [{"position": {"x": ww.position.x, "y": ww.position.y},
                     "width_px": ww.width_px} for ww in windows]
    final_img = draw_debug_overlay(plan, wall_dicts, room_dicts, door_dicts, window_dicts)
    final_b64 = encode_to_base64(final_img)

    return DebugLayers(
        original=original_b64,
        preprocessed=preprocessed_b64,
        walls_detected=walls_b64,
        rooms_detected=rooms_b64,
        doors_detected=None,    # TODO: отдельный слой дверей
        windows_detected=None,  # TODO: отдельный слой окон
        final_geometry=final_b64,
    )


def needs_user_validation(geometry: ApartmentGeometry) -> bool:
    """Нужна ли пользовательская валидация геометрии?"""
    return geometry.confidence.needs_user_validation(VALIDATION_THRESHOLD)
