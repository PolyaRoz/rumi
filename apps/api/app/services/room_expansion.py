"""
Room Expansion — расширение полигонов комнат до стен.

ПРОБЛЕМА:
room_polygonizer делает агрессивный MORPH_CLOSE (kernel=9 × 3 итерации)
для закрытия дверных проёмов. Эффект close = ~27px → стены в маске
выглядят толще на 13px с каждой стороны → полигоны комнат вырезаются
ВНУТРЬ на эти 13px от реальной стены. На UI это выглядит как
белые «зазоры» между полигоном и стеной.

РЕШЕНИЕ:
После polygonize_rooms iteratively dilate каждый полигон, но не
позволяем ему:
- залезать в стену (wall_mask)
- залезать в другую комнату

Алгоритм Watershed-стайл:
1. Создаём labels-mask где каждая комната = свой ID
2. На каждой итерации dilate каждый ID, кроме пикселей с другим ID
   и стенами
3. Повторяем пока есть прирост (макс ~30 итераций = 30px)
4. Restore polygon из конечной mask
"""

from __future__ import annotations

import logging

import cv2
import numpy as np

from app.schemas.geometry import Point, Room

logger = logging.getLogger(__name__)


# Максимум на сколько px расширяем (= compensation для polygonizer kernel)
MAX_EXPAND_PX = 30


def expand_rooms_to_walls(
    rooms: list[Room],
    wall_mask: np.ndarray,
    max_expand_px: int = MAX_EXPAND_PX,
) -> list[Room]:
    """
    Расширить полигоны комнат до стен.

    Args:
        rooms: список комнат после polygonize_rooms
        wall_mask: ОРИГИНАЛЬНАЯ маска стен (без gap-closing)
        max_expand_px: на сколько максимум расширять

    Returns:
        Список комнат с обновлёнными polygon (расширенными к стенам)
    """
    if not rooms:
        return rooms

    h, w = wall_mask.shape

    # ── 1. Создаём labels-mask: каждая комната = свой uniq label (1..N)
    labels = np.zeros((h, w), dtype=np.uint16)
    for idx, room in enumerate(rooms):
        if not room.polygon or len(room.polygon) < 3:
            continue
        pts = np.array([[int(p.x), int(p.y)] for p in room.polygon], dtype=np.int32)
        cv2.fillPoly(labels, [pts], idx + 1)  # +1 чтобы 0 оставался "пусто"

    initial_pixels = int(np.sum(labels > 0))

    # ── 2. Iterative dilation с ограничением walls + neighbour rooms ───────
    kernel = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))

    # Маска "куда нельзя расширяться" (стены) — фиксированная
    wall_block = (wall_mask > 0)

    for _iter in range(max_expand_px):
        # Чтобы dilation НЕ перекрывал соседние комнаты, делаем для каждой
        # отдельно по принципу: расширить free-space в текущую комнату
        # с приоритетом по существующим labels.

        # Где сейчас есть какая-то комната
        any_label = labels > 0

        # Кандидаты на захват: пустые пиксели НЕ являющиеся стеной
        free_space = (~any_label) & (~wall_block)
        if not np.any(free_space):
            break

        # Для каждого пустого пикселя смотрим какой label у его соседа
        # Используем cv2.dilate отдельно по каждому ID, потом конфликтующие
        # пиксели разрешаем по приоритету самого большого ID-полигона.
        new_labels = labels.copy()
        progress = False

        for room_idx in range(1, len(rooms) + 1):
            room_only = (labels == room_idx).astype(np.uint8) * 255
            if np.sum(room_only) == 0:
                continue
            dilated = cv2.dilate(room_only, kernel, iterations=1)
            # Только новые пиксели в free_space, ещё не занятые в new_labels
            gained = (dilated > 0) & free_space & (new_labels == 0)
            if np.any(gained):
                new_labels[gained] = room_idx
                progress = True

        if not progress:
            break

        labels = new_labels

    final_pixels = int(np.sum(labels > 0))
    logger.info(
        f"Room expansion: {initial_pixels}px → {final_pixels}px "
        f"(+{final_pixels - initial_pixels}px = {(final_pixels - initial_pixels) / initial_pixels * 100:.1f}%)"
    )

    # ── 3. Восстановить polygon из новых labels для каждой комнаты ─────────
    expanded_rooms: list[Room] = []
    for idx, room in enumerate(rooms):
        room_label = idx + 1
        room_mask = (labels == room_label).astype(np.uint8) * 255
        if np.sum(room_mask) == 0:
            # Не должно быть, но safety
            expanded_rooms.append(room)
            continue

        contours, _ = cv2.findContours(
            room_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE,
        )
        if not contours:
            expanded_rooms.append(room)
            continue

        cnt = max(contours, key=cv2.contourArea)
        perimeter = cv2.arcLength(cnt, True)
        epsilon = 0.005 * perimeter   # чуть мягче чем в polygonizer
        approx = cv2.approxPolyDP(cnt, epsilon, True)
        new_polygon = [Point(x=float(p[0][0]), y=float(p[0][1])) for p in approx]

        if len(new_polygon) < 3:
            expanded_rooms.append(room)
            continue

        # Centroid через moments
        M = cv2.moments(cnt)
        if M["m00"] > 0:
            cx = M["m10"] / M["m00"]
            cy = M["m01"] / M["m00"]
            new_centroid = Point(x=round(cx, 1), y=round(cy, 1))
        else:
            new_centroid = room.centroid

        # Обновляем area_px2
        new_area_px = float(np.sum(room_mask > 0))

        # Создаём обновлённую комнату
        room.polygon = new_polygon
        room.centroid = new_centroid
        room.area_px2 = round(new_area_px, 1)
        expanded_rooms.append(room)

    return expanded_rooms
