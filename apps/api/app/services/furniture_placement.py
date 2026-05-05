"""
Движок расстановки мебели (Rule-Based Placement Engine).

Принципы:
1. Геометрия LOCKED — стены, комнаты, двери, окна НЕ изменяются
2. Мебель берётся только из каталога с реальными размерами
3. Каждый предмет проверяется: не выходит за границы комнаты,
   не пересекает другую мебель, не блокирует двери/проходы
4. Правила приоритета (bedroom): кровать → тумбы → шкаф → кресло → ковёр
5. Правила приоритета (living_room): диван → ковёр → кресло → тумба ТВ

Алгоритм:
- Для каждой комнаты подбираем набор мебели из каталога
- Для каждого предмета ищем позицию методом grid-search вдоль стен
- Проверяем clearance constraints
- Записываем результат в FurniturePlacement
"""

from __future__ import annotations

import logging
import math
from typing import Iterator

import numpy as np

from app.schemas.furniture import (
    CategoryKey,
    FurnitureCatalogItem,
    FurniturePlacement,
    PlacedFurniture,
    RoomLayout,
    RoomTypeKey,
)
from app.schemas.geometry import ApartmentGeometry, Opening, OpeningType, Point, Room, Wall

logger = logging.getLogger(__name__)

# ─── Типы комнат → приоритетные категории мебели ────────────────────────────

_ROOM_FURNITURE_PLAN: dict[RoomTypeKey, list[CategoryKey]] = {
    "living_room": ["sofa", "rug", "armchair", "tv_unit", "ottoman"],
    "bedroom":     ["bed", "nightstand", "nightstand", "wardrobe", "dresser", "rug"],
    "kids_room":   ["bed", "wardrobe", "desk", "bookshelf", "rug", "armchair"],
    "kitchen":     ["kitchen_set", "table", "chair", "chair", "chair", "chair"],
    "bathroom":    ["bathroom_fixture", "bathtub"],
    "toilet":      ["toilet"],
    "corridor":    ["wardrobe", "ottoman"],
    "storage":     ["wardrobe"],
    "balcony":     [],
    "unknown":     ["sofa", "armchair"],
}

GRID_STEP_M = 0.1          # шаг сетки для поиска позиции (10 см)
ROTATIONS = [0, 90, 180, 270]   # углы поворота мебели


# ─── Геометрические утилиты ──────────────────────────────────────────────────

class Rect:
    """Прямоугольник в пикселях (для проверки пересечений)."""
    __slots__ = ("x", "y", "w", "h")

    def __init__(self, x: float, y: float, w: float, h: float):
        self.x = x
        self.y = y
        self.w = w
        self.h = h

    @property
    def x2(self) -> float:
        return self.x + self.w

    @property
    def y2(self) -> float:
        return self.y + self.h

    def intersects(self, other: "Rect", gap: float = 0.0) -> bool:
        return (
            self.x < other.x2 + gap and
            self.x2 > other.x - gap and
            self.y < other.y2 + gap and
            self.y2 > other.y - gap
        )

    def expanded(self, margin: float) -> "Rect":
        return Rect(self.x - margin, self.y - margin, self.w + 2 * margin, self.h + 2 * margin)

    def center(self) -> tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2


def _rotated_size(width_px: float, depth_px: float, rotation: int) -> tuple[float, float]:
    """Вернуть (w, h) с учётом поворота."""
    if rotation in (0, 180):
        return width_px, depth_px
    return depth_px, width_px


def _point_in_polygon(px: float, py: float, polygon: list[Point]) -> bool:
    """Ray-casting алгоритм: точка внутри полигона."""
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i].x, polygon[i].y
        xj, yj = polygon[j].x, polygon[j].y
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi + 1e-10) + xi):
            inside = not inside
        j = i
    return inside


def _rect_in_polygon(rect: Rect, polygon: list[Point], samples: int = 9) -> bool:
    """Проверить, лежит ли прямоугольник целиком внутри полигона."""
    test_points = [
        (rect.x + rect.w * sx / (samples - 1), rect.y + rect.h * sy / (samples - 1))
        for sx in range(samples)
        for sy in range(samples)
    ]
    return all(_point_in_polygon(px, py, polygon) for px, py in test_points)


def _door_clearance_rect(door: Opening, px_per_meter: float) -> Rect | None:
    """Зона запрета перед дверью (прямоугольник clearance_m)."""
    if door.width_px <= 0:
        return None
    clearance_px = door.clearance_m * px_per_meter
    hw = door.width_px / 2
    return Rect(
        door.position.x - hw - clearance_px,
        door.position.y - clearance_px,
        hw * 2 + clearance_px * 2,
        clearance_px * 2,
    )


