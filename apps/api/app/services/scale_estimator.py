"""
Модуль оценки масштаба плана (пикселей на метр).

Стратегии (в порядке приоритета):
1. OCR: найти подписи площадей комнат (формат "14.4" или "14,4 м²")
   Сопоставить с полигонами комнат → px_per_meter = sqrt(area_px / area_m2)
2. OCR: найти размерные линии (формат "3200" мм или "3.2 м")
3. Пользовательский ввод: если confidence < 0.5 → запросить у пользователя

Для OCR используется pytesseract. Если pytesseract не установлен —
graceful degradation с confidence=0.
"""

from __future__ import annotations

import logging
import math
import re
from typing import NamedTuple

import numpy as np

logger = logging.getLogger(__name__)

# Пытаемся импортировать pytesseract — не критично, если нет
try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    logger.warning("pytesseract не установлен — OCR масштаба недоступен")


class OcrArea(NamedTuple):
    value_m2: float
    cx_px: float     # примерное положение подписи в изображении
    cy_px: float


# Регэкспы для площадей
_AREA_PATTERNS = [
    # "14.4 м²", "14,4 м²", "14.4м2"
    re.compile(r"(\d+[.,]\d+)\s*[мм][²²2]", re.IGNORECASE),
    # "14.4" — просто число в диапазоне 2-100 (характерный диапазон площадей комнат)
    re.compile(r"\b(\d+[.,]\d+)\b"),
    # Целое число типа "14" или "18"
    re.compile(r"\b(\d{1,2})\b"),
]

# Диапазон разумных площадей комнаты
AREA_MIN_M2 = 2.0
AREA_MAX_M2 = 80.0


def _parse_float(s: str) -> float:
    return float(s.replace(",", "."))


def extract_area_labels_from_image(
    gray_img: "np.ndarray",
) -> list[OcrArea]:
    """
    OCR на изображении → список (площадь_м², cx, cy).
    Возвращает пустой список если pytesseract недоступен.
    """
    if not TESSERACT_AVAILABLE:
        return []

    try:
        # Конфиг Tesseract: числа + пробелы + "м²"
        config = "--oem 3 --psm 11 -c tessedit_char_whitelist=0123456789.,"
        data = pytesseract.image_to_data(
            gray_img,
            lang="rus+eng",
            config=config,
            output_type=pytesseract.Output.DICT,
        )
    except Exception as e:
        logger.warning(f"pytesseract OCR error: {e}")
        return []

    results: list[OcrArea] = []
    texts = data.get("text", [])
    lefts = data.get("left", [])
    tops = data.get("top", [])
    widths = data.get("width", [])
    heights = data.get("height", [])
    confs = data.get("conf", [])

    for i, text in enumerate(texts):
        text = (text or "").strip()
        if not text or int(confs[i]) < 40:
            continue

        for pattern in _AREA_PATTERNS:
            m = pattern.search(text)
            if m:
                try:
                    val = _parse_float(m.group(1))
                    if AREA_MIN_M2 <= val <= AREA_MAX_M2:
                        cx = lefts[i] + widths[i] / 2
                        cy = tops[i] + heights[i] / 2
                        results.append(OcrArea(value_m2=val, cx_px=cx, cy_px=cy))
                except ValueError:
                    pass
                break

    # Дедупликация: убрать дубли с одинаковой площадью вблизи
    deduped: list[OcrArea] = []
    for r in results:
        is_dup = any(
            abs(r.value_m2 - d.value_m2) < 0.5
            and math.hypot(r.cx_px - d.cx_px, r.cy_px - d.cy_px) < 30
            for d in deduped
        )
        if not is_dup:
            deduped.append(r)

    logger.info(f"OCR площадей: {len(deduped)} подписей найдено: {[r.value_m2 for r in deduped]}")
    return deduped


def estimate_scale_from_areas(
    room_polygons: list[dict],   # [{"id": ..., "area_px2": float, "centroid": {"x", "y"}}]
    ocr_areas: list[OcrArea],
) -> tuple[float | None, float]:
    """
    Оценить px_per_meter по соответствию площадей полигонов и OCR-подписей.

    Алгоритм:
    1. Для каждой OCR-подписи (area_m2, cx, cy) найти ближайший полигон
    2. Вычислить px_per_meter = sqrt(area_px / area_m2)
    3. Взять медиану по всем парам, отфильтровать выбросы

    Returns:
        (px_per_meter | None, confidence)
    """
    if not ocr_areas or not room_polygons:
        return None, 0.0

    estimates: list[float] = []

    for ocr in ocr_areas:
        # Ближайший полигон по центроиду
        best_room = None
        best_dist = float("inf")
        for room in room_polygons:
            centroid = room.get("centroid")
            if not centroid:
                continue
            dist = math.hypot(centroid["x"] - ocr.cx_px, centroid["y"] - ocr.cy_px)
            if dist < best_dist:
                best_dist = dist
                best_room = room

        if best_room is None:
            continue

        area_px2 = best_room.get("area_px2")
        if not area_px2 or area_px2 <= 0:
            continue

        # px_per_meter = sqrt(area_px2 / area_m2)
        try:
            scale = math.sqrt(area_px2 / ocr.value_m2)
            estimates.append(scale)
            logger.debug(
                f"Комната {best_room.get('id')}: "
                f"{area_px2:.0f}px² / {ocr.value_m2}м² → {scale:.1f} px/m"
            )
        except (ZeroDivisionError, ValueError):
            pass

    if not estimates:
        return None, 0.0

    # Медиана — устойчива к выбросам
    median_scale = float(np.median(estimates))

    # Фильтр выбросов: убираем те, что отличаются от медианы > 30%
    filtered = [s for s in estimates if abs(s - median_scale) / median_scale < 0.30]

    if not filtered:
        filtered = estimates

    final_scale = float(np.mean(filtered))

    # Confidence: чем больше совпадающих пар и чем ниже дисперсия — тем лучше
    if len(filtered) == 0:
        confidence = 0.0
    elif len(filtered) == 1:
        confidence = 0.5
    else:
        cv = float(np.std(filtered) / (final_scale + 1e-6))  # coefficient of variation
        confidence = max(0.0, min(1.0, 1.0 - cv * 2))
        # Бонус за количество совпадений
        confidence = min(1.0, confidence + 0.1 * min(len(filtered) - 1, 3))

    logger.info(
        f"Масштаб: {final_scale:.1f} px/m "
        f"(из {len(filtered)}/{len(estimates)} оценок, "
        f"confidence={confidence:.2f})"
    )
    return final_scale, confidence


def estimate_scale_from_user_input(
    known_wall_length_m: float,
    wall_length_px: float,
) -> tuple[float, float]:
    """
    Пользователь указал длину одной стены — вычисляем масштаб напрямую.
    Confidence = 0.95 (почти точно, если пользователь не ошибся).
    """
    if known_wall_length_m <= 0 or wall_length_px <= 0:
        return 0.0, 0.0
    scale = wall_length_px / known_wall_length_m
    return scale, 0.95


def pixels_to_meters(px: float, px_per_meter: float) -> float:
    if px_per_meter <= 0:
        return 0.0
    return px / px_per_meter


def meters_to_pixels(m: float, px_per_meter: float) -> float:
    return m * px_per_meter
