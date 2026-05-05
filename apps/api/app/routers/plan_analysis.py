"""
API-роутер: анализ плана квартиры, расстановка мебели, валидация.

Эндпоинты:
  POST /api/v1/plan/analyze        — CV-пайплайн: image → geometry JSON
  POST /api/v1/plan/place-furniture — rule-based placement
  POST /api/v1/plan/validate-layout — проверка расстановки
  POST /api/v1/plan/scale           — обновить масштаб (user input)
"""

from __future__ import annotations

import io
import logging

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.schemas.furniture import (
    AnalyzePlanResponse,
    FurniturePlacement,
    PlaceFurnitureRequest,
    PlaceFurnitureResponse,
    ValidateLayoutRequest,
    ValidateLayoutResponse,
)
from app.schemas.geometry import ApartmentGeometry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/plan", tags=["plan-analysis"])


# ─── Утилиты ─────────────────────────────────────────────────────────────────

def _load_cv2():
    """Ленивый импорт OpenCV — не падать при старте если не установлен."""
    try:
        import cv2
        import numpy as np
        from app.services.preprocessing import load_image_from_bytes
        return cv2, np, load_image_from_bytes
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=f"OpenCV не установлен: {e}. Запустите: pip install opencv-python-headless"
        )


async def _fetch_image_from_url(url: str) -> bytes:
    """Скачать изображение по URL."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url)
        if resp.status_code != 200:
            raise HTTPException(400, f"Не удалось загрузить изображение: {url}")
        return resp.content


# ─── POST /plan/analyze ───────────────────────────────────────────────────────

@router.post("/analyze", response_model=AnalyzePlanResponse)
async def analyze_plan(
    file: UploadFile | None = File(default=None),
    image_url: str | None = Form(default=None),
    include_debug: bool = Form(default=False),
):
    """
    Анализ плана квартиры.

    Принимает:
    - file: изображение плана (multipart upload)
    - image_url: URL изображения (fal.ai или S3)
    - include_debug: включить base64 debug-слои в ответ

    Возвращает:
    - geometry: ApartmentGeometry JSON
    - needs_validation: нужно ли подтверждение пользователя
    """
    cv2, np, load_image_from_bytes = _load_cv2()
    from app.services.plan_processor import needs_user_validation, run_pipeline

    # Получаем байты изображения
    if file is not None:
        image_bytes = await file.read()
        logger.info(f"[analyze] Загружен file: {len(image_bytes)} байт, name={file.filename}")
    elif image_url:
        image_bytes = await _fetch_image_from_url(image_url)
        logger.info(f"[analyze] Загружено по URL: {len(image_bytes)} байт")
    else:
        raise HTTPException(400, "Нужно передать file или image_url")

    # Сохраняем загруженный план для post-mortem анализа
    import os
    debug_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "debug_uploads")
    try:
        os.makedirs(debug_dir, exist_ok=True)
        import time
        debug_path = os.path.join(debug_dir, f"plan_{int(time.time())}.png")
        with open(debug_path, "wb") as f:
            f.write(image_bytes)
        logger.info(f"[analyze] План сохранён для дебага: {debug_path}")
    except Exception as e:
        logger.warning(f"[analyze] Не удалось сохранить дебаг: {e}")

    # Конвертируем в numpy
    try:
        image = load_image_from_bytes(image_bytes)
        logger.info(f"[analyze] Изображение декодировано: shape={image.shape}")
    except Exception as e:
        raise HTTPException(400, f"Не удалось декодировать изображение: {e}")

    # Запускаем пайплайн
    try:
        geometry = run_pipeline(image, include_debug=include_debug)
    except Exception as e:
        logger.exception("Ошибка CV-пайплайна")
        raise HTTPException(500, f"Ошибка анализа плана: {e}")

    needs_val = needs_user_validation(geometry)

    return AnalyzePlanResponse(
        geometry=geometry.model_dump(),
        needs_validation=needs_val,
        message=(
            "Геометрия распознана с низкой уверенностью. Проверьте стены и комнаты."
            if needs_val else
            "Геометрия успешно распознана."
        ),
    )


# ─── POST /plan/scale ─────────────────────────────────────────────────────────

@router.post("/scale")
async def update_scale(
    geometry: dict,
    known_wall_length_m: float,
    wall_id: str,
):
    """
    Обновить масштаб на основе пользовательского ввода.
    Пользователь указывает длину одной известной стены в метрах.
    """
    from app.services.scale_estimator import estimate_scale_from_user_input

    try:
        geo = ApartmentGeometry(**geometry)
    except Exception as e:
        raise HTTPException(400, f"Неверный формат geometry: {e}")

    wall = geo.get_wall(wall_id)
    if wall is None:
        raise HTTPException(404, f"Стена {wall_id!r} не найдена")

    import math
    wall_length_px = math.hypot(
        wall.end.x - wall.start.x,
        wall.end.y - wall.start.y
    )
    px_per_meter, confidence = estimate_scale_from_user_input(known_wall_length_m, wall_length_px)

    geo.scale.px_per_meter = px_per_meter
    geo.scale.source = "user_input"
    geo.scale.confidence = confidence

    # Обновить площади комнат
    for room in geo.rooms:
        if room.area_px2:
            room.area_m2 = round(room.area_px2 / (px_per_meter ** 2), 1)

    return {"geometry": geo.model_dump(), "px_per_meter": px_per_meter}


# ─── POST /plan/place-furniture ──────────────────────────────────────────────

@router.post("/place-furniture", response_model=PlaceFurnitureResponse)
async def place_furniture(body: PlaceFurnitureRequest):
    """
    Расставить мебель из каталога по locked-геометрии.

    Принимает user-validated geometry + предпочтения (стиль, бюджет).
    Возвращает FurniturePlacement с координатами каждого предмета.
    """
    from app.services.furniture_catalog import load_catalog
    from app.services.furniture_placement import FurniturePlacementEngine

    # Парсим геометрию
    try:
        geometry = ApartmentGeometry(**body.geometry)
    except Exception as e:
        raise HTTPException(400, f"Неверный формат geometry: {e}")

    if not geometry.user_validated:
        logger.warning("Расстановка по невалидированной геометрии")

    # Загружаем каталог
    catalog = load_catalog()

    # Запускаем движок
    engine = FurniturePlacementEngine(
        geometry=geometry,
        catalog=catalog,
        style=body.style,
        budget=body.budget,
    )
    placement = engine.place_all()

    return PlaceFurnitureResponse(
        placement=placement.model_dump(),
    )


# ─── POST /plan/validate-layout ───────────────────────────────────────────────

@router.post("/validate-layout", response_model=ValidateLayoutResponse)
async def validate_layout(body: ValidateLayoutRequest):
    """
    Проверить расстановку мебели на корректность.

    Проверяет:
    - Все item_id существуют в каталоге
    - Размеры не изменены AI
    - Мебель не выходит за границы комнат
    - Нет пересечений
    - Не заблокированы двери
    """
    from app.services.furniture_catalog import load_catalog
    from app.services.layout_validator import validate_layout as do_validate

    try:
        geometry = ApartmentGeometry(**body.geometry)
        placement = FurniturePlacement(**body.placement)
    except Exception as e:
        raise HTTPException(400, f"Неверный формат данных: {e}")

    catalog = load_catalog()
    result = do_validate(geometry, placement, catalog)

    return ValidateLayoutResponse(
        valid=result.valid,
        errors=result.errors,
        warnings=result.warnings,
    )
