"""
Модуль оценки масштаба + OCR площадей с плана.

КЛЮЧЕВЫЕ ИЗМЕНЕНИЯ V2:
1. Auto-detect Tesseract на Windows (часто не в PATH после установки)
2. Несколько PSM-режимов: 11 (sparse text) + 6 (single block) + 12 (sparse + OSD)
3. Pre-processing для OCR: upscale + adaptive threshold
4. Распознаём И запятые ("4,0") и точки ("4.0")
5. Bbox-фильтрация: только числа в "обычном" размере шрифта плана
6. Range-фильтрация: 1.5 ≤ value ≤ 80 м² (чтобы отбросить даты, телефоны)
"""

from __future__ import annotations

import logging
import math
import os
import re
import shutil
from typing import NamedTuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)


# ─── Tesseract auto-detect ────────────────────────────────────────────────────


def _setup_tesseract() -> bool:
    """
    Найти tesseract.exe на Windows и сообщить pytesseract где он.
    Возвращает True если найден.
    """
    try:
        import pytesseract
    except ImportError:
        logger.warning("pytesseract не установлен")
        return False

    # 1. Уже в PATH?
    if shutil.which("tesseract"):
        logger.info(f"Tesseract найден в PATH: {shutil.which('tesseract')}")
        return True

    # 2. Стандартные пути установки на Windows
    win_candidates = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
        os.path.expanduser(r"~\AppData\Local\Tesseract-OCR\tesseract.exe"),
    ]

    # 3. Стандартные пути на Linux/Mac (на случай контейнера)
    nix_candidates = [
        "/usr/bin/tesseract",
        "/usr/local/bin/tesseract",
        "/opt/homebrew/bin/tesseract",
    ]

    for path in win_candidates + nix_candidates:
        if os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
            logger.info(f"Tesseract auto-detected: {path}")
            return True

    logger.warning(
        "Tesseract не найден. Установите с https://github.com/UB-Mannheim/tesseract/wiki "
        "(Windows) или 'brew install tesseract tesseract-lang' (macOS)."
    )
    return False


_TESSERACT_AVAILABLE = _setup_tesseract()


class OcrArea(NamedTuple):
    value_m2: float
    cx_px: float
    cy_px: float
    raw_text: str = ""


# ─── Регэкспы ────────────────────────────────────────────────────────────────

# Десятичное число с точкой ИЛИ запятой ("4.0", "14,4", "16.3")
_DECIMAL_PATTERN = re.compile(r"\b(\d{1,2}[.,]\d{1,2})\b")

# Целое число (1-80) — иногда подписывают как "16"
_INTEGER_PATTERN = re.compile(r"\b(\d{1,2})\b")

# Диапазон осмысленных площадей комнат
AREA_MIN_M2 = 1.5
AREA_MAX_M2 = 80.0

# Минимальная и максимальная высота bbox текста (в px) — отсекает огромный/мелкий шрифт
MIN_TEXT_HEIGHT_PX = 6
MAX_TEXT_HEIGHT_PX = 60


# ─── Pre-processing для OCR ──────────────────────────────────────────────────


def _prepare_for_ocr(gray_img: np.ndarray) -> np.ndarray:
    """
    Подготовить изображение для лучшего OCR числовых меток:
    - upscale (x2) для мелкого шрифта,
    - adaptive threshold,
    - дополнительный denoise.
    """
    h, w = gray_img.shape
    # Upscale до ~1500-2000 max side для лучшей читаемости
    target = 1800
    if max(h, w) < target:
        scale = target / max(h, w)
        gray_img = cv2.resize(gray_img, (int(w * scale), int(h * scale)),
                              interpolation=cv2.INTER_CUBIC)

    # Adaptive threshold: численные метки обычно на белом фоне
    binary = cv2.adaptiveThreshold(
        gray_img, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=21, C=10,
    )
    return binary


def _parse_value(text: str) -> float | None:
    """Распарсить '4,0' или '4.0' в float."""
    text = text.strip().replace(",", ".")
    try:
        v = float(text)
        if AREA_MIN_M2 <= v <= AREA_MAX_M2:
            return v
    except ValueError:
        pass
    return None


# ─── OCR функция ──────────────────────────────────────────────────────────────


