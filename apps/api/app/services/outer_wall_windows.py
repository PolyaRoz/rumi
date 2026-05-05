"""
Outer Wall Window Detector — окна на ВНЕШНИХ стенах.

Логика отличается от dверей:
- Двери = разрывы в стене, дополненные дугой открывания
- Окна = графические символы (прямоугольник со штрихами стеклопакета)
  накладываются на наружную стену, что даёт low-density участки
  при горизонтальной/вертикальной проекции стены.

Алгоритм:
1. Для каждой outer wall сегмента создать "strip" — узкую полосу
   перпендикулярно стене толщиной ~25px (захватывает всю толщину стены
   плюс символы окон).
2. Считаем плотность темных пикселей по столбцам (для горизонтальной
   стены) или строкам (для вертикальной).
3. Низкоплотностные runs длиной 40-120px = окно или перегородка между
   окнами.
4. Объединяем соседние runs (gap < 30px) — двухстворчатое окно
   засчитывается как одно.
5. Возвращаем список окон в координатах изображения.
"""

from __future__ import annotations

import logging
import math

import cv2
import numpy as np

from app.schemas.geometry import Opening, OpeningType, Point, SwingDirection, Wall, WallType

logger = logging.getLogger(__name__)

# Параметры
STRIP_THICKNESS_PX = 25       # толщина strip перпендикулярно стене
LOW_DENSITY_THRESHOLD = 0.30  # column density ниже = пропуск стены
MIN_WINDOW_WIDTH_PX = 35
MAX_WINDOW_WIDTH_PX = 200
MERGE_GAP_PX = 35             # расстояние между low-density runs для merge


def find_windows_on_outer_walls(
    gray: np.ndarray,
    walls: list[Wall],
    px_per_meter: float | None = None,
) -> list[Opening]:
    """
    Найти окна на внешних стенах через анализ плотности.

    Args:
        gray: greyscale исходного плана (с символами окон)
        walls: список стен из wall_graph
        px_per_meter: масштаб (для конверсии px↔m)
    """
    h_img, w_img = gray.shape

    # Бинаризация — находим все темные пиксели (стены + символы окон)
    _, binary = cv2.threshold(gray, 100, 255, cv2.THRESH_BINARY_INV)

    outer_walls = [w for w in walls if w.type == WallType.outer]
    if not outer_walls:
        logger.info("Outer wall window detector: нет outer walls")
        return []

    windows: list[Opening] = []
    win_idx = 0

    for wall in outer_walls:
        wall_windows = _find_windows_on_one_wall(
            wall, binary, h_img, w_img, px_per_meter,
        )
        for w_open in wall_windows:
            w_open.id = f"window_{win_idx:03d}"
            win_idx += 1
            windows.append(w_open)

    logger.info(
        f"Outer wall window detector: {len(windows)} окон на "
        f"{len(outer_walls)} внешних стенах"
    )
    return windows


