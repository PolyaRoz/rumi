"""
Модуль предобработки изображения плана квартиры.

Шаги:
1. Конвертация в grayscale
2. Повышение контраста (CLAHE)
3. Шумоподавление
4. Бинаризация (Otsu)
5. Морфологические операции для выделения стен
6. Удаление текстовых/мебельных артефактов (blob filtering)

Возвращает набор numpy-массивов для последующих детекторов.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


@dataclass
class PreprocessedPlan:
    original: np.ndarray         # BGR, исходник
    gray: np.ndarray             # grayscale
    enhanced: np.ndarray         # CLAHE enhanced
    binary: np.ndarray           # бинаризованное (стены = 255, фон = 0)
    walls_mask: np.ndarray       # только стены (после morph ops)
    clean: np.ndarray            # без текста и мелких артефактов
    scale_factor: float = 1.0   # если изображение было ресайзнуто
    original_size: tuple[int, int] = (0, 0)  # (width, height)


MAX_DIMENSION = 2048  # ограничиваем размер для скорости CV


def load_image_from_bytes(data: bytes) -> np.ndarray:
    """Загрузить изображение из байт → BGR numpy array."""
    pil = Image.open(io.BytesIO(data)).convert("RGB")
    arr = np.array(pil)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def load_image_from_file(path: str) -> np.ndarray:
    img = cv2.imread(path)
    if img is None:
        raise ValueError(f"Не удалось загрузить изображение: {path}")
    return img


def _resize_if_needed(img: np.ndarray) -> tuple[np.ndarray, float]:
    """Уменьшить изображение, если оно слишком большое, сохраняя пропорции."""
    h, w = img.shape[:2]
    max_side = max(h, w)
    if max_side <= MAX_DIMENSION:
        return img, 1.0
    scale = MAX_DIMENSION / max_side
    new_w = int(w * scale)
    new_h = int(h * scale)
    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
    logger.info(f"Изображение уменьшено: {w}x{h} → {new_w}x{new_h} (scale={scale:.3f})")
    return resized, scale


def _enhance_contrast(gray: np.ndarray) -> np.ndarray:
    """CLAHE: улучшение локального контраста для тёмных чертежей."""
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(gray)


def _binarize(enhanced: np.ndarray) -> np.ndarray:
    """
    Адаптивная бинаризация.
    - Сначала пробуем Otsu (хорошо для чистых чертежей)
    - Если Otsu даёт слишком мало стен — переходим к адаптивной
    """
    # Otsu (инвертированный): стены = тёмные линии → после инверсии = 255
    _, binary_otsu = cv2.threshold(
        enhanced, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )

    wall_ratio = np.sum(binary_otsu > 0) / binary_otsu.size
    if 0.02 < wall_ratio < 0.35:
        # Разумный диапазон для плана
        return binary_otsu

    # Адаптивная — работает лучше на неравномерно освещённых сканах
    binary_adaptive = cv2.adaptiveThreshold(
        enhanced, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        blockSize=15, C=8
    )
    return binary_adaptive


def _remove_small_blobs(binary: np.ndarray, min_area: int = 100) -> np.ndarray:
    """
    Удалить маленькие несвязные компоненты:
    - шум
    - цифры площадей (маленькие символы)
    - условные обозначения мебели/сантехники
    """
    nb_components, output, stats, _ = cv2.connectedComponentsWithStats(
        binary, connectivity=8
    )
    cleaned = np.zeros_like(binary)
    for i in range(1, nb_components):
        area = stats[i, cv2.CC_STAT_AREA]
        if area >= min_area:
            cleaned[output == i] = 255
    return cleaned


def _remove_large_blobs(binary: np.ndarray, max_area_fraction: float = 0.15) -> np.ndarray:
    """
    Удалить очень большие компоненты — обычно это фон или штриховки комнат.
    Стены — это средние по размеру линии.
    """
    total_area = binary.shape[0] * binary.shape[1]
    max_area = int(total_area * max_area_fraction)

    nb_components, output, stats, _ = cv2.connectedComponentsWithStats(
        binary, connectivity=8
    )
    cleaned = np.zeros_like(binary)
    for i in range(1, nb_components):
        area = stats[i, cv2.CC_STAT_AREA]
        if area <= max_area:
            cleaned[output == i] = 255
    return cleaned


def _extract_walls_mask(binary: np.ndarray) -> np.ndarray:
    """
    Выделить стены как толстые линии.

    Подход:
    1. Морфологическое закрытие — соединяем разрывы в стенах
    2. Дилатация — немного утолщаем, чтобы связать смежные сегменты
    3. Скелетизация — (опционально) находим центральные линии

    Стены распознаются как линии толщиной > MIN_WALL_THICKNESS пикселей.
    Тонкие линии дверей, окон, подписей фильтруются.
    """
    # Параметры морфологии (подбираются под типичный масштаб чертежа)
    kernel_close = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel_close, iterations=2)

    # Убираем очень тонкие линии (< 2 px) — они не стены
    kernel_erode = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    eroded = cv2.erode(closed, kernel_erode, iterations=1)
    dilated_back = cv2.dilate(eroded, kernel_erode, iterations=1)

    return dilated_back


def preprocess(image: np.ndarray) -> PreprocessedPlan:
    """
    Полный пайплайн предобработки.

    Args:
        image: BGR numpy array из cv2.imread или load_image_from_bytes

    Returns:
        PreprocessedPlan с набором слоёв для детекторов.
    """
    original_h, original_w = image.shape[:2]

    # 1. Ресайз для скорости
    resized, scale_factor = _resize_if_needed(image)

    # 2. Grayscale
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)

    # 3. Шумоподавление (перед CLAHE — меньше артефактов)
    denoised = cv2.fastNlMeansDenoising(gray, h=7, templateWindowSize=7, searchWindowSize=21)

    # 4. Повышение контраста
    enhanced = _enhance_contrast(denoised)

    # 5. Бинаризация
    binary = _binarize(enhanced)

    # 6. Удаляем мелкий мусор (шум, текст, мебель на плане)
    clean = _remove_small_blobs(binary, min_area=80)

    # 7. Выделяем маску стен (толстые линии)
    walls_mask = _extract_walls_mask(clean)

    h, w = resized.shape[:2]
    logger.info(
        f"Предобработка завершена: {w}x{h}, "
        f"wall_pixels={np.sum(walls_mask > 0)}, "
        f"wall_fraction={np.sum(walls_mask > 0) / (w * h):.3f}"
    )

    return PreprocessedPlan(
        original=resized,
        gray=gray,
        enhanced=enhanced,
        binary=binary,
        walls_mask=walls_mask,
        clean=clean,
        scale_factor=scale_factor,
        original_size=(original_w, original_h),
    )


def encode_to_base64(img: np.ndarray) -> str:
    """Закодировать numpy-изображение в base64 PNG для передачи на фронтенд."""
    import base64
    _, buffer = cv2.imencode(".png", img)
    return base64.b64encode(buffer).decode("utf-8")


def draw_debug_overlay(plan: PreprocessedPlan, walls=None, rooms=None, doors=None, windows=None) -> np.ndarray:
    """
    Нарисовать debug-оверлей поверх оригинала:
    - стены — синий
    - комнаты — полупрозрачный зелёный
    - двери — оранжевый
    - окна — голубой
    """
    overlay = plan.original.copy()
    h, w = overlay.shape[:2]

    if walls:
        for wall in walls:
            p1 = (int(wall["start"]["x"]), int(wall["start"]["y"]))
            p2 = (int(wall["end"]["x"]), int(wall["end"]["y"]))
            cv2.line(overlay, p1, p2, (200, 60, 20), 3)  # синий

    if rooms:
        room_overlay = overlay.copy()
        for room in rooms:
            pts = np.array(
                [[int(p["x"]), int(p["y"])] for p in room["polygon"]], dtype=np.int32
            )
            cv2.fillPoly(room_overlay, [pts], (80, 200, 80))   # зелёный fill
            cv2.polylines(overlay, [pts], True, (0, 180, 0), 2)
        overlay = cv2.addWeighted(overlay, 0.75, room_overlay, 0.25, 0)

    if doors:
        for door in doors:
            cx = int(door["position"]["x"])
            cy = int(door["position"]["y"])
            w_px = int(door.get("width_px", 30))
            cv2.rectangle(overlay, (cx - w_px // 2, cy - 6), (cx + w_px // 2, cy + 6), (0, 140, 255), 2)
            cv2.putText(overlay, "D", (cx - 5, cy + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 100, 255), 1)

    if windows:
        for win in windows:
            cx = int(win["position"]["x"])
            cy = int(win["position"]["y"])
            w_px = int(win.get("width_px", 40))
            cv2.rectangle(overlay, (cx - w_px // 2, cy - 4), (cx + w_px // 2, cy + 4), (255, 200, 0), 2)
            cv2.putText(overlay, "W", (cx - 5, cy + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (220, 180, 0), 1)

    return overlay