def _wall_positions(
    wall: Wall,
    item_w_px: float,
    item_d_px: float,
    room_polygon: list[Point],
    step_px: float,
) -> Iterator[tuple[float, float]]:
    """
    Сгенерировать кандидатные позиции вдоль стены.
    Мебель ставится вплотную к стене (offset = 0).
    """
    sx, sy = wall.start.x, wall.start.y
    ex, ey = wall.end.x, wall.end.y
    length = math.hypot(ex - sx, ey - sy)
    if length < item_w_px:
        return

    # Вектор вдоль стены и перпендикуляр (в сторону комнаты)
    ux = (ex - sx) / length
    uy = (ey - sy) / length

    # Перпендикуляр: поворот на 90° вправо
    nx = -uy
    ny = ux

    # Проверяем, что перпендикуляр указывает внутрь комнаты
    mid_x = (sx + ex) / 2
    mid_y = (sy + ey) / 2
    test_x = mid_x + nx * item_d_px / 2
    test_y = mid_y + ny * item_d_px / 2
    if not _point_in_polygon(test_x, test_y, room_polygon):
        nx, ny = -nx, -ny  # разворачиваем

    t = 0.0
    while t + item_w_px <= length:
        x0 = sx + ux * t
        y0 = sy + uy * t
        x_item = x0
        y_item = y0
        # Смещение в глубину: предмет стоит вплотную к стене
        # (левый нижний угол прямоугольника в системе координат изображения)
        # Для простоты возвращаем начальный угол
        yield x_item, y_item
        t += step_px


# ─── Основной движок ─────────────────────────────────────────────────────────

