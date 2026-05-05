"""
Тесты валидатора расстановки мебели.

Проверяем:
- Существующий item_id → OK
- Несуществующий item_id → ERROR (AI-галлюцинация)
- Мебель вне комнаты → ERROR
- Пересечение предметов → ERROR
- Правильные размеры из каталога → OK
- Изменённые AI размеры → ERROR
"""

import pytest

from app.schemas.furniture import (
    FurnitureCatalogItem,
    FurnitureDimensions,
    FurniturePlacement,
    PlacedFurniture,
    PlacementRules,
    RoomLayout,
)
from app.schemas.geometry import (
    ApartmentGeometry,
    ConfidenceScores,
    Constraints,
    Opening,
    OpeningType,
    Point,
    Room,
    RoomLabel,
    Scale,
    Wall,
    WallType,
)
from app.services.layout_validator import validate_layout


# ─── Фикстуры ────────────────────────────────────────────────────────────────

def _rect_room(x0=50, y0=50, w=300, h=250) -> Room:
    return Room(
        id="room_000",
        label=RoomLabel.bedroom,
        area_m2=15.0,
        area_px2=w * h,
        polygon=[
            Point(x=x0, y=y0), Point(x=x0+w, y=y0),
            Point(x=x0+w, y=y0+h), Point(x=x0, y=y0+h),
        ],
        centroid=Point(x=x0 + w/2, y=y0 + h/2),
        locked=True,
        wall_ids=["wall_000"],
    )


def _simple_geometry(room: Room | None = None, px_per_meter: float = 50.0) -> ApartmentGeometry:
    r = room or _rect_room()
    return ApartmentGeometry(
        source_image_width_px=500,
        source_image_height_px=400,
        scale=Scale(px_per_meter=px_per_meter, source="user_input", confidence=1.0),
        walls=[Wall(id="wall_000", type=WallType.outer,
                    start=r.polygon[0], end=r.polygon[1], locked=True)],
        openings=[],
        rooms=[r],
        constraints=Constraints(),
        confidence=ConfidenceScores(
            wall_confidence=1.0, room_confidence=1.0,
            door_confidence=1.0, window_confidence=1.0, scale_confidence=1.0
        ),
        user_validated=True,
    )


def _catalog_item(item_id: str = "item_001",
                  width_m: float = 0.5, depth_m: float = 0.4) -> FurnitureCatalogItem:
    return FurnitureCatalogItem(
        id=item_id,
        name=f"Test {item_id}",
        category="nightstand",
        store="Test",
        price_rub=5000,
        url="",
        image_url="",
        dimensions=FurnitureDimensions(width_m=width_m, depth_m=depth_m, height_m=0.55),
        style_tags=["any"],
        room_types=["bedroom"],
        placement_rules=PlacementRules(),
    )


def _placed(item_id: str, x: float, y: float,
            w_px: float, d_px: float) -> PlacedFurniture:
    return PlacedFurniture(
        item_id=item_id, room_id="room_000",
        position=Point(x=x, y=y),
        rotation_deg=0.0,
        width_px=w_px, depth_px=d_px,
    )


def _placement(*placed_items: PlacedFurniture) -> FurniturePlacement:
    return FurniturePlacement(
        style="scandi", budget="middle",
        rooms=[RoomLayout(room_id="room_000", room_label="bedroom",
                          placed_items=list(placed_items))],
    )


# ─── Тесты ────────────────────────────────────────────────────────────────────

