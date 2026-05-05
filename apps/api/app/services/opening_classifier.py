"""
Opening Classifier — классифицирует найденные OpeningCandidate
в door | window | unknown.

ВАЖНО: на вход поступают ТОЛЬКО валидные проёмы (gaps в стенах из
opening_detector). Этот модуль НЕ ищет арки/линии по всему изображению.

Классификация:
- DOOR: есть дуга (HoughCircles) рядом с проёмом — внутри радиуса от центра.
        Дуга должна быть "четвертью" окружности (75% точек на фоне).
- WINDOW: проём на ВНЕШНЕЙ стене + наличие тонких параллельных линий
          в зоне проёма (паттерн стеклопакета).
- UNKNOWN: проём найден, но classifier не уверен.

Это решает проблему "64 двери" — раньше HoughCircles ловил всё подряд,
теперь дуги проверяются ТОЛЬКО рядом с уже найденными проёмами.
"""

from __future__ import annotations

import logging
import math

import cv2
import numpy as np

from app.schemas.geometry import Opening, OpeningType, SwingDirection, Wall, WallType
from app.services.opening_detector import OpeningCandidate, candidate_to_opening

logger = logging.getLogger(__name__)


# ─── Параметры ───────────────────────────────────────────────────────────────

# Радиус поиска дуги вокруг центра проёма (в долях ширины проёма)
ARC_SEARCH_RADIUS_FACTOR = 1.4

# Параметры HoughCircles в локальном окне.
# 25 — строже чем 18, отсекает шумные окружности от санитарной мебели.
LOCAL_HOUGH_PARAM2 = 25

# Дуга = четверть круга → 65-85% точек на фоне.
# Раньше было 0.55-0.92 — ловило почти-полные круги от унитаза/плиты.
ARC_BG_FRACTION_RANGE = (0.62, 0.88)


def classify_openings(
    candidates: list[OpeningCandidate],
    walls: list[Wall],
    gray: np.ndarray,
    binary: np.ndarray,
) -> list[Opening]:
    """
    Превратить opening candidates в door/window.

    СТРОГИЕ ПРАВИЛА (как требует ТЗ):
    - Door: должен быть И gap в стене (есть), И дуга открывания (HoughCircles),
      И характерная форма двери (полотно — линия перпендикулярная стене).
      Без дуги нельзя быть дверью — gap может оказаться чем угодно.
    - Window: gap на ВНЕШНЕЙ стене БЕЗ дуги (с window pattern или без).
    - Все candidate без дуги на ВНУТРЕННЕЙ стене → отбрасываем как
      "потенциальные арки/проёмы" (могут быть user-confirmed позже,
      но автоматически не считаем дверью).
    """
    if not candidates:
        return []

    walls_by_id = {w.id: w for w in walls}
    binary_inv = cv2.bitwise_not(binary)
    h_img, w_img = gray.shape

    openings: list[Opening] = []
    door_count = 0
    window_count = 0
    rejected_no_arc = 0

    for i, cand in enumerate(candidates):
        wall = walls_by_id.get(cand.wall_id)
        if wall is None:
            continue

        # ── 1. Ищем дугу двери в локальном окне ──────────────────────────
        has_arc, swing = _detect_arc_near(cand, gray, binary_inv, h_img, w_img)

        # ── 2. Классификация по СТРОГИМ правилам ─────────────────────────
        opening_type = None
        confidence = cand.confidence

        if has_arc:
            # Двойная проверка: ищем "полотно" (door panel) — прямую линию
            # перпендикулярно стене из одной точки gap'а
            has_panel = _detect_door_panel(cand, binary, h_img, w_img)
            opening_type = OpeningType.door
            if has_panel:
                # Идеальная дверь: gap + дуга + полотно
                confidence = min(1.0, cand.confidence + 0.20)
            else:
                # Только gap + дуга, без явного полотна
                confidence = min(1.0, cand.confidence + 0.05)
            door_count += 1
        elif wall.type == WallType.outer:
            # Внешняя стена + нет дуги → window
            has_pattern = _detect_window_pattern(cand, binary, h_img, w_img)
            opening_type = OpeningType.window
            confidence = (
                min(1.0, cand.confidence + 0.10) if has_pattern
                else cand.confidence * 0.7
            )
            window_count += 1
        else:
            # Внутренняя стена + нет дуги → НЕ door (была главная причина FP).
            # Это может быть: проход без двери, или ложный gap.
            # Не создаём opening вообще; пользователь добавит вручную если нужно.
            rejected_no_arc += 1
            continue

        if opening_type is None:
            continue

        opening_id = f"{opening_type.value}_{i:03d}"
        opening = candidate_to_opening(
            cand,
            opening_id=opening_id,
            opening_type=opening_type,
            swing=swing,
        )
        opening.confidence = round(confidence, 3)
        openings.append(opening)

    logger.info(
        f"Opening classification: doors={door_count}, "
        f"windows={window_count}, rejected_no_arc_inner={rejected_no_arc}"
    )

    return openings


