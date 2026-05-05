"""
Детектор комнат.

Алгоритм:
1. Инвертируем walls_mask → пространство "не-стена"
2. Flood-fill с границей → находим замкнутые области (комнаты)
3. Фильтруем по площади (маленькие → шум, огромные → внешнее пространство)
4. Строим полигоны аппроксимацией контуров (cv2.approxPolyDP)
5. Вычисляем центроид каждой комнаты
6. Определяем тип комнаты по соотношению сторон и площади (эвристика)
7. Связываем стены и проёмы с комнатами

Масштабирование:
  Если scale (px_per_meter) известен — вычисляем area_m2.
  Если нет — оставляем area_px2 и None для area_m2.
"""

from __future__ import annotations

import logging
import math

import cv2
import numpy as np

from app.schemas.geometry import Point, Room, RoomLabel, Wall
from app.services.preprocessing import PreprocessedPlan

logger = logging.getLogger(__name__)

# Настройки
MIN_ROOM_AREA_PX = 2000    # минимальная площадь комнаты в пикселях
MAX_ROOM_AREA_FRACTION = 0.6  # комната не занимает > 60% изображения
POLY_EPSILON_FRACTION = 0.01   # аппроксимация полигона (доля периметра)
BORDER_MARGIN_PX = 5           # игнорировать области, касающиеся границы


def _build_room_mask(walls_mask: np.ndarray) -> np.ndarray:
    """
    Из маски стен строим маску "внутри комнат":
    - Инвертируем (фон → белый)
    - Закрываем мелкие дыры в стенах (morph close)
    - Убираем внешнее пространство (flood fill от углов)
    """
    h, w = walls_mask.shape

    # 1. Инвертируем: всё не-стена = 255
    inv = cv2.bitwise_not(walls_mask)

    # 2. Закрываем маленькие дыры в стенах (проёмы дверей)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    closed = cv2.morphologyEx(inv, cv2.MORPH_CLOSE, kernel, iterations=2)

    # 3. Заливаем внешнее пространство с 4 углов → получаем маску "внешнего"
    flood_mask = np.zeros((h + 2, w + 2), dtype=np.uint8)
    external = closed.copy()
    corners = [(0, 0), (0, h - 1), (w - 1, 0), (w - 1, h - 1)]
    for cx, cy in corners:
        if external[cy, cx] == 255:
            cv2.floodFill(external, flood_mask, (cx, cy), 0)

    return external


def _filter_border_contour(cnt: np.ndarray, img_w: int, img_h: int,
                            margin: int = BORDER_MARGIN_PX) -> bool:
    """True если контур касается границы изображения — это внешнее пространство."""
    x, y, cw, ch = cv2.boundingRect(cnt)
    return (
        x <= margin or y <= margin or
        x + cw >= img_w - margin or
        y + ch >= img_h - margin
    )


def _approx_polygon(cnt: np.ndarray) -> list[Point]:
    """Аппроксимировать контур полигоном, убрать дрожание точек."""
    perimeter = cv2.arcLength(cnt, True)
    epsilon = POLY_EPSILON_FRACTION * perimeter
    approx = cv2.approxPolyDP(cnt, epsilon, True)
    return [Point(x=float(p[0][0]), y=float(p[0][1])) for p in approx]


def _compute_centroid(polygon: list[Point]) -> Point:
    xs = [p.x for p in polygon]
    ys = [p.y for p in polygon]
    return Point(x=sum(xs) / len(xs), y=sum(ys) / len(ys))


def _infer_room_label(area_px: float, aspect_ratio: float,
                      centroid: Point, img_w: int, img_h: int) -> RoomLabel:
    """
    Эвристика для определения типа комнаты.
    Используется только если нет текстовых подписей на плане.

    Правила (упрощённые):
    - Очень маленькая: санузел / туалет / коридор
    - Вытянутая (aspect > 3): коридор
    - Средняя: спальня / детская
    - Большая: гостиная / кухня-гостиная
    - Близко к верхнему/нижнему краю: балкон (эвристика слабая)
    """
    if aspect_ratio > 3.0:
        return RoomLabel.corridor

    img_area = img_w * img_h

    if area_px < img_area * 0.04:
        # Очень маленькая
        if aspect_ratio < 2.0:
            return RoomLabel.bathroom
        return RoomLabel.corridor

    if area_px < img_area * 0.09:
        return RoomLabel.bedroom  # Спальня

    if area_px < img_area * 0.15:
        return RoomLabel.kitchen  # Кухня

    return RoomLabel.living_room  # Самая большая = гостиная


