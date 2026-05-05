"""
Детектор окон.

На архитектурных планах окна обозначаются:
- Двойной тонкой линией (параллельные линии) в проёме внешней стены
- Иногда тройной линией (ЖБ-стеклопакет)

Алгоритм:
1. Находим разрывы во внешних стенах
2. В разрывах ищем параллельные тонкие линии (HoughLinesP на инвертированной маске)
3. Пары параллельных линий вблизи внешних стен = окна
4. Определяем ширину и положение окна
"""

from __future__ import annotations

import logging
import math

import cv2
import numpy as np

from app.schemas.geometry import Opening, OpeningType, Point, SwingDirection, Wall, WallType
from app.services.preprocessing import PreprocessedPlan

logger = logging.getLogger(__name__)

WINDOW_LINE_PAIR_DIST_PX = (3, 20)   # расстояние между двумя линиями окна (px)
WINDOW_MIN_LENGTH_PX = 20            # минимальная длина оконного проёма
OUTER_WALL_PROXIMITY_PX = 30         # расстояние от внешней стены для поиска окон
ANGLE_TOLERANCE = 5                   # допуск для параллельности линий (градусы)


def _get_outer_wall_segments(walls: list[Wall]) -> list[Wall]:
    """Вернуть только внешние стены."""
    return [w for w in walls if w.type == WallType.outer]


def _detect_thin_lines(gray: np.ndarray, walls_mask: np.ndarray) -> list[tuple]:
    """
    Найти тонкие линии, которых нет в маске стен.
    Это кандидаты на оконные линии.
    """
    # Получаем тонкие линии (обратная маска стен)
    _, thin_binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    # Убираем толстые стены
    walls_dilated = cv2.dilate(walls_mask, np.ones((3, 3), np.uint8), iterations=2)
    thin_only = cv2.bitwise_and(thin_binary, cv2.bitwise_not(walls_dilated))

    lines = cv2.HoughLinesP(
        thin_only,
        rho=1,
        theta=np.pi / 180,
        threshold=15,
        minLineLength=WINDOW_MIN_LENGTH_PX,
        maxLineGap=5,
    )
    if lines is None:
        return []
    return [tuple(line[0]) for line in lines]


def _lines_are_parallel(
    l1: tuple, l2: tuple, angle_tol: float = ANGLE_TOLERANCE
) -> bool:
    """Проверить, параллельны ли два отрезка."""
    x1a, y1a, x2a, y2a = l1
    x1b, y1b, x2b, y2b = l2
    angle_a = math.degrees(math.atan2(y2a - y1a, x2a - x1a)) % 180
    angle_b = math.degrees(math.atan2(y2b - y1b, x2b - x1b)) % 180
    diff = abs(angle_a - angle_b)
    return diff < angle_tol or diff > (180 - angle_tol)


def _perpendicular_distance(l1: tuple, l2: tuple) -> float:
    """Расстояние между параллельными отрезками (перпендикулярное)."""
    x1a, y1a, x2a, y2a = l1
    x1b, y1b, _, _ = l2
    dx = x2a - x1a
    dy = y2a - y1a
    length = math.hypot(dx, dy)
    if length == 0:
        return float("inf")
    return abs(dy * x1b - dx * y1b + x2a * y1a - y2a * x1a) / length


def _is_near_outer_wall(
    cx: float, cy: float, outer_walls: list[Wall], max_dist: float = OUTER_WALL_PROXIMITY_PX
) -> tuple[bool, Wall | None]:
    """Проверить, находится ли точка рядом с внешней стеной."""
    for wall in outer_walls:
        sx, sy = wall.start.x, wall.start.y
        ex, ey = wall.end.x, wall.end.y
        dx, dy = ex - sx, ey - sy
        length_sq = dx * dx + dy * dy
        if length_sq == 0:
            dist = math.hypot(cx - sx, cy - sy)
        else:
            t = max(0.0, min(1.0, ((cx - sx) * dx + (cy - sy) * dy) / length_sq))
            proj_x = sx + t * dx
            proj_y = sy + t * dy
            dist = math.hypot(cx - proj_x, cy - proj_y)
        if dist <= max_dist:
            return True, wall
    return False, None


def detect_windows(
    plan: PreprocessedPlan,
    walls: list[Wall],
    px_per_meter: float | None = None,
) -> tuple[list[Opening], float]:
    """
    Главная функция детектора окон.

    Returns:
        (list[Opening], overall_confidence)
    """
    outer_walls = _get_outer_wall_segments(walls)
    if not outer_walls:
        logger.warning("Нет внешних стен — окна не ищем")
        return [], 0.3

    thin_lines = _detect_thin_lines(plan.gray, plan.walls_mask)
    logger.info(f"Тонких линий найдено: {len(thin_lines)}")

    windows: list[Opening] = []
    used_indices = set()
    window_idx = 0

    for i, l1 in enumerate(thin_lines):
        if i in used_indices:
            continue
        for j, l2 in enumerate(thin_lines):
            if j <= i or j in used_indices:
                continue

            if not _lines_are_parallel(l1, l2):
                continue

            dist = _perpendicular_distance(l1, l2)
            if not (WINDOW_LINE_PAIR_DIST_PX[0] <= dist <= WINDOW_LINE_PAIR_DIST_PX[1]):
                continue

            # Центр окна
            x1a, y1a, x2a, y2a = l1
            x1b, y1b, x2b, y2b = l2
            cx = (x1a + x2a + x1b + x2b) / 4
            cy = (y1a + y2a + y1b + y2b) / 4

            # Проверяем близость к внешней стене
            is_near, nearest_wall = _is_near_outer_wall(cx, cy, outer_walls)
            if not is_near or nearest_wall is None:
                continue

            # Ширина = длина линий
            len1 = math.hypot(x2a - x1a, y2a - y1a)
            len2 = math.hypot(x2b - x1b, y2b - y1b)
            width_px = (len1 + len2) / 2

            width_m: float | None = None
            if px_per_meter and px_per_meter > 0:
                width_m = round(width_px / px_per_meter, 2)

            # Confidence: чем ровнее пара линий, тем выше
            confidence = min(0.9, 0.5 + (1.0 - abs(len1 - len2) / max(len1, len2)) * 0.4)

            window = Opening(
                id=f"window_{window_idx:03d}",
                type=OpeningType.window,
                wall_id=nearest_wall.id,
                position=Point(x=round(cx, 1), y=round(cy, 1)),
                width_px=round(width_px, 1),
                width_m=width_m,
                swing_direction=SwingDirection.unknown,
                clearance_m=0.5,  # не ставить высокую мебель в 0.5м
                locked=True,
                confidence=round(float(confidence), 3),
            )
            windows.append(window)
            used_indices.add(i)
            used_indices.add(j)
            window_idx += 1
            break

    overall_confidence = (
        float(np.mean([w.confidence for w in windows]))
        if windows else 0.3
    )
    logger.info(f"Окна: {len(windows)} найдено, confidence={overall_confidence:.2f}")
    return windows, overall_confidence