class TestLayoutValidator:

    def test_valid_placement_passes(self):
        """Корректная расстановка (1 предмет внутри комнаты) → valid=True."""
        geo = _simple_geometry()
        item = _catalog_item("item_001", 0.5, 0.4)
        # 0.5m * 50 px/m = 25px
        pi = _placed("item_001", 100, 100, 25, 20)
        pl = _placement(pi)

        result = validate_layout(geo, pl, [item])
        assert result.valid, f"Ожидалось valid=True, ошибки: {result.errors}"

    def test_nonexistent_item_id_is_error(self):
        """Несуществующий item_id = AI-галлюцинация → ERROR."""
        geo = _simple_geometry()
        catalog = [_catalog_item("real_item", 0.5, 0.4)]
        pi = _placed("fake_ai_item", 100, 100, 25, 20)
        pl = _placement(pi)

        result = validate_layout(geo, pl, catalog)
        assert not result.valid
        assert any("не найден в каталоге" in e for e in result.errors)

    def test_furniture_outside_room_is_error(self):
        """Мебель за пределами комнаты → ERROR."""
        geo = _simple_geometry()
        item = _catalog_item("item_001", 0.5, 0.4)
        # Комната: x=[50,350], y=[50,300]
        # Ставим за пределами
        pi = _placed("item_001", 400, 400, 25, 20)
        pl = _placement(pi)

        result = validate_layout(geo, pl, [item])
        assert not result.valid
        assert any("выходит за границы" in e for e in result.errors)

    def test_overlapping_furniture_is_error(self):
        """Два пересекающихся предмета → ERROR."""
        geo = _simple_geometry()
        item_a = _catalog_item("item_a", 0.5, 0.4)
        item_b = _catalog_item("item_b", 0.5, 0.4)

        # Ставим в одно место (пересечение)
        pi_a = _placed("item_a", 100, 100, 25, 20)
        pi_b = _placed("item_b", 102, 102, 25, 20)  # почти то же место
        pl = _placement(pi_a, pi_b)

        result = validate_layout(geo, pl, [item_a, item_b])
        assert not result.valid
        assert any("пересекается" in e for e in result.errors)

    def test_correct_dimensions_pass(self):
        """Размеры совпадают с каталогом → нет ошибок по размерам."""
        geo = _simple_geometry(px_per_meter=50.0)
        item = _catalog_item("item_001", width_m=0.5, depth_m=0.4)
        # 0.5m * 50px/m = 25px, 0.4m * 50px/m = 20px
        pi = _placed("item_001", 100, 100, 25.0, 20.0)
        pl = _placement(pi)

        result = validate_layout(geo, pl, [item])
        dim_errors = [e for e in result.errors if "не соответствует каталогу" in e]
        assert len(dim_errors) == 0, f"Ошибки размеров: {dim_errors}"

    def test_wrong_dimensions_are_error(self):
        """AI изменил размеры предмета → ERROR."""
        geo = _simple_geometry(px_per_meter=50.0)
        item = _catalog_item("item_001", width_m=0.5, depth_m=0.4)
        # Правильно: 25x20px, AI поставил 60x20px (изменил ширину)
        pi = _placed("item_001", 100, 100, 60.0, 20.0)
        pl = _placement(pi)

        result = validate_layout(geo, pl, [item])
        dim_errors = [e for e in result.errors if "не соответствует каталогу" in e]
        assert len(dim_errors) > 0, "Должны быть ошибки размеров"

    def test_door_clearance_violation_is_error(self):
        """Мебель блокирует дверь → ERROR."""
        from app.schemas.geometry import Opening, OpeningType, SwingDirection

        room = _rect_room(x0=50, y0=50, w=300, h=250)
        # Дверь на стене wall_000
        door = Opening(
            id="door_000",
            type=OpeningType.door,
            wall_id="wall_000",
            position=Point(x=200, y=50),
            width_px=40,
            clearance_m=0.8,
            locked=True,
        )

        geo = ApartmentGeometry(
            source_image_width_px=500,
            source_image_height_px=400,
            scale=Scale(px_per_meter=50.0, source="user_input", confidence=1.0),
            walls=[Wall(id="wall_000", type=WallType.outer,
                        start=room.polygon[0], end=room.polygon[1], locked=True)],
            openings=[door],
            rooms=[room],
            constraints=Constraints(do_not_block_doors=True),
            confidence=ConfidenceScores(
                wall_confidence=1.0, room_confidence=1.0,
                door_confidence=1.0, window_confidence=1.0, scale_confidence=1.0
            ),
            user_validated=True,
        )
        room.wall_ids = ["wall_000"]
        room.opening_ids = ["door_000"]

        item = _catalog_item("item_001", 0.5, 0.4)
        # Ставим прямо в зону двери
        pi = _placed("item_001", 180, 20, 25, 20)
        pl = _placement(pi)

        result = validate_layout(geo, pl, [item])
        door_errors = [e for e in result.errors if "блокирует зону двери" in e]
        assert len(door_errors) > 0, f"Ошибки двери не найдены, все ошибки: {result.errors}"

    def test_empty_placement_is_valid(self):
        """Пустая расстановка (нет мебели) → valid=True."""
        geo = _simple_geometry()
        pl = FurniturePlacement(
            style="scandi", budget="middle",
            rooms=[RoomLayout(room_id="room_000", room_label="bedroom")],
        )
        result = validate_layout(geo, pl, [])
        assert result.valid
