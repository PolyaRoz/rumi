"""
Room Recovery — восстановление комнаты по позиции OCR-метки через flood fill.

ПРОБЛЕМА которую решаем:
  Polygonizer находит N полигонов через flood fill из углов изображения.
  Но если коридор/спальня соединены с соседями открытыми проёмами больше
  чем gap-closing kernel может закрыть → они сливаются в один большой
  полигон. anchor_rooms_to_labels привяжет только ОДНУ метку из нескольких,
  попавших в этот полигон, остальные пропадут.

РЕШЕНИЕ:
  Для каждой OCR-метки, которая не была привязана ни к одному полигону
  ПОСЛЕ anchoring, запустить **flood fill из позиции метки** на
  fortified mask (стены + закрытые проёмы). Это даст полигон ровно той
  области, в которой стоит подпись, независимо от того, насколько
  большая получилась слитная область вокруг.

Это превращает area labels в АНКЕРНЫЕ ТОЧКИ (как требует ТЗ):
  если метка есть → комната ВСЕГДА восстанавливается, даже если
  polygonizer её пропустил.
"""

from __future__ import annotations

import logging

import cv2
import numpy as np

from app.schemas.geometry import Point, Room, RoomLabel
from app.services.room_anchoring import classify_room_by_area
from app.services.scale_estimator import OcrArea

logger = logging.getLogger(__name__)


# Параметры
MIN_RECOVERED_AREA_PX = 500    # ниже — точка попала на стену или мелкую иконку
POLY_EPSILON_FRACTION = 0.008


def recover_rooms_from_labels(
    closed_mask: np.ndarray,
    unresolved_labels: list[OcrArea],
    existing_rooms: list[Room],
    px_per_meter: float | None,
    img_area_px: float,
) -> tuple[list[Room], list[OcrArea]]:
    """
    Для каждой OCR-метки в unresolved_labels запустить flood fill и
    извлечь полигон комнаты вокруг неё.

    Returns:
        (recovered_rooms, still_unresolved_labels)
    """
    if not unresolved_labels:
        return [], []

    h, w = closed_mask.shape

    # Инвертируем: фон (interior) = 255, стены = 0
    interior = cv2.bitwise_not(closed_mask)

    recovered: list[Room] = []
    still_unresolved: list[OcrArea] = []

    # ID-генератор для новых комнат — продолжаем после existing
    next_idx = len(existing_rooms)

    for label in unresolved_labels:
        seed_x = int(label.cx_px)
        seed_y = int(label.cy_px)

        # Защита от выхода за границы
        if not (0 <= seed_x < w and 0 <= seed_y < h):
            still_unresolved.append(label)
            continue

        # Если seed попал на стену — попробуем сместиться. Часто метка
        # стоит впритык к стене, а соседний пиксель уже interior.
        if interior[seed_y, seed_x] == 0:
            # Поиск ближайшей точки interior в радиусе 30px
            found = False
            for r in range(1, 30):
                for dx in range(-r, r + 1):
                    for dy in (-r, r):
                        nx, ny = seed_x + dx, seed_y + dy
                        if 0 <= nx < w and 0 <= ny < h and interior[ny, nx] > 0:
                            seed_x, seed_y = nx, ny
                            found = True
                            break
                    if found:
                        break
                for dy in range(-r + 1, r):
                    for dx in (-r, r):
                        nx, ny = seed_x + dx, seed_y + dy
                        if 0 <= nx < w and 0 <= ny < h and interior[ny, nx] > 0:
                            seed_x, seed_y = nx, ny
                            found = True
                            break
                    if found:
                        break
                if found:
                    break
            if not found:
                logger.warning(
                    f"Recovery: метка '{label.raw_text}' ({label.value_m2}м²) "
                    f"в позиции ({seed_x},{seed_y}) — нет interior рядом"
                )
                still_unresolved.append(label)
                continue

        # Flood fill из этой позиции на КОПИИ маски
        # (cv2.floodFill модифицирует input)
        scratch = interior.copy()
        flood_mask = np.zeros((h + 2, w + 2), dtype=np.uint8)
        # Заливаем 128 (отличное от 255, чтобы выделить эту область)
        cv2.floodFill(scratch, flood_mask, (seed_x, seed_y), 128)

        # Получаем mask только этой комнаты
        room_mask = (scratch == 128).astype(np.uint8) * 255
        area_px = int(np.sum(room_mask > 0))

        if area_px < MIN_RECOVERED_AREA_PX:
            logger.warning(
                f"Recovery: метка '{label.raw_text}' ({label.value_m2}м²) — "
                f"восстановленная область слишком мала ({area_px}px²)"
            )
            still_unresolved.append(label)
            continue

        # Проверка: не пересекается ли с уже существующей комнатой
        # (если flood fill вернул ту же область что у уже labeled room)
        is_duplicate = False
        for existing in existing_rooms:
            if existing.centroid is None:
                continue
            ex_cx = int(existing.centroid.x)
            ex_cy = int(existing.centroid.y)
            if (0 <= ex_cx < w and 0 <= ex_cy < h
                    and room_mask[ex_cy, ex_cx] > 0):
                is_duplicate = True
                break
        if is_duplicate:
            logger.info(
                f"Recovery: метка '{label.raw_text}' попала в уже существующую "
                f"комнату — пропускаем (anchoring должен был обработать)"
            )
            still_unresolved.append(label)
            continue

        # Извлекаем контур
        contours, _ = cv2.findContours(
            room_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE,
        )
        if not contours:
            still_unresolved.append(label)
            continue
        cnt = max(contours, key=cv2.contourArea)
        perimeter = cv2.arcLength(cnt, True)
        epsilon = POLY_EPSILON_FRACTION * perimeter
        approx = cv2.approxPolyDP(cnt, epsilon, True)
        polygon = [Point(x=float(p[0][0]), y=float(p[0][1])) for p in approx]

        if len(polygon) < 3:
            still_unresolved.append(label)
            continue

        # Centroid
        M = cv2.moments(cnt)
        if M["m00"] > 0:
            cx = M["m10"] / M["m00"]
            cy = M["m01"] / M["m00"]
        else:
            cx, cy = float(seed_x), float(seed_y)

        room_id = f"room_recovered_{next_idx:03d}"
        next_idx += 1

        room = Room(
            id=room_id,
            label=classify_room_by_area(
                area_m2=label.value_m2,
                area_px2=float(area_px),
                centroid=Point(x=cx, y=cy),
                img_area_px=img_area_px,
            ),
            area_m2=label.value_m2,
            area_px2=float(area_px),
            polygon=polygon,
            centroid=Point(x=round(cx, 1), y=round(cy, 1)),
            locked=True,
            confidence=0.85,  # recovered — чуть ниже чем у "primary"
        )
        recovered.append(room)
        logger.info(
            f"Recovery: восстановлена комната {room_id} ({label.value_m2}м², "
            f"area_px={area_px}, label='{label.raw_text}', "
            f"type={room.label.value})"
        )

    logger.info(
        f"Recovery: восстановлено {len(recovered)} комнат, "
        f"{len(still_unresolved)} меток остались без полигона"
    )

    return recovered, still_unresolved