def extract_area_labels_from_image(gray_img: np.ndarray) -> list[OcrArea]:
    """
    OCR на изображении → список (площадь_м², cx, cy).

    Запускает OCR в нескольких режимах и объединяет результаты.
    Если pytesseract или Tesseract недоступны — возвращает [].
    """
    if not _TESSERACT_AVAILABLE:
        return []

    try:
        import pytesseract
    except ImportError:
        return []

    h_orig, w_orig = gray_img.shape
    prepared = _prepare_for_ocr(gray_img)
    h_prep, w_prep = prepared.shape
    scale_back = w_orig / w_prep  # для обратной трансформации координат

    # Запускаем несколько OCR-проходов с разными PSM
    psm_configs = [
        # PSM 11: sparse text — лучше для меток, разбросанных по плану
        "--oem 3 --psm 11 -c tessedit_char_whitelist=0123456789.,",
        # PSM 6: assume uniform block — иногда работает лучше для чистых сканов
        "--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789.,",
    ]

    all_results: list[OcrArea] = []
    for config in psm_configs:
        try:
            data = pytesseract.image_to_data(
                prepared, lang="rus+eng",
                config=config,
                output_type=pytesseract.Output.DICT,
            )
        except Exception as e:
            logger.warning(f"pytesseract OCR error (config={config[:20]}...): {e}")
            continue

        texts = data.get("text", [])
        lefts = data.get("left", [])
        tops = data.get("top", [])
        widths = data.get("width", [])
        heights = data.get("height", [])
        confs = data.get("conf", [])

        for i, raw in enumerate(texts):
            text = (raw or "").strip()
            if not text:
                continue
            try:
                conf = int(confs[i])
            except (ValueError, TypeError):
                conf = 0
            if conf < 30:
                continue

            # Высота bbox должна быть в нормальном диапазоне
            bbox_h = heights[i]
            if bbox_h < MIN_TEXT_HEIGHT_PX or bbox_h > MAX_TEXT_HEIGHT_PX:
                continue

            # Сначала ищем десятичное (чаще встречается)
            value = None
            m = _DECIMAL_PATTERN.search(text)
            if m:
                value = _parse_value(m.group(1))

            # Если не нашли десятичное — пробуем целое (но строже)
            if value is None and len(text) <= 4:
                m = _INTEGER_PATTERN.search(text)
                if m:
                    raw_int = int(m.group(1))
                    if 5 <= raw_int <= 60:  # узкий диапазон для целых
                        value = float(raw_int)

            if value is None:
                continue

            # Переводим bbox в исходные координаты
            cx = (lefts[i] + widths[i] / 2) * scale_back
            cy = (tops[i] + heights[i] / 2) * scale_back

            all_results.append(OcrArea(
                value_m2=value,
                cx_px=float(cx),
                cy_px=float(cy),
                raw_text=text,
            ))

    # Дедуп: метки с одинаковой площадью в близких координатах
    deduped: list[OcrArea] = []
    for r in all_results:
        is_dup = any(
            abs(r.value_m2 - d.value_m2) < 0.4
            and math.hypot(r.cx_px - d.cx_px, r.cy_px - d.cy_px) < 40
            for d in deduped
        )
        if not is_dup:
            deduped.append(r)

    logger.info(
        f"OCR: найдено {len(deduped)} уникальных меток площадей: "
        f"{sorted([round(r.value_m2, 1) for r in deduped])}"
    )
    return deduped


# ─── Оценка масштаба ─────────────────────────────────────────────────────────


def estimate_scale_from_areas(
    room_polygons: list[dict],
    ocr_areas: list[OcrArea],
) -> tuple[float | None, float]:
    """
    Оценить px_per_meter по соответствию OCR-площадей и пиксельных площадей полигонов.

    Returns: (px_per_meter | None, confidence)
    """
    if not ocr_areas or not room_polygons:
        return None, 0.0

    estimates: list[tuple[float, str]] = []  # (scale, room_id для дебага)

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

        try:
            scale = math.sqrt(area_px2 / ocr.value_m2)
            estimates.append((scale, best_room.get("id", "?")))
        except (ZeroDivisionError, ValueError):
            pass

    if not estimates:
        return None, 0.0

    scales = [e[0] for e in estimates]
    median_scale = float(np.median(scales))

    # Фильтр выбросов (>30% отклонение от медианы)
    filtered = [s for s in scales if abs(s - median_scale) / median_scale < 0.30]
    if not filtered:
        filtered = scales

    final_scale = float(np.mean(filtered))

    # Confidence
    if len(filtered) <= 1:
        confidence = 0.5 if filtered else 0.0
    else:
        cv = float(np.std(filtered) / (final_scale + 1e-6))
        confidence = max(0.0, min(1.0, 1.0 - cv * 2))
        confidence = min(1.0, confidence + 0.1 * min(len(filtered) - 1, 3))

    logger.info(
        f"Scale: {final_scale:.1f} px/m (filtered {len(filtered)}/{len(estimates)}, "
        f"confidence={confidence:.2f})"
    )
    return final_scale, confidence


def estimate_scale_from_user_input(
    known_wall_length_m: float, wall_length_px: float,
) -> tuple[float, float]:
    if known_wall_length_m <= 0 or wall_length_px <= 0:
        return 0.0, 0.0
    return wall_length_px / known_wall_length_m, 0.95


def pixels_to_meters(px: float, px_per_meter: float) -> float:
    return px / px_per_meter if px_per_meter > 0 else 0.0


def meters_to_pixels(m: float, px_per_meter: float) -> float:
    return m * px_per_meter
