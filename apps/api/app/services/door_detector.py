"""
Детектор дверей.

На архитектурных планах двери обозначаются:
- Дугой (четверть окружности), показывающей направление открывания
- Разрывом в стене рядом с дугой

Алгоритм:
1. HoughCircles на preprocessed изображении → находим окружности
2. Берём только четверти окружностей (проверяем, что 75% дуги = фон)
3. Для каждой дуги ищем ближайший разрыв в стене
4. Определяем ширину проёма и направление открывания
"""

from __future__ import annotations

import logging
import math

import cv2
import numpy as np

from app.schemas.geometry import Opening, OpeningType, Point, SwingDirection, Wall
from app.services.preprocessing import PreprocessedPlan

logger = logging.getLogger(__name__)

# Параметры HoughCircles
HOUGH_DP = 1.2           # отношение разрешения аккумулятора к разрешению изображения
HOUGH_MIN_DIST = 20      # минимальное расстояние между центрами окружностей
HOUGH_PARAM1 = 50        # верхний порог Canny
HOUGH_PARAM2 = 25        # порог аккумулятора
MIN_RADIUS = 12          # минимальный радиус двери (px)
MAX_RADIUS = 80          # максимальный радиус двери (px)

MAX_WALL_DIST_PX = 20    # максимальное расстояние от дуги до стены (px)
DOOR_ARC_CHECK_SAMPLES = 16  # количество точек для проверки дуги


def _find_arc_circles(gray: np.ndarray) -> list[tuple[float, float, float]]:
    """
    HoughCircles для поиска дуг дверей.
    Возвращает список (cx, cy, radius).
    """
    # Blur перед Hough обязателен
    blurred = cv2.GaussianBlur(gray, (7, 7), 1.5)
    circles = cv2.HoughCircles(
        blurred,
        cv2.HOUGH_GRADIENT,
        dp=HOUGH_DP,
        minDist=HOUGH_MIN_DIST,
        param1=HOUGH_PARAM1,
        param2=HOUGH_PARAM2,
        minRadius=MIN_RADIUS,
        maxRadius=MAX_RADIUS,
    )
    if circles is None:
        return []
    return [(float(c[0]), float(c[1]), float(c[2])) for c in circles[0]]


def _is_quarter_arc(
    cx: float, cy: float, r: float,
    binary_inv: np.ndarray,   # фон = 255, стены = 0
) -> tuple[bool, float]:
    """
    Проверить, является ли окружность четвертью (дуга двери).

    Стратегия:
    - Проходим по кругу 360 точек
    - Считаем сколько из них попадают на фон (background)
    - Дуга двери: ~25% окружности = линия (на стене), ~75% = фон
    Возвращает (is_arc, arc_fraction_on_background)
    """
    h, w = binary_inv.shape
    background_hits = 0
    total = DOOR_ARC_CHECK_SAMPLES * 4  # полный круг

    for i in range(total):
        angle = 2 * math.pi * i / total
        px = int(cx + r * math.cos(angle))
        py = int(cy + r * math.sin(angle))
        if 0 <= px < w and 0 <= py < h:
            if binary_inv[py, px] > 128:
                background_hits += 1

    fraction_bg = background_hits / total
    # Дуга: 75% ± 15% точек на фоне (остальные — на стене)
    is_arc = 0.60 <= fraction_bg <= 0.90
    return is_arc, fraction_bg


def _find_nearest_wall(
    cx: float, cy: float, walls: list[Wall], max_dist: float = MAX_WALL_DIST_PX
) -> Wall | None:
    """Найти ближайшую стену к центру дуги."""
    best_wall = None
    best_dist = float("inf")

    for wall in walls:
        # Расстояние от точки до отрезка
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

        if dist < best_dist:
            best_dist = dist
            best_wall = wall

    return best_wall if best_dist <= max_dist else None


def _estimate_door_width(r: float, px_per_meter: float | None) -> tuple[float, float | None]:
    """
    Ширина дверного проёма ≈ радиус дуги.
    Возвращает (width_px, width_m | None).
    """
    width_px = r
    width_m: float | None = None
    if px_per_meter and px_per_meter > 0:
        width_m = round(width_px / px_per_meter, 2)
    return width_px, width_m


def _infer_swing_direction(
    cx: float, cy: float, r: float,
    binary_inv: np.ndarray
) -> SwingDirection:
    """
    Определить направление открывания двери.

    Смотрим в какой из 4 квадрантов от центра окружности
    находится наибольшая плотность фоновых пикселей дуги.
    """
    h, w = binary_inv.shape
    quadrant_hits = [0, 0, 0, 0]  # Q1(+x,+y), Q2(-x,+y), Q3(-x,-y), Q4(+x,-y)

    samples = DOOR_ARC_CHECK_SAMPLES
    for i in range(samples * 4):
        angle = 2 * math.pi * i / (samples * 4)
        px = int(cx + r * math.cos(angle))
        py = int(cy + r * math.sin(angle))
        if 0 <= px < w and 0 <= py < h and binary_inv[py, px] > 128:
            dx = math.cos(angle)
            dy = math.sin(angle)
            if dx >= 0 and dy >= 0:
                quadrant_hits[0] += 1
            elif dx < 0 and dy >= 0:
                quadrant_hits[1] += 1
            elif dx < 0 and dy < 0:
                quadrant_hits[2] += 1
            else:
                quadrant_hits[3] += 1

    dominant = quadrant_hits.index(max(quadrant_hits))
    directions = [
        SwingDirection.right,
        SwingDirection.left,
        SwingDirection.inward,
        SwingDirection.outward,
    ]
    return directions[dominant]


def detect_doors(
    plan: PreprocessedPlan,
    walls: list[Wall],
    px_per_meter: float | None = None,
) -> tuple[list[Opening], float]:
    """
    Главная функция детектора дверей.

    Returns:
        (list[Opening], overall_confidence)
    """
    # binary_inv: фон = 255, стены = 0 (для проверки дуги)
    binary_inv = cv2.bitwise_not(plan.binary)

    circles = _find_arc_circles(plan.gray)
    logger.info(f"HoughCircles: {len(circles)} кандидатов")

    doors: list[Opening] = []
    confidences: list[float] = []

    for i, (cx, cy, r) in enumerate(circles):
        is_arc, bg_fraction = _is_quarter_arc(cx, cy, r, binary_inv)
        if not is_arc:
            continue

        nearest_wall = _find_nearest_wall(cx, cy, walls)
        if nearest_wall is None:
            # Дуга без стены — возможно окружность на плане мебели
            continue

        width_px, width_m = _estimate_door_width(r, px_per_meter)
        swing = _infer_swing_direction(cx, cy, r, binary_inv)

        # Confidence: чем ближе bg_fraction к 0.75, тем лучше
        confidence = 1.0 - abs(bg_fraction - 0.75) * 4
        confidence = max(0.1, min(1.0, confidence))

        door = Opening(
            id=f"door_{i:03d}",
            type=OpeningType.door,
            wall_id=nearest_wall.id,
            position=Point(x=round(cx, 1), y=round(cy, 1)),
            width_px=round(width_px, 1),
            width_m=width_m,
            swing_direction=swing,
            clearance_m=0.8,
            locked=True,
            confidence=round(float(confidence), 3),
        )
        doors.append(door)
        confidences.append(confidence)

    overall_confidence = float(np.mean(confidences)) if confidences else 0.5
    logger.info(f"Двери: {len(doors)} найдено, confidence={overall_confidence:.2f}")

    return doors, overall_confidence
