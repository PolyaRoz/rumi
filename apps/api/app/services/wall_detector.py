"""
Детектор стен.

Алгоритм:
1. Применяем HoughLinesP к walls_mask для нахождения прямых отрезков
2. Разделяем горизонтальные/вертикальные/диагональные линии
3. Объединяем близкие коллинеарные сегменты
4. Определяем толщину стен (через distance transform)
5. Определяем тип стены (внешняя/внутренняя) по близости к границе изображения
6. Возвращаем список Wall с confidence
"""

from __future__ import annotations

import logging
import math
from typing import NamedTuple

import cv2
import numpy as np

from app.schemas.geometry import Point, Wall, WallType
from app.services.preprocessing import PreprocessedPlan

logger = logging.getLogger(__name__)

# Параметры
HOUGH_RHO = 1
HOUGH_THETA = np.pi / 180
HOUGH_THRESHOLD = 40          # выше → меньше ложных срабатываний на мебель
HOUGH_MIN_LINE_LEN = 40       # px — минимальная длина (40px ≈ 0.5м при 78px/m)
HOUGH_MAX_LINE_GAP = 10       # px — допустимый разрыв в линии

MERGE_DISTANCE_PX = 12        # расстояние для объединения коллинеарных сегментов
ANGLE_TOLERANCE_DEG = 5       # допуск для считания линий коллинеарными
OUTER_WALL_MARGIN_FRACTION = 0.08  # 8% от края → внешняя стена
MIN_WALL_LENGTH_PX = 35       # короче → не стена (убирает мебельные линии)


class LineSegment(NamedTuple):
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def length(self) -> float:
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)

    @property
    def angle_deg(self) -> float:
        return math.degrees(math.atan2(self.y2 - self.y1, self.x2 - self.x1)) % 180

    @property
    def midpoint(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)

    def is_horizontal(self, tol: float = ANGLE_TOLERANCE_DEG) -> bool:
        a = self.angle_deg
        return a <= tol or a >= (180 - tol)

    def is_vertical(self, tol: float = ANGLE_TOLERANCE_DEG) -> bool:
        a = self.angle_deg
        return abs(a - 90) <= tol


def _detect_raw_lines(walls_mask: np.ndarray) -> list[LineSegment]:
    """HoughLinesP → список отрезков."""
    lines = cv2.HoughLinesP(
        walls_mask,
        rho=HOUGH_RHO,
        theta=HOUGH_THETA,
        threshold=HOUGH_THRESHOLD,
        minLineLength=HOUGH_MIN_LINE_LEN,
        maxLineGap=HOUGH_MAX_LINE_GAP,
    )
    if lines is None:
        return []
    result = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        seg = LineSegment(float(x1), float(y1), float(x2), float(y2))
        if seg.length >= MIN_WALL_LENGTH_PX:
            result.append(seg)
    return result


def _snap_to_orthogonal(seg: LineSegment, tol: float = ANGLE_TOLERANCE_DEG) -> LineSegment:
    """
    Если линия почти горизонтальная или вертикальная — привести к точно ортогональной.
    Это убирает дрожание линий на отсканированных чертежах.
    """
    if seg.is_horizontal(tol):
        y_mid = (seg.y1 + seg.y2) / 2
        return LineSegment(min(seg.x1, seg.x2), y_mid, max(seg.x1, seg.x2), y_mid)
    if seg.is_vertical(tol):
        x_mid = (seg.x1 + seg.x2) / 2
        return LineSegment(x_mid, min(seg.y1, seg.y2), x_mid, max(seg.y1, seg.y2))
    return seg


def _are_collinear(a: LineSegment, b: LineSegment,
                   angle_tol: float = ANGLE_TOLERANCE_DEG,
                   dist_tol: float = MERGE_DISTANCE_PX) -> bool:
    """Проверить, лежат ли два отрезка на одной прямой (коллинеарность)."""
    if abs(a.angle_deg - b.angle_deg) > angle_tol:
        return False
    # Расстояние от центра b до прямой a
    dx = a.x2 - a.x1
    dy = a.y2 - a.y1
    length_a = a.length
    if length_a == 0:
        return False
    # Перпендикулярное расстояние
    perp_dist = abs(dy * b.x1 - dx * b.y1 + a.x2 * a.y1 - a.y2 * a.x1) / length_a
    return perp_dist < dist_tol


