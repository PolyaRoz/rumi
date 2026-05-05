"""
Structural Wall Mask — извлекает ТОЛЬКО структурные стены, отфильтровывая:
- цифры площадей и текст,
- дуги дверей,
- сантехнические/кухонные иконки,
- тонкие декоративные линии.

В предыдущей версии preprocessing.py wall_mask содержала всё подряд,
и door_detector ловил арки от унитазов как двери. Здесь делаем агрессивно.

Алгоритм:
1. Предобработка → бинарная маска
2. Connected component analysis → измеряем aspect ratio, solidity, area
3. Удаляем компоненты, похожие на текст (мелкие, низкая solidity, особый aspect)
4. Удаляем компоненты, похожие на арки (высокая кривизна, средний размер)
5. Удаляем санитарные/кухонные иконки (компактные округлые формы)
6. Оставшееся = структурные стены (длинные, тонкие, прямые)
"""

from __future__ import annotations

import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)


# ─── Параметры фильтрации ────────────────────────────────────────────────────

# Минимальная "длинная" сторона компонента, чтобы считать его стеной (px)
MIN_WALL_BBOX_LONG_SIDE = 40

# Максимальная "толщина" компонента стены (px) — стены тонкие, иконки толстые
MAX_WALL_THICKNESS = 22

# Aspect ratio (long_side / short_side) — стены вытянутые
MIN_WALL_ASPECT = 3.0

# Solidity (area / convexHullArea): стены прямые → высокая solidity
# Дуги дверей и окружности → низкая
MIN_WALL_SOLIDITY = 0.55

# Площадь компонента: стены большие
MIN_WALL_AREA = 80

# Иконки и символы обычно компактные (≤ this size)
ICON_MAX_BBOX_LONG = 35


def extract_wall_mask(binary: np.ndarray) -> tuple[np.ndarray, dict]:
    """
    Из бинаризованного изображения (стены = 255, фон = 0) извлекает
    маску ТОЛЬКО структурных стен.

    Returns:
        (wall_mask, stats_dict)
        stats_dict содержит счётчики отфильтрованного для дебага.
    """
    h, w = binary.shape
    img_area = h * w

    # 1. Закрываем мелкие разрывы (но не дверные — это потом)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=1)

    # 2. Connected components с метаданными
    nb_components, labels, stats, _ = cv2.connectedComponentsWithStats(
        closed, connectivity=8
    )

    wall_mask = np.zeros_like(closed)
    rejected: dict[str, int] = {
        "too_small": 0,
        "too_large": 0,
        "icon_size": 0,
        "low_aspect": 0,
        "low_solidity": 0,
        "thick_blob": 0,
    }
    accepted = 0

    # Порог: "большой" компонент = главная структура плана (≥ 0.3% площади).
    # Для них пропускаем aspect-фильтр (замкнутый прямоугольник стен имеет aspect ~1).
    LARGE_COMPONENT_AREA = img_area * 0.003

    for i in range(1, nb_components):
        x, y, cw, ch, area = stats[i]
        long_side = max(cw, ch)
        short_side = max(min(cw, ch), 1)
        aspect = long_side / short_side
        is_large = area > LARGE_COMPONENT_AREA

        # 1. Совсем маленькое — мусор/шум
        if area < MIN_WALL_AREA:
            rejected["too_small"] += 1
            continue

        # 2. Огромное — фон
        if area > img_area * 0.5:
            rejected["too_large"] += 1
            continue

        # 3. КРУПНЫЕ структурные компоненты — главная архитектура плана.
        #    Контур замкнутой комнаты выглядит как "рамка": bbox большой,
        #    но фактическая площадь занятых пикселей маленькая (low solidity).
        #    Плотный блок (мебель, штриховка пола) имеет solidity ≈ 1.
        if is_large:
            component_mask = (labels == i).astype(np.uint8) * 255
            cnts, _ = cv2.findContours(component_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
            if not cnts:
                continue
            big_cnt = max(cnts, key=cv2.contourArea)
            hull_area = cv2.contourArea(cv2.convexHull(big_cnt))
            # Solidity по area/hull: для рамки = низкая, для блока = высокая
            density = area / max(hull_area, 1)
            if density > 0.85 and area > LARGE_COMPONENT_AREA * 5:
                # Плотный большой блок — мебель/штриховка
                rejected["thick_blob"] += 1
                continue
            wall_mask[labels == i] = 255
            accepted += 1
            continue

        # 4. Компактная иконка (унитаз, плита, раковина) — отбрасываем
        if long_side <= ICON_MAX_BBOX_LONG and aspect < 2.5:
            rejected["icon_size"] += 1
            continue

        # 5. Малый компонент с низким aspect — не стена
        if aspect < MIN_WALL_ASPECT:
            rejected["low_aspect"] += 1
            continue

        # 6. Слишком толстая короткая сторона = блок мебели, не стена
        if min(cw, ch) > MAX_WALL_THICKNESS:
            rejected["thick_blob"] += 1
            continue

        # 7. Solidity-фильтр (отделить дуги от прямых отрезков)
        component_mask = (labels == i).astype(np.uint8) * 255
        contours, _ = cv2.findContours(component_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if not contours:
            continue
        cnt = max(contours, key=cv2.contourArea)
        cnt_area = cv2.contourArea(cnt)
        if cnt_area > 0:
            hull_area = cv2.contourArea(cv2.convexHull(cnt))
            solidity = cnt_area / hull_area if hull_area > 0 else 0
            if solidity < MIN_WALL_SOLIDITY:
                rejected["low_solidity"] += 1
                continue

        wall_mask[labels == i] = 255
        accepted += 1

    logger.info(
        f"Wall mask: accepted={accepted}, "
        f"rejected={rejected} "
        f"(коэф. фильтрации: {sum(rejected.values())} / {nb_components - 1})"
    )

    # Финальное morphological closing — чтобы соединить близкие участки одной стены
    final_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    wall_mask = cv2.morphologyEx(wall_mask, cv2.MORPH_CLOSE, final_kernel, iterations=1)

    return wall_mask, {"accepted": accepted, **rejected}
