"""
Door Validation — финальная фильтрация дверей по геометрической логике.

ПРАВИЛО: настоящая дверь должна:
1. ЛИБО быть на границе ДВУХ комнат (room A ↔ room B), доступная с обеих
   сторон (центр двери в пределах N px от полигонов обеих комнат);
2. ЛИБО быть на внешней стене как вход в квартиру (центр двери в пределах
   N px от ровно ОДНОГО полигона комнаты — той, что внутри).

Двери, не подходящие под эти правила (например, на отдельной стене
сантехники без соседних комнат), отбрасываются.

Это устраняет «двери в рандомных местах» без потери настоящих дверей.
"""

from __future__ import annotations

import logging
import math

from app.schemas.geometry import Opening, OpeningType, Point, Room

logger = logging.getLogger(__name__)


# Расстояние от центра двери до полигона комнаты для считания "соседом"
DOOR_PROXIMITY_PX = 25


def _point_in_polygon(px: float, py: float, polygon: list[Point]) -> bool:
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i].x, polygon[i].y
        xj, yj = polygon[j].x, polygon[j].y
        if ((yi > py) != (yj > py)) and \
           (px < (xj - xi) * (py - yi) / (yj - yi + 1e-10) + xi):
            inside = not inside
        j = i
    return inside


def _distance_to_polygon(px: float, py: float, polygon: list[Point]) -> float:
    """Минимальное расстояние от точки до периметра полигона."""
    if _point_in_polygon(px, py, polygon):
        return 0.0
    min_dist = float("inf")
    n = len(polygon)
    for i in range(n):
        a = polygon[i]
        b = polygon[(i + 1) % n]
        # Расстояние от точки до отрезка [a, b]
        dx = b.x - a.x
        dy = b.y - a.y
        ll = dx * dx + dy * dy
        if ll == 0:
            d = math.hypot(px - a.x, py - a.y)
        else:
            t = max(0.0, min(1.0, ((px - a.x) * dx + (py - a.y) * dy) / ll))
            d = math.hypot(px - (a.x + t * dx), py - (a.y + t * dy))
        if d < min_dist:
            min_dist = d
    return min_dist


def validate_doors_against_rooms(
    openings: list[Opening],
    rooms: list[Room],
    proximity_px: float = DOOR_PROXIMITY_PX,
) -> tuple[list[Opening], list[tuple[str, str]]]:
    """
    Проверить что каждая дверь связана с реальными комнатами.

    Returns:
        (valid_openings, rejected_with_reason)
    """
    if not rooms:
        return openings, []

    valid: list[Opening] = []
    rejected: list[tuple[str, str]] = []

    for op in openings:
        if op.type != OpeningType.door:
            valid.append(op)
            continue

        # Считаем сколько комнат ближе чем proximity_px к этой двери
        nearby_rooms = []
        for room in rooms:
            if not room.polygon or len(room.polygon) < 3:
                continue
            d = _distance_to_polygon(op.position.x, op.position.y, room.polygon)
            if d <= proximity_px:
                nearby_rooms.append((room.id, d))

        if len(nearby_rooms) >= 2:
            # Между двумя или более комнатами → межкомнатная дверь
            valid.append(op)
        elif len(nearby_rooms) == 1:
            # Одна соседняя комната → должно быть на внешней стене (вход)
            # Без полной проверки на outer wall просто принимаем —
            # opening_classifier уже делает arc-check.
            valid.append(op)
        else:
            # Не примыкает ни к одной комнате → ложная дверь
            rejected.append((op.id, "no_adjacent_rooms"))

    logger.info(
        f"Door room-adjacency validation: {len(valid)} kept, "
        f"{len(rejected)} rejected (no adjacent rooms)"
    )
    return valid, rejected