def _find_windows_on_one_wall(
    wall: Wall,
    binary: np.ndarray,
    h_img: int,
    w_img: int,
    px_per_meter: float | None,
) -> list[Opening]:
    """Найти окна на одной outer wall через column density analysis."""
    sx, sy = wall.start.x, wall.start.y
    ex, ey = wall.end.x, wall.end.y
    dx, dy = ex - sx, ey - sy
    length = math.hypot(dx, dy)
    if length < MIN_WINDOW_WIDTH_PX * 1.5:
        return []  # короткая стена — окон не бывает

    # Угол стены
    angle = math.atan2(dy, dx)

    # Собираем strip перпендикулярно стене
    # Используем cv2.warpAffine чтобы повернуть фрагмент изображения
    # так чтобы стена стала горизонтальной → можно делать column projection.
    cx_wall = (sx + ex) / 2
    cy_wall = (sy + ey) / 2

    M = cv2.getRotationMatrix2D((cx_wall, cy_wall), math.degrees(angle), 1.0)
    rotated = cv2.warpAffine(binary, M, (w_img, h_img))

    # Выбираем strip: y в окрестности cy_wall, x в [sx_rotated - half_length .. sx_rotated + half_length]
    half_thickness = STRIP_THICKNESS_PX // 2
    y_top = max(0, int(cy_wall - half_thickness))
    y_bot = min(h_img, int(cy_wall + half_thickness))

    half_len = int(length / 2)
    x_left = max(0, int(cx_wall - half_len))
    x_right = min(w_img, int(cx_wall + half_len))

    strip = rotated[y_top:y_bot, x_left:x_right]
    if strip.size == 0:
        return []

    # Column density
    col_density = np.sum(strip > 0, axis=0) / max(strip.shape[0], 1)

    # Найти low-density runs
    runs = _find_low_density_runs(col_density)
    if not runs:
        return []

    # Объединить соседние
    merged = _merge_close_runs(runs, MERGE_GAP_PX)

    # Конвертировать обратно в координаты изображения
    openings: list[Opening] = []
    for run_start, run_end in merged:
        run_width = run_end - run_start
        if not (MIN_WINDOW_WIDTH_PX <= run_width <= MAX_WINDOW_WIDTH_PX):
            continue

        # Центр в координатах rotated
        local_cx_rotated = x_left + (run_start + run_end) / 2
        local_cy_rotated = cy_wall

        # Обратная трансформация: rotated → original
        Minv = cv2.invertAffineTransform(M)
        # Apply: [x_orig, y_orig, 1] = Minv @ [local_cx_rotated, local_cy_rotated, 1]
        gx = (
            Minv[0, 0] * local_cx_rotated
            + Minv[0, 1] * local_cy_rotated
            + Minv[0, 2]
        )
        gy = (
            Minv[1, 0] * local_cx_rotated
            + Minv[1, 1] * local_cy_rotated
            + Minv[1, 2]
        )

        width_m = run_width / px_per_meter if px_per_meter else None
        confidence = _compute_window_confidence(run_width, col_density, run_start, run_end)

        opening = Opening(
            id="window_temp",
            type=OpeningType.window,
            wall_id=wall.id,
            position=Point(x=round(gx, 1), y=round(gy, 1)),
            width_px=round(float(run_width), 1),
            width_m=round(width_m, 2) if width_m else None,
            swing_direction=SwingDirection.unknown,
            clearance_m=0.5,
            locked=True,
            confidence=round(confidence, 3),
        )
        openings.append(opening)

    return openings


def _find_low_density_runs(densities: np.ndarray) -> list[tuple[int, int]]:
    """Runs of consecutive columns where density <= LOW_DENSITY_THRESHOLD."""
    runs: list[tuple[int, int]] = []
    in_low = False
    start = 0
    for i, d in enumerate(densities):
        if d <= LOW_DENSITY_THRESHOLD and not in_low:
            in_low = True
            start = i
        elif d > LOW_DENSITY_THRESHOLD and in_low:
            in_low = False
            runs.append((start, i))
    if in_low:
        runs.append((start, len(densities)))
    return runs


def _merge_close_runs(
    runs: list[tuple[int, int]], max_gap: int,
) -> list[tuple[int, int]]:
    """Объединить runs с зазором ≤ max_gap (двухстворчатое окно)."""
    if not runs:
        return []
    merged = [runs[0]]
    for start, end in runs[1:]:
        last_start, last_end = merged[-1]
        if start - last_end <= max_gap:
            merged[-1] = (last_start, end)
        else:
            merged.append((start, end))
    return merged


def _compute_window_confidence(
    width: int, densities: np.ndarray, start: int, end: int
) -> float:
    """Confidence: чем "чище" падение плотности → выше."""
    # Plain confidence: width в идеальном диапазоне → выше.
    ideal = (60 + 120) / 2  # ~90px = ~1.5m
    width_score = max(0.0, 1.0 - abs(width - ideal) / ideal)
    return max(0.4, min(0.95, 0.5 + width_score * 0.4))
