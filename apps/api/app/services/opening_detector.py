"""
Opening Detector — находит РАЗРЫВЫ в детектированных стенах.

ЭТО КЛЮЧЕВОЙ МОДУЛЬ нового pipeline.

Старый door_detector использовал HoughCircles на ВСЁМ изображении → ловил
арки от унитаза, плиты, раковины → 64 ложных двери.

Новый подход:
  1. Идём вдоль каждой найденной wall-векторной линии
  2. Сэмплируем точки вдоль линии каждые 1px
  3. Проверяем, есть ли в этой точке ПИКСЕЛЬ стены (в исходной wall_mask, БЕЗ закрытия)
  4. Найденные разрывы (run-of-zeros) длиной 0.4-1.5м = opening candidates
  5. Каждый opening привязан к конкретной стене (wall_id) — это база
     для последующей классификации в door/window

Дверные арки/окна не существуют сами по себе — они существуют только КАК
проёмы в стенах. Это правило архитектуры жёсткое.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

import cv2
import numpy as np

from app.schemas.geometry import Opening, OpeningType, Point, SwingDirection, Wall

logger = logging.getLogger(__name__)


# ─── Параметры ───────────────────────────────────────────────────────────────

# Размер ядра для "толстой" версии стены при поиске разрывов
WALL_PROBE_THICKNESS = 5

# Шаг сэмплирования вдоль стены (px)
SAMPLE_STEP = 1

# Минимальная и максимальная ширина проёма (в долях px_per_meter)
MIN_OPENING_WIDTH_M = 0.4
MAX_OPENING_WIDTH_M = 1.8

# Если масштаб не известен — используем px напрямую
DEFAULT_MIN_OPENING_PX = 18
DEFAULT_MAX_OPENING_PX = 90

# Минимальная длина "хвостов" стены вокруг разрыва (защита от концов стен).
# 4px — хватает чтобы отличить gap-в-середине от обрыва на конце,
# но не отбрасывает gap'ы рядом с концами на коротких стенах коридора.
MIN_TAIL_LENGTH_PX = 4


@dataclass
class OpeningCandidate:
    """Сырой кандидат проёма — без классификации в door/window."""
    wall_id: str
    start: Point         # координата начала разрыва на стене
    end: Point           # координата конца
    center: Point
    width_px: float
    width_m: float | None
    confidence: float
    # Дополнительные метаданные для классификации
    perpendicular_x: float = 0.0   # вектор нормали внутрь
    perpendicular_y: float = 0.0


# ─── Главная функция ─────────────────────────────────────────────────────────


def find_openings(
    wall_mask: np.ndarray,
    walls: list[Wall],
    px_per_meter: float | None = None,
) -> list[OpeningCandidate]:
    """
    Найти все проёмы в детектированных стенах.

    Args:
        wall_mask: исходная маска стен (с разрывами на дверях/окнах)
        walls: список найденных стен
        px_per_meter: масштаб (для конверсии px↔m)

    Returns:
        Список OpeningCandidate. Каждый привязан к конкретной стене.
    """
    if not walls:
        return []

    # Размеры проёма в px
    if px_per_meter and px_per_meter > 0:
        min_w_px = MIN_OPENING_WIDTH_M * px_per_meter
        max_w_px = MAX_OPENING_WIDTH_M * px_per_meter
    else:
        min_w_px = DEFAULT_MIN_OPENING_PX
        max_w_px = DEFAULT_MAX_OPENING_PX

    h_img, w_img = wall_mask.shape

    # "Толстая" маска стен — компенсируем погрешность в детектируемых линиях.
    # Для проверки "есть ли стена в этой точке" используем dilated версию.
    # Но для поиска РАЗРЫВОВ — оригинал.
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    wall_dilated = cv2.dilate(wall_mask, kernel, iterations=1)

    candidates: list[OpeningCandidate] = []

    for wall in walls:
        wall_candidates = _find_gaps_on_wall(
            wall, wall_mask, wall_dilated,
            min_w_px=min_w_px, max_w_px=max_w_px,
            img_w=w_img, img_h=h_img,
            px_per_meter=px_per_meter,
        )
        candidates.extend(wall_candidates)

    logger.info(
        f"Opening candidates: {len(candidates)} найдено "
        f"({min_w_px:.0f}–{max_w_px:.0f}px размер) "
        f"на {len(walls)} стенах"
    )

    return candidates


# ─── Поиск разрывов вдоль одной стены ────────────────────────────────────────


def _find_gaps_on_wall(
    wall: Wall,
    wall_mask: np.ndarray,
    wall_dilated: np.ndarray,
    min_w_px: float,
    max_w_px: float,
    img_w: int,
    img_h: int,
    px_per_meter: float | None,
) -> list[OpeningCandidate]:
    """Найти разрывы вдоль одной стены."""
    sx, sy = wall.start.x, wall.start.y
    ex, ey = wall.end.x, wall.end.y
    dx = ex - sx
    dy = ey - sy
    length = math.hypot(dx, dy)
    if length < 2 * MIN_TAIL_LENGTH_PX + min_w_px:
        return []

    ux, uy = dx / length, dy / length
    # Перпендикуляр (две стороны)
    nx, ny = -uy, ux

    # Сэмплируем точки вдоль линии — ишем "off" пиксели
    n_samples = int(length / SAMPLE_STEP)
    if n_samples < 4:
        return []

    # Для каждой точки: считается ли она "стеной"?
    # Проверяем dilated mask в небольшой окрестности (по перпендикуляру)
    on_wall: list[bool] = []
    for i in range(n_samples + 1):
        t = i / n_samples
        px = sx + t * dx
        py = sy + t * dy

        # Проверяем 3 точки по перпендикуляру: центр + ±2px
        is_on = False
        for offset in (-WALL_PROBE_THICKNESS // 2, 0, WALL_PROBE_THICKNESS // 2):
            qx = int(round(px + nx * offset))
            qy = int(round(py + ny * offset))
            if 0 <= qx < img_w and 0 <= qy < img_h:
                if wall_dilated[qy, qx] > 0:
                    is_on = True
                    break
        on_wall.append(is_on)

    # Находим runs of False (gaps)
    candidates: list[OpeningCandidate] = []
    in_gap = False
    gap_start_i = 0
    head_tail_samples = max(int(MIN_TAIL_LENGTH_PX / SAMPLE_STEP), 2)

    for i, on in enumerate(on_wall):
        if not on:
            if not in_gap:
                in_gap = True
                gap_start_i = i
        else:
            if in_gap:
                in_gap = False
                gap_end_i = i
                gap_len_px = (gap_end_i - gap_start_i) * SAMPLE_STEP

                # Проверки
                if gap_len_px < min_w_px or gap_len_px > max_w_px:
                    continue
                # Должны быть "хвосты" с обеих сторон
                if gap_start_i < head_tail_samples:
                    continue
                if gap_end_i > len(on_wall) - head_tail_samples:
                    continue

                # Координаты
                t_start = gap_start_i / n_samples
                t_end = gap_end_i / n_samples
                gx_s, gy_s = sx + t_start * dx, sy + t_start * dy
                gx_e, gy_e = sx + t_end * dx, sy + t_end * dy
                cx, cy = (gx_s + gx_e) / 2, (gy_s + gy_e) / 2

                width_m = gap_len_px / px_per_meter if px_per_meter else None
                # Confidence: ширина внутри нормального окна → высокая
                ideal_width_px = (min_w_px + max_w_px) / 2
                width_dist = abs(gap_len_px - ideal_width_px) / (ideal_width_px + 1e-6)
                confidence = max(0.4, 1.0 - width_dist)

                candidates.append(OpeningCandidate(
                    wall_id=wall.id,
                    start=Point(x=round(gx_s, 1), y=round(gy_s, 1)),
                    end=Point(x=round(gx_e, 1), y=round(gy_e, 1)),
                    center=Point(x=round(cx, 1), y=round(cy, 1)),
                    width_px=round(gap_len_px, 1),
                    width_m=round(width_m, 2) if width_m else None,
                    confidence=round(confidence, 3),
                    perpendicular_x=nx,
                    perpendicular_y=ny,
                ))

    return candidates


# ─── Конверсия в Opening ─────────────────────────────────────────────────────


def candidate_to_opening(
    candidate: OpeningCandidate,
    opening_id: str,
    opening_type: OpeningType,
    swing: SwingDirection = SwingDirection.unknown,
) -> Opening:
    """Превратить candidate в финальный Opening после классификации."""
    return Opening(
        id=opening_id,
        type=opening_type,
        wall_id=candidate.wall_id,
        position=candidate.center,
        width_px=candidate.width_px,
        width_m=candidate.width_m,
        swing_direction=swing,
        clearance_m=0.8 if opening_type == OpeningType.door else 0.5,
        locked=True,
        confidence=candidate.confidence,
    )