def _merge_collinear_segments(segments: list[LineSegment]) -> list[LineSegment]:
    """Объединить коллинеарные отрезки в один длинный."""
    if not segments:
        return []

    merged: list[LineSegment] = []
    used = [False] * len(segments)

    for i, seg_a in enumerate(segments):
        if used[i]:
            continue
        group = [seg_a]
        used[i] = True
        for j, seg_b in enumerate(segments):
            if used[j] or i == j:
                continue
            if _are_collinear(seg_a, seg_b):
                group.append(seg_b)
                used[j] = True

        if len(group) == 1:
            merged.append(group[0])
            continue

        # Собираем все точки группы
        all_x = [s.x1 for s in group] + [s.x2 for s in group]
        all_y = [s.y1 for s in group] + [s.y2 for s in group]

        # Ортогональные группы: растягиваем по главной оси
        if seg_a.is_horizontal():
            y_mean = sum(all_y) / len(all_y)
            merged.append(LineSegment(min(all_x), y_mean, max(all_x), y_mean))
        elif seg_a.is_vertical():
            x_mean = sum(all_x) / len(all_x)
            merged.append(LineSegment(x_mean, min(all_y), x_mean, max(all_y)))
        else:
            # Диагональ — берём крайние точки
            # Используем PCA для нахождения главной оси
            pts = np.array(list(zip(all_x, all_y)), dtype=np.float32)
            _, _, vt = np.linalg.svd(pts - pts.mean(axis=0))
            direction = vt[0]
            projections = (pts - pts.mean(axis=0)) @ direction
            i_min, i_max = projections.argmin(), projections.argmax()
            merged.append(LineSegment(*pts[i_min], *pts[i_max]))

    return merged


def _estimate_wall_thickness(walls_mask: np.ndarray, seg: LineSegment) -> float:
    """
    Оценить толщину стены через distance transform:
    для каждого пикселя вдоль линии взять максимальное расстояние до фона.
    """
    dist = cv2.distanceTransform(walls_mask, cv2.DIST_L2, 5)
    h, w = walls_mask.shape

    samples = 10
    thicknesses = []
    for t in np.linspace(0, 1, samples):
        px = int(seg.x1 + t * (seg.x2 - seg.x1))
        py = int(seg.y1 + t * (seg.y2 - seg.y1))
        if 0 <= py < h and 0 <= px < w:
            thicknesses.append(float(dist[py, px]))

    if not thicknesses:
        return 8.0
    return float(np.median(thicknesses)) * 2  # радиус → диаметр


def _classify_wall_type(seg: LineSegment, img_w: int, img_h: int) -> WallType:
    """
    Внешняя стена — если находится в OUTER_WALL_MARGIN_FRACTION от края изображения.
    Остальные — внутренние.
    """
    margin_x = img_w * OUTER_WALL_MARGIN_FRACTION
    margin_y = img_h * OUTER_WALL_MARGIN_FRACTION

    coords_x = [seg.x1, seg.x2]
    coords_y = [seg.y1, seg.y2]

    near_left = all(x <= margin_x for x in coords_x)
    near_right = all(x >= img_w - margin_x for x in coords_x)
    near_top = all(y <= margin_y for y in coords_y)
    near_bottom = all(y >= img_h - margin_y for y in coords_y)

    if near_left or near_right or near_top or near_bottom:
        return WallType.outer
    return WallType.inner


def _compute_wall_confidence(seg: LineSegment, walls_mask: np.ndarray) -> float:
    """
    Confidence = доля пикселей вдоль линии, попавших в walls_mask.
    """
    h, w = walls_mask.shape
    samples = max(int(seg.length / 3), 5)
    hits = 0
    total = 0
    for t in np.linspace(0, 1, samples):
        px = int(seg.x1 + t * (seg.x2 - seg.x1))
        py = int(seg.y1 + t * (seg.y2 - seg.y1))
        if 0 <= py < h and 0 <= px < w:
            total += 1
            if walls_mask[py, px] > 0:
                hits += 1
    return hits / total if total > 0 else 0.0


def detect_walls(plan: PreprocessedPlan) -> tuple[list[Wall], float]:
    """
    Главная функция детектора стен.

    Returns:
        (list[Wall], overall_confidence)
    """
    h, w = plan.walls_mask.shape

    # 1. Hough
    raw_lines = _detect_raw_lines(plan.walls_mask)
    logger.info(f"HoughLinesP: {len(raw_lines)} линий")

    if not raw_lines:
        logger.warning("Стены не найдены")
        return [], 0.0

    # 2. Привести к ортогонали
    snapped = [_snap_to_orthogonal(seg) for seg in raw_lines]

    # 3. Объединить коллинеарные
    merged = _merge_collinear_segments(snapped)
    logger.info(f"После merge: {len(merged)} стен")

    # 4. Построить Wall объекты
    walls: list[Wall] = []
    confidences: list[float] = []

    for i, seg in enumerate(merged):
        if seg.length < MIN_WALL_LENGTH_PX:
            continue

        thickness = _estimate_wall_thickness(plan.walls_mask, seg)
        wall_type = _classify_wall_type(seg, w, h)
        confidence = _compute_wall_confidence(seg, plan.walls_mask)

        wall = Wall(
            id=f"wall_{i:03d}",
            type=wall_type,
            start=Point(x=round(seg.x1, 1), y=round(seg.y1, 1)),
            end=Point(x=round(seg.x2, 1), y=round(seg.y2, 1)),
            thickness_px=round(thickness, 1),
            locked=True,
            confidence=round(confidence, 3),
        )
        walls.append(wall)
        confidences.append(confidence)

    overall_confidence = float(np.mean(confidences)) if confidences else 0.0
    logger.info(
        f"Стены: {len(walls)} объектов, "
        f"confidence={overall_confidence:.2f}, "
        f"outer={sum(1 for w in walls if w.type == WallType.outer)}, "
        f"inner={sum(1 for w in walls if w.type == WallType.inner)}"
    )

    return walls, overall_confidence
