"""
Room Polygonizer — извлечение комнат через WALL-GRAPH-FIRST подход.

ПРОБЛЕМА предыдущей версии:
  Старый room_detector делал inverse + flood fill. Но дверные проёмы — это
  ДЫРЫ в стенах. Через дыру flood fill "вытекал" из одной комнаты в другую,
  и в итоге всё помещение получалось одним полигоном — или ничего не находилось.

РЕШЕНИЕ:
  1. Берём wall_mask
  2. Закрываем КОРОТКИЕ разрывы (door-sized gaps): 5–25 px вдоль линии стены
  3. На закрытой маске делаем flood fill / contour extraction
  4. Каждая закрытая область = комната
  5. Сохраняем gap-координаты для последующего opening_detector

Морфологический dilate+erode размером 6–8 px закрывает дверные проёмы
типичной ширины (0.6–1.2 м при масштабе ~50px/м), но НЕ закрывает
длинные зазоры между комнатами.
"""

from __future__ import annotations

import logging
import math

import cv2
import numpy as np

from app.schemas.geometry import Point, Room, RoomLabel, Wall

logger = logging.getLogger(__name__)


# ─── Параметры ───────────────────────────────────────────────────────────────

# Размер ядра для закрытия дверных проёмов (px).
# 8px ≈ 16-20px в исходном пространстве после morph close = ~30-40px зазор.
DOOR_GAP_CLOSE_KERNEL = 9

# Минимальная площадь комнаты в px²
MIN_ROOM_AREA_PX = 1500

# Максимальная фракция изображения для одной комнаты
MAX_ROOM_AREA_FRACTION = 0.65

# Поля от границы (отбрасываем компоненты, касающиеся края)
BORDER_MARGIN = 4

# Аппроксимация полигона
POLY_EPSILON_FRACTION = 0.008


# ─── Главная функция ─────────────────────────────────────────────────────────