def _detect_arc_near(
    cand: OpeningCandidate,
    gray: np.ndarray,
    binary_inv: np.ndarray,
    h_img: int, w_img: int,
) -> tuple[bool, SwingDirection]:
    """
    Поиск дуги в локальном окне вокруг проёма.

    Дуга = окружность, у которой ~75% точек попадают в фон.
    """
    cx = int(cand.center.x)
    cy = int(cand.center.y)
    radius_search = int(cand.width_px * ARC_SEARCH_RADIUS_FACTOR)

    # Локальное окно
    x0 = max(0, cx - radius_search)
    y0 = max(0, cy - radius_search)
    x1 = min(w_img, cx + radius_search)
    y1 = min(h_img, cy + radius_search)
    if x1 - x0 < 20 or y1 - y0 < 20:
        return False, SwingDirection.unknown

    local_gray = gray[y0:y1, x0:x1]
    local_inv = binary_inv[y0:y1, x0:x1]

    # HoughCircles в локальном окне
    blurred = cv2.GaussianBlur(local_gray, (5, 5), 1.2)
    min_r = int(cand.width_px * 0.5)
    max_r = int(cand.width_px * 1.5)

    circles = cv2.HoughCircles(
        blurred, cv2.HOUGH_GRADIENT,
        dp=1.2, minDist=20,
        param1=50, param2=LOCAL_HOUGH_PARAM2,
        minRadius=max(8, min_r), maxRadius=max(20, max_r),
    )
    if circles is None:
        return False, SwingDirection.unknown

    # Проверяем каждую найденную окружность
    for c in circles[0]:
        ccx, ccy, cr = float(c[0]), float(c[1]), float(c[2])
        # Координаты в глобальной системе
        gccx = ccx + x0
        gccy = ccy + y0

        # Центр дуги должен быть ОЧЕНЬ близко к одному из концов проёма
        # (для реальной дверной арки — буквально на конце gap'а).
        # 0.35 * width ≈ 15-20px — отсекает arcs внутри сантехники.
        dist_to_start = math.hypot(gccx - cand.start.x, gccy - cand.start.y)
        dist_to_end = math.hypot(gccx - cand.end.x, gccy - cand.end.y)
        if min(dist_to_start, dist_to_end) > cand.width_px * 0.35:
            continue

        # Является ли это четвертью круга?
        is_quarter, dominant_quadrant = _check_quarter_arc(
            ccx, ccy, cr, local_inv,
        )
        if is_quarter:
            return True, _quadrant_to_swing(dominant_quadrant)

    return False, SwingDirection.unknown