def _find_walls_for_room(room: Room, walls: list[Wall],
                         proximity_px: float = 15.0) -> list[str]:
    """Найти стены, которые ограничивают данную комнату."""
    room_poly_pts = np.array([[p.x, p.y] for p in room.polygon], dtype=np.float32)
    wall_ids = []
    for wall in walls:
        # Проверяем, лежат ли концы стены близко к полигону комнаты
        for pt in [wall.start, wall.end]:
            dist = cv2.pointPolygonTest(room_poly_pts, (pt.x, pt.y), True)
            if abs(dist) < proximity_px:
                wall_ids.append(wall.id)
                break
    return list(set(wall_ids))


def detect_rooms(
    plan: PreprocessedPlan,
    walls: list[Wall],
    px_per_meter: float | None = None,
) -> tuple[list[Room], float]:
    """
    Главная функция детектора комнат.

    Args:
        plan: результат предобработки
        walls: уже найденные стены
        px_per_meter: масштаб (если известен)

    Returns:
        (list[Room], overall_confidence)
    """
    h, w = plan.walls_mask.shape

    # 1. Построить маску комнат
    room_mask = _build_room_mask(plan.walls_mask)

    # 2. Найти контуры
    contours, hierarchy = cv2.findContours(
        room_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    max_area = w * h * MAX_ROOM_AREA_FRACTION

    rooms: list[Room] = []
    confidences: list[float] = []

    for i, cnt in enumerate(contours):
        area_px = cv2.contourArea(cnt)

        # Фильтрация
        if area_px < MIN_ROOM_AREA_PX:
            continue
        if area_px > max_area:
            continue
        if _filter_border_contour(cnt, w, h):
            continue

        # Полигон
        polygon = _approx_polygon(cnt)
        if len(polygon) < 3:
            continue

        # Геометрические характеристики
        x_bbox, y_bbox, bw, bh = cv2.boundingRect(cnt)
        aspect = max(bw, bh) / max(min(bw, bh), 1)
        centroid = _compute_centroid(polygon)

        # Тип комнаты (эвристика)
        label = _infer_room_label(area_px, aspect, centroid, w, h)

        # Площадь в м²
        area_m2: float | None = None
        if px_per_meter and px_per_meter > 0:
            area_m2 = round(area_px / (px_per_meter ** 2), 1)

        # Confidence: насколько контур "аккуратный"
        hull_area = cv2.contourArea(cv2.convexHull(cnt))
        solidity = area_px / hull_area if hull_area > 0 else 0
        confidence = min(solidity * 0.8 + 0.2, 1.0)

        room = Room(
            id=f"room_{i:03d}",
            label=label,
            area_m2=area_m2,
            area_px2=round(float(area_px), 1),
            polygon=polygon,
            centroid=centroid,
            locked=True,
            confidence=round(float(confidence), 3),
        )

        # Связываем с стенами
        room.wall_ids = _find_walls_for_room(room, walls)

        rooms.append(room)
        confidences.append(confidence)

    # Сортировка: самые большие комнаты — первыми
    rooms.sort(key=lambda r: r.area_px2 or 0, reverse=True)

    # Переиндексация для читаемости
    for idx, room in enumerate(rooms):
        room.id = f"room_{idx:03d}"

    overall_confidence = float(np.mean(confidences)) if confidences else 0.0
    logger.info(
        f"Комнаты: {len(rooms)} найдено, confidence={overall_confidence:.2f}"
    )
    for r in rooms:
        logger.debug(
            f"  {r.id}: {r.label.value}, "
            f"area={r.area_m2}m² ({r.area_px2:.0f}px²), "
            f"conf={r.confidence:.2f}"
        )

    return rooms, overall_confidence


def assign_room_labels_from_ocr(
    rooms: list[Room],
    ocr_areas: list[tuple[float, float, float]],   # (area_m2, cx_px, cy_px)
) -> list[Room]:
    """
    Связать OCR-распознанные площади (area_m2, cx, cy) с ближайшей комнатой.
    Обновляет room.area_m2 из реальных подписей на плане.

    Args:
        rooms: список комнат
        ocr_areas: список (площадь_м², x_центроида, y_центроида) из OCR

    Returns:
        обновлённый список комнат
    """
    for area_m2, cx, cy in ocr_areas:
        if not rooms:
            break
        # Ближайшая комната по центроиду
        best_room = min(
            rooms,
            key=lambda r: (
                (r.centroid.x - cx) ** 2 + (r.centroid.y - cy) ** 2
                if r.centroid else float("inf")
            ),
        )
        if best_room.area_m2 is None:
            best_room.area_m2 = area_m2
            logger.debug(f"OCR: {best_room.id} ← {area_m2} м²")

    return rooms