class FurniturePlacementEngine:

    def __init__(
        self,
        geometry: ApartmentGeometry,
        catalog: list[FurnitureCatalogItem],
        style: str = "scandi",
        budget: str = "middle",
    ):
        self.geometry = geometry
        self.catalog = catalog
        self.style = style
        self.budget = budget
        self.px_per_meter = geometry.scale.px_per_meter or 50.0

    def _m_to_px(self, m: float) -> float:
        return m * self.px_per_meter

    def _select_items_for_room(
        self,
        room: Room,
        room_type: RoomTypeKey,
        already_used_ids: set[str],
    ) -> list[FurnitureCatalogItem]:
        """Выбрать набор мебели для комнаты из каталога."""
        from app.services.furniture_catalog import filter_catalog

        plan = _ROOM_FURNITURE_PLAN.get(room_type, ["armchair"])
        selected: list[FurnitureCatalogItem] = []

        for category in plan:
            available = filter_catalog(
                self.catalog, room_type, self.budget, self.style,
                categories=[category],
            )
            # Исключаем уже используемые
            available = [i for i in available if i.id not in already_used_ids]
            if not available:
                continue
            # Берём лучший вариант (первый после сортировки)
            item = available[0]
            selected.append(item)
            already_used_ids.add(item.id)

        return selected

    def _get_room_doors(self, room: Room) -> list[Opening]:
        """Вернуть двери, относящиеся к этой комнате."""
        door_ids = set(room.opening_ids)
        return [
            o for o in self.geometry.openings
            if o.id in door_ids and o.type == OpeningType.door
        ]

    def _get_room_walls(self, room: Room) -> list[Wall]:
        """Вернуть стены комнаты."""
        wall_ids = set(room.wall_ids)
        # Если wall_ids не заполнен — берём все стены
        if not wall_ids:
            return self.geometry.walls
        return [w for w in self.geometry.walls if w.id in wall_ids]

    def _try_place_item(
        self,
        item: FurnitureCatalogItem,
        room: Room,
        placed_rects: list[Rect],
        door_clearance_rects: list[Rect],
    ) -> PlacedFurniture | None:
        """
        Найти допустимую позицию для предмета в комнате.

        Пробуем позиции вдоль каждой стены, каждый угол поворота.
        Возвращаем первую допустимую позицию или None.
        """
        walls = self._get_room_walls(room)
        step_px = self._m_to_px(GRID_STEP_M)

        for rotation in ROTATIONS:
            w_px = self._m_to_px(item.dimensions.width_m)
            d_px = self._m_to_px(item.dimensions.depth_m)
            rw, rh = _rotated_size(w_px, d_px, rotation)

            if item.placement_rules.against_wall:
                for wall in walls:
                    for x, y in _wall_positions(wall, rw, rh, room.polygon, step_px):
                        rect = Rect(x, y, rw, rh)
                        if self._is_valid_placement(rect, room, placed_rects, door_clearance_rects):
                            return PlacedFurniture(
                                item_id=item.id,
                                room_id=room.id,
                                position=Point(x=round(x, 1), y=round(y, 1)),
                                rotation_deg=float(rotation),
                                width_px=round(rw, 1),
                                depth_px=round(rh, 1),
                            )
            else:
                # Свободностоящая: пробуем центр комнаты и окрестность
                for candidate in self._free_standing_candidates(room, rw, rh, step_px):
                    rect = Rect(candidate[0], candidate[1], rw, rh)
                    if self._is_valid_placement(rect, room, placed_rects, door_clearance_rects):
                        return PlacedFurniture(
                            item_id=item.id,
                            room_id=room.id,
                            position=Point(x=round(candidate[0], 1), y=round(candidate[1], 1)),
                            rotation_deg=float(rotation),
                            width_px=round(rw, 1),
                            depth_px=round(rh, 1),
                        )

        return None

    def _free_standing_candidates(
        self, room: Room, w: float, h: float, step: float
    ) -> Iterator[tuple[float, float]]:
        """Кандидатные позиции для свободностоящей мебели (от центра к краям)."""
        if not room.centroid:
            return
        cx, cy = room.centroid.x, room.centroid.y
        # Спираль от центра
        for r in np.arange(0, 200, step):
            for angle in np.linspace(0, 2 * math.pi, max(4, int(r / step) + 4), endpoint=False):
                x = cx + r * math.cos(angle) - w / 2
                y = cy + r * math.sin(angle) - h / 2
                yield x, y

    def _is_valid_placement(
        self,
        rect: Rect,
        room: Room,
        placed_rects: list[Rect],
        door_clearance_rects: list[Rect],
    ) -> bool:
        """Проверить все ограничения для прямоугольника мебели."""
        constraints = self.geometry.constraints

        # 1. Прямоугольник должен быть внутри комнаты
        if not _rect_in_polygon(rect, room.polygon):
            return False

        # 2. Не пересекаться с уже размещённой мебелью
        for placed in placed_rects:
            if rect.intersects(placed, gap=self._m_to_px(0.05)):
                return False

        # 3. Не блокировать двери (clearance зоны)
        if constraints.do_not_block_doors:
            for dc in door_clearance_rects:
                if rect.intersects(dc):
                    return False

        return True

    def place_all(self) -> FurniturePlacement:
        """Расставить мебель во всех комнатах."""
        result = FurniturePlacement(
            style=self.style,
            budget=self.budget,
        )
        already_used_ids: set[str] = set()

        for room in self.geometry.rooms:
            room_type: RoomTypeKey = room.label.value  # type: ignore[assignment]
            if room_type not in _ROOM_FURNITURE_PLAN:
                room_type = "unknown"

            layout = self._place_room(room, room_type, already_used_ids)
            result.rooms.append(layout)
            # Обновляем использованные ID
            already_used_ids.update(pi.item_id for pi in layout.placed_items)

        # Итоговая цена
        catalog_by_id = {i.id: i for i in self.catalog}
        total = 0
        for rl in result.rooms:
            for pi in rl.placed_items:
                item = catalog_by_id.get(pi.item_id)
                if item:
                    total += item.price_rub
        result.total_price_rub = total

        return result

    def _place_room(
        self,
        room: Room,
        room_type: RoomTypeKey,
        already_used_ids: set[str],
    ) -> RoomLayout:
        layout = RoomLayout(room_id=room.id, room_label=room.label.value)

        if not room.polygon:
            layout.warnings.append("Нет полигона комнаты — пропускаем")
            return layout

        items = self._select_items_for_room(room, room_type, already_used_ids)
        if not items:
            layout.warnings.append(f"Нет мебели в каталоге для {room_type}")
            return layout

        placed_rects: list[Rect] = []

        # Предвычислим зоны запрета дверей
        doors = self._get_room_doors(room)
        door_clearance_rects: list[Rect] = []
        if self.geometry.constraints.do_not_block_doors:
            for door in doors:
                dc = _door_clearance_rect(door, self.px_per_meter)
                if dc:
                    door_clearance_rects.append(dc)

        for item in items:
            placed = self._try_place_item(item, room, placed_rects, door_clearance_rects)
            if placed:
                layout.placed_items.append(placed)
                placed_rects.append(
                    Rect(placed.position.x, placed.position.y,
                         placed.width_px, placed.depth_px)
                )
                logger.debug(f"  ✓ {item.name} → ({placed.position.x:.0f}, {placed.position.y:.0f})")
            else:
                layout.unplaced_items.append(item.id)
                layout.warnings.append(f"Не удалось разместить: {item.name}")
                logger.debug(f"  ✗ {item.name} — не поместилась")

        logger.info(
            f"Комната {room.id} ({room_type}): "
            f"{len(layout.placed_items)}/{len(items)} предметов размещено"
        )
        return layout