def _check_quarter_arc(
    cx: float, cy: float, r: float, local_inv: np.ndarray,
) -> tuple[bool, int]:
    """Проверка, является ли окружность четвертью круга. Возвращает (is_arc, dominant_quadrant)."""
    h, w = local_inv.shape
    n = 64
    quadrant_hits = [0, 0, 0, 0]
    bg_hits = 0

    for i in range(n):
        angle = 2 * math.pi * i / n
        px = int(cx + r * math.cos(angle))
        py = int(cy + r * math.sin(angle))
        if 0 <= px < w and 0 <= py < h:
            if local_inv[py, px] > 128:
                bg_hits += 1
                if math.cos(angle) >= 0 and math.sin(angle) >= 0:
                    quadrant_hits[0] += 1
                elif math.cos(angle) < 0 and math.sin(angle) >= 0:
                    quadrant_hits[1] += 1
                elif math.cos(angle) < 0 and math.sin(angle) < 0:
                    quadrant_hits[2] += 1
                else:
                    quadrant_hits[3] += 1

    bg_fraction = bg_hits / n
    if not (ARC_BG_FRACTION_RANGE[0] <= bg_fraction <= ARC_BG_FRACTION_RANGE[1]):
        return False, 0

    dominant = quadrant_hits.index(max(quadrant_hits))
    return True, dominant


def _quadrant_to_swing(q: int) -> SwingDirection:
    return [
        SwingDirection.right,
        SwingDirection.left,
        SwingDirection.inward,
        SwingDirection.outward,
    ][q]


def _detect_door_panel(
    cand: OpeningCandidate,
    binary: np.ndarray,
    h_img: int, w_img: int,
) -> bool:
    """
    Door panel detection: на архитектурном плане полотно двери — это
    прямой отрезок длиной ~ширина проёма, исходящий перпендикулярно от
    одного из концов gap'а.

    Алгоритм:
    1. Берём perpendicular vector к стене (от gap внутрь комнаты).
    2. На расстоянии cand.width_px от каждого конца gap'а проверяем
       есть ли в этой точке пиксель binary (полотно).
    3. Если хотя бы в одном из 4 candidate-направлений (от каждого
       конца дуги, в обе стороны perpendicular) находим линию — это panel.
    """
    nx = cand.perpendicular_x
    ny = cand.perpendicular_y
    width_px = cand.width_px

    # Проверочные точки: от каждого конца gap'а, на расстоянии 0.6-1.0 width
    candidate_endpoints = []
    for end_pt in (cand.start, cand.end):
        for radius_factor in (0.7, 0.85):
            r = width_px * radius_factor
            for sign in (1, -1):  # обе стороны perpendicular
                px = int(end_pt.x + sign * nx * r)
                py = int(end_pt.y + sign * ny * r)
                candidate_endpoints.append((px, py))

    hits = 0
    for px, py in candidate_endpoints:
        if 0 <= px < w_img and 0 <= py < h_img:
            # Проверяем небольшую окрестность (3x3) на наличие линии
            x0 = max(0, px - 2)
            y0 = max(0, py - 2)
            x1 = min(w_img, px + 3)
            y1 = min(h_img, py + 3)
            if np.any(binary[y0:y1, x0:x1] > 0):
                hits += 1

    # Если хотя бы 2 из 8 точек совпадают с линией — есть полотно
    return hits >= 2


def _detect_window_pattern(
    cand: OpeningCandidate,
    binary: np.ndarray,
    h_img: int, w_img: int,
) -> bool:
    """
    Окно: тонкие параллельные линии (стеклопакет) в зоне проёма.
    Простая эвристика: ищем не-нулевые пиксели в средней части проёма.
    """
    cx = int(cand.center.x)
    cy = int(cand.center.y)
    half_w = int(cand.width_px / 2)
    half_h = 6

    x0 = max(0, cx - half_w)
    y0 = max(0, cy - half_h)
    x1 = min(w_img, cx + half_w)
    y1 = min(h_img, cy + half_h)

    if x1 - x0 < 5 or y1 - y0 < 3:
        return False

    region = binary[y0:y1, x0:x1]
    fill_ratio = np.sum(region > 0) / max(region.size, 1)
    # 5–35% заполнения = тонкие линии (стеклопакет)
    return 0.05 <= fill_ratio <= 0.35