def polygonize_rooms(
    wall_mask: np.ndarray,
    walls: list[Wall],
    px_per_meter: float | None = None,
) -> tuple[list[Room], np.ndarray]:
    """
    Извлечь комнаты из маски стен.

    Args:
        wall_mask: бинарная маска со стенами (255=стена, 0=фон)
        walls: список стен (для связи с wall_ids)
        px_per_meter: масштаб (опционально для расчёта area_m2)

    Returns:
        (rooms, closed_mask)
        closed_mask — wall_mask с закрытыми дверными проёмами,
        используется потом для opening_detector чтобы найти эти gap'ы.
    """
    h, w = wall_mask.shape

    # ── 1a. УКРЕПЛЕНИЕ: рисуем найденные walls поверх mask толстыми линиями.
    # Это закрывает все дверные проёмы и точно соединяет смежные сегменты.
    # Без этого 40-50px gap'ы между сегментами не закроются никаким morph close.
    fortified = wall_mask.copy()
    if walls:
        # Толщина = max(actual_thickness, 5) — чтобы соседние линии слились
        for wall in walls:
            p1 = (int(round(wall.start.x)), int(round(wall.start.y)))
            p2 = (int(round(wall.end.x)), int(round(wall.end.y)))
            t = max(int(round(wall.thickness_px)), 5)
            cv2.line(fortified, p1, p2, 255, t)

    # ── 1b. Закрыть оставшиеся короткие разрывы (door-sized gaps) ─────────
    kernel_size = DOOR_GAP_CLOSE_KERNEL
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
    closed = cv2.morphologyEx(fortified, cv2.MORPH_CLOSE, kernel, iterations=3)

    # ── 2. Инвертируем — внутренние области = 255 ─────────────────────────
    interior = cv2.bitwise_not(closed)

    # ── 3. Заливаем "внешний фон" с углов изображения ─────────────────────
    flood_mask = np.zeros((h + 2, w + 2), dtype=np.uint8)
    interior_clean = interior.copy()
    for cx, cy in [(0, 0), (0, h - 1), (w - 1, 0), (w - 1, h - 1)]:
        if interior_clean[cy, cx] == 255:
            cv2.floodFill(interior_clean, flood_mask, (cx, cy), 0)

    # ── 4. Connected components → каждая = комната ────────────────────────
    nb_components, labels, stats, centroids = cv2.connectedComponentsWithStats(
        interior_clean, connectivity=8
    )

    rooms: list[Room] = []
    img_area = w * h
    max_room_area = img_area * MAX_ROOM_AREA_FRACTION

    for i in range(1, nb_components):
        x_bbox, y_bbox, cw, ch, area = stats[i]
        cx, cy = centroids[i]

        # Фильтрация
        if area < MIN_ROOM_AREA_PX:
            continue
        if area > max_room_area:
            continue
        # Касается границы изображения → внешнее пространство
        if (x_bbox <= BORDER_MARGIN or y_bbox <= BORDER_MARGIN or
            x_bbox + cw >= w - BORDER_MARGIN or
            y_bbox + ch >= h - BORDER_MARGIN):
            continue

        # ── 5. Извлечь полигон через contour ───────────────────────────────
        component_mask = (labels == i).astype(np.uint8) * 255
        contours, _ = cv2.findContours(component_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue
        cnt = max(contours, key=cv2.contourArea)

        # Аппроксимация (упрощаем дрожание)
        perimeter = cv2.arcLength(cnt, True)
        epsilon = POLY_EPSILON_FRACTION * perimeter
        approx = cv2.approxPolyDP(cnt, epsilon, True)
        polygon = [Point(x=float(p[0][0]), y=float(p[0][1])) for p in approx]
        if len(polygon) < 3:
            continue

        # ── 6. Solidity (отделить нормальные комнаты от фрагментов) ────────
        hull_area = cv2.contourArea(cv2.convexHull(cnt))
        solidity = float(area / hull_area) if hull_area > 0 else 0
        if solidity < 0.50:
            # Слишком "разорванная" — скорее всего шум или коридор-разрыв
            continue

        # ── 7. Тип комнаты (эвристика по площади) ──────────────────────────
        aspect = max(cw, ch) / max(min(cw, ch), 1)
        label = _infer_label(area, aspect, img_area)

        area_m2: float | None = None
        if px_per_meter and px_per_meter > 0:
            area_m2 = round(area / (px_per_meter ** 2), 1)

        # ── 8. Confidence: solidity * size_normalization ───────────────────
        size_score = min(1.0, area / (img_area * 0.05))
        confidence = float(min(1.0, solidity * 0.6 + size_score * 0.4))

        room = Room(
            id=f"room_{len(rooms):03d}",
            label=label,
            area_m2=area_m2,
            area_px2=round(float(area), 1),
            polygon=polygon,
            centroid=Point(x=float(cx), y=float(cy)),
            locked=True,
            confidence=round(confidence, 3),
        )

        # Привязка стен (стены в пределах bbox комнаты)
        room.wall_ids = _walls_for_bbox(walls, x_bbox, y_bbox, cw, ch)

        rooms.append(room)

    # Сортировка: большие комнаты — первыми (для логики типизации)
    rooms.sort(key=lambda r: r.area_px2 or 0, reverse=True)
    for idx, room in enumerate(rooms):
        room.id = f"room_{idx:03d}"

    logger.info(
        f"Полигонизация: {len(rooms)} комнат "
        f"(closed_kernel={kernel_size}px), areas={[r.area_px2 for r in rooms]}"
    )

    return rooms, closed


def _infer_label(area_px: float, aspect: float, img_area: float) -> RoomLabel:
    """Эвристика типа комнаты по площади и пропорциям."""
    if aspect > 3.5:
        return RoomLabel.corridor
    if area_px < img_area * 0.025:
        return RoomLabel.bathroom
    if area_px < img_area * 0.05:
        return RoomLabel.toilet if aspect > 2 else RoomLabel.bedroom
    if area_px < img_area * 0.10:
        return RoomLabel.bedroom
    if area_px < img_area * 0.15:
        return RoomLabel.kitchen
    return RoomLabel.living_room


def _walls_for_bbox(
    walls: list[Wall], x: int, y: int, w: int, h: int,
    padding: int = 15,
) -> list[str]:
    """Стены, чьи концы попадают в bbox комнаты ± padding."""
    x_min, y_min = x - padding, y - padding
    x_max, y_max = x + w + padding, y + h + padding
    result = []
    for wall in walls:
        for pt in [wall.start, wall.end]:
            if x_min <= pt.x <= x_max and y_min <= pt.y <= y_max:
                result.append(wall.id)
                break
    return result
