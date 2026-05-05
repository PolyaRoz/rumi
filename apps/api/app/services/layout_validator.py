"""
Валидатор расстановки мебели.

Проверяет:
1. Геометрическая корректность — мебель не выходит за границы комнаты
2. Пересечения — мебель не пересекается с другой мебелью или стенами
3. Clearance constraints — соблюдены минимальные проходы
4. Блокировка дверей — зоны открывания дверей свободны
5. Каталог — все item_id существуют и размеры совпадают с каталогом
6. Размеры — AI не изменил размеры предметов (главная защита от галлюцинаций)

Возвращает ValidationResult с флагом valid, списком ошибок и предупреждений.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

from app.schemas.furniture import FurnitureCatalogItem, FurniturePlacement, PlacedFurniture
from app.schemas.geometry import ApartmentGeometry, OpeningType, Point, Room
from app.services.furniture_placement import Rect, _point_in_polygon, _rect_in_polygon

logger = logging.getLogger(__name__)

DIMENSION_TOLERANCE = 0.05   # допуск 5% для сравнения размеров из каталога и placement
SIZE_MISMATCH_TOLERANCE_PX_RATIO = 0.10  # допуск 10% на пересчёт px


@dataclass
class ValidationResult:
    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        self.valid = False

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)


def validate_layout(
    geometry: ApartmentGeometry,
    placement: FurniturePlacement,
    catalog: list[FurnitureCatalogItem],
) -> ValidationResult:
    """
    Полная валидация расстановки мебели.

    Args:
        geometry: заблокированная геометрия квартиры
        placement: результат layout-engine
        catalog: полный каталог для проверки item_id и размеров

    Returns:
        ValidationResult
    """
    result = ValidationResult()
    catalog_index = {item.id: item for item in catalog}
    px_per_meter = geometry.scale.px_per_meter or 50.0

    for room_layout in placement.rooms:
        room = geometry.get_room(room_layout.room_id)
        if room is None:
            result.add_error(f"Комната {room_layout.room_id} не найдена в геометрии")
            continue

        placed_rects: list[tuple[PlacedFurniture, Rect]] = []

        for pi in room_layout.placed_items:

            # ── 1. Проверка существования в каталоге ────────────────────────
            catalog_item = catalog_index.get(pi.item_id)
            if catalog_item is None:
                result.add_error(
                    f"[{room_layout.room_label}] Товар {pi.item_id!r} не найден в каталоге. "
                    "AI возможно придумал несуществующий ID."
                )
                continue

            # ── 2. Проверка размеров (защита от AI-галлюцинаций) ────────────
            expected_w_px = catalog_item.dimensions.width_m * px_per_meter
            expected_d_px = catalog_item.dimensions.depth_m * px_per_meter
            tol = SIZE_MISMATCH_TOLERANCE_PX_RATIO

            actual_w = pi.width_px if pi.rotation_deg in (0, 180) else pi.depth_px
            actual_d = pi.depth_px if pi.rotation_deg in (0, 180) else pi.width_px

            if abs(actual_w - expected_w_px) / (expected_w_px + 1e-6) > tol:
                result.add_error(
                    f"[{room_layout.room_label}] '{catalog_item.name}': "
                    f"ширина {actual_w:.0f}px не соответствует каталогу {expected_w_px:.0f}px. "
                    "Размер не должен изменяться AI."
                )

            if abs(actual_d - expected_d_px) / (expected_d_px + 1e-6) > tol:
                result.add_error(
                    f"[{room_layout.room_label}] '{catalog_item.name}': "
                    f"глубина {actual_d:.0f}px не соответствует каталогу {expected_d_px:.0f}px. "
                    "Размер не должен изменяться AI."
                )

            rect = Rect(pi.position.x, pi.position.y, pi.width_px, pi.depth_px)

            # ── 3. Мебель внутри комнаты ─────────────────────────────────────
            if room.polygon:
                if not _rect_in_polygon(rect, room.polygon, samples=5):
                    result.add_error(
                        f"[{room_layout.room_label}] '{catalog_item.name}' "
                        f"выходит за границы комнаты {room.id}"
                    )

            # ── 4. Пересечения с другой мебелью ──────────────────────────────
            for other_pi, other_rect in placed_rects:
                if rect.intersects(other_rect, gap=-2.0):  # небольшой допуск на пиксельное дрожание
                    other_item = catalog_index.get(other_pi.item_id)
                    other_name = other_item.name if other_item else other_pi.item_id
                    result.add_error(
                        f"[{room_layout.room_label}] '{catalog_item.name}' "
                        f"пересекается с '{other_name}'"
                    )

            placed_rects.append((pi, rect))

        # ── 5. Блокировка дверей ──────────────────────────────────────────────
        if geometry.constraints.do_not_block_doors:
            doors = [o for o in geometry.openings if o.type == OpeningType.door]
            for door in doors:
                if door.wall_id not in (room.wall_ids or []):
                    continue
                clearance_px = door.clearance_m * px_per_meter
                hw = door.width_px / 2
                door_zone = Rect(
                    door.position.x - hw - clearance_px,
                    door.position.y - clearance_px,
                    hw * 2 + clearance_px * 2,
                    clearance_px * 2,
                )
                for pi, rect in placed_rects:
                    catalog_item = catalog_index.get(pi.item_id)
                    name = catalog_item.name if catalog_item else pi.item_id
                    if rect.intersects(door_zone):
                        result.add_error(
                            f"[{room_layout.room_label}] '{name}' блокирует зону двери {door.id}"
                        )

        # ── 6. Проверка минимальных проходов ─────────────────────────────────
        min_walkway_px = geometry.constraints.keep_walkway_width_m * px_per_meter
        _check_walkways(room, placed_rects, min_walkway_px, result, room_layout.room_label)

    placement.validated = result.valid
    placement.validation_errors = result.errors

    logger.info(
        f"Валидация: valid={result.valid}, "
        f"errors={len(result.errors)}, warnings={len(result.warnings)}"
    )
    return result


def _check_walkways(
    room: Room,
    placed_rects: list[tuple[PlacedFurniture, Rect]],
    min_walkway_px: float,
    result: ValidationResult,
    room_label: str,
) -> None:
    """
    Упрощённая проверка проходов:
    Для каждой пары предметов проверяем, что расстояние между ними >= min_walkway_px.
    Это не идеально (не учитывает топологию), но достаточно для MVP.
    """
    for i, (pi_a, rect_a) in enumerate(placed_rects):
        for pi_b, rect_b in placed_rects[i + 1:]:
            # Расстояние между прямоугольниками
            gap_x = max(0.0, max(rect_a.x, rect_b.x) - min(rect_a.x2, rect_b.x2))
            gap_y = max(0.0, max(rect_a.y, rect_b.y) - min(rect_a.y2, rect_b.y2))
            # Зазор = минимальный из двух осей (если прямоугольники вытянуты)
            gap = min(gap_x, gap_y) if gap_x > 0 and gap_y > 0 else max(gap_x, gap_y)

            if 0 < gap < min_walkway_px * 0.7:  # допуск 30%
                result.add_warning(
                    f"[{room_label}] Узкий проход между предметами: "
                    f"{gap:.0f}px < {min_walkway_px:.0f}px (минимум)"
                )
