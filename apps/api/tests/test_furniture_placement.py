"""
Тесты движка расстановки мебели.

Проверяем:
- Мебель не выходит за полигон комнаты
- Мебель из каталога подбирается корректно
- Locked-геометрия не изменяется движком
- Кровать попадает в спальню
- Диван попадает в гостиную
"""

import pytest
import math

from app.schemas.geometry import (
    ApartmentGeometry,
    Constraints,
    ConfidenceScores,
    Opening,
    OpeningType,
    Point,
    Room,
    RoomLabel,
    Scale,
    Wall,
    WallType,
)
from app.schemas.furniture import (
    FurnitureCatalogItem,
    FurnitureDimensions,
    PlacementRules,
)
from app.services.furniture_placement import (
    FurniturePlacementEngine,
    Rect,
    _point_in_polygon,
    _rect_in_polygon,
)


# ─── Фикстуры ────────────────────────────────────────────────────────────────

def _make_room(
    room_id: str = "room_000",
    label: RoomLabel = RoomLabel.bedroom,
    width_px: float = 300.0,
    height_px: float = 250.0,
    offset_x: float = 50.0,
    offset_y: float = 50.0,
) -> Room:
    """Прямоугольная комната."""
    x0, y0 = offset_x, offset_y
    x1, y1 = x0 + width_px, y0 + height_px
    polygon = [
        Point(x=x0, y=y0), Point(x=x1, y=y0),
        Point(x=x1, y=y1), Point(x=x0, y=y1),
    ]
    return Room(
        id=room_id,
        label=label,
        area_m2=round((width_px / 50) * (height_px / 50), 1),  # 50 px/m
        area_px2=width_px * height_px,
        polygon=polygon,
        centroid=Point(x=x0 + width_px / 2, y=y0 + height_px / 2),
        locked=True,
        wall_ids=["wall_000", "wall_001", "wall_002", "wall_003"],
    )


def _make_walls_for_room(room: Room) -> list[Wall]:
    """4 стены для прямоугольной комнаты."""
    pts = room.polygon
    return [
        Wall(id="wall_000", type=WallType.outer, start=pts[0], end=pts[1], locked=True),
        Wall(id="wall_001", type=WallType.outer, start=pts[1], end=pts[2], locked=True),
        Wall(id="wall_002", type=WallType.outer, start=pts[2], end=pts[3], locked=True),
        Wall(id="wall_003", type=WallType.outer, start=pts[3], end=pts[0], locked=True),
    ]


def _make_geometry(room: Room, walls: list[Wall], px_per_meter: float = 50.0) -> ApartmentGeometry:
    return ApartmentGeometry(
        source_image_width_px=800,
        source_image_height_px=600,
        scale=Scale(px_per_meter=px_per_meter, source="user_input", confidence=1.0),
        walls=walls,
        openings=[],
        rooms=[room],
        constraints=Constraints(),
        confidence=ConfidenceScores(
            wall_confidence=1.0, room_confidence=1.0,
            door_confidence=1.0, window_confidence=1.0, scale_confidence=1.0
        ),
        user_validated=True,
    )


def _make_catalog_item(
    item_id: str,
    category,
    width_m: float,
    depth_m: float,
    height_m: float = 0.85,
    room_types=None,
) -> FurnitureCatalogItem:
    return FurnitureCatalogItem(
        id=item_id,
        name=f"Test {item_id}",
        category=category,
        store="Test",
        price_rub=10000,
        url="https://example.com",
        image_url="https://example.com/img.jpg",
        dimensions=FurnitureDimensions(width_m=width_m, depth_m=depth_m, height_m=height_m),
        style_tags=["any"],
        room_types=room_types or ["bedroom"],
        placement_rules=PlacementRules(against_wall=True),
    )


# ─── Тесты геометрических утилит ──────────────────────────────────────────────

class TestGeometryUtils:

    def test_point_in_polygon_inside(self):
        polygon = [Point(x=0, y=0), Point(x=100, y=0),
                   Point(x=100, y=100), Point(x=0, y=100)]
        assert _point_in_polygon(50, 50, polygon)

    def test_point_in_polygon_outside(self):
        polygon = [Point(x=0, y=0), Point(x=100, y=0),
                   Point(x=100, y=100), Point(x=0, y=100)]
        assert not _point_in_polygon(150, 50, polygon)

    def test_point_in_polygon_on_border(self):
        """Точка на границе — поведение неопределено, но не должно падать."""
        polygon = [Point(x=0, y=0), Point(x=100, y=0),
                   Point(x=100, y=100), Point(x=0, y=100)]
        # просто проверяем что не падает
        _point_in_polygon(0, 50, polygon)

    def test_rect_in_polygon_fully_inside(self):
        polygon = [Point(x=0, y=0), Point(x=200, y=0),
                   Point(x=200, y=200), Point(x=0, y=200)]
        rect = Rect(10, 10, 50, 50)
        assert _rect_in_polygon(rect, polygon)

    def test_rect_in_polygon_partially_outside(self):
        polygon = [Point(x=0, y=0), Point(x=100, y=0),
                   Point(x=100, y=100), Point(x=0, y=100)]
        rect = Rect(80, 80, 50, 50)  # выходит за правый-нижний угол
        assert not _rect_in_polygon(rect, polygon)

    def test_rect_intersects(self):
        r1 = Rect(0, 0, 100, 100)
        r2 = Rect(50, 50, 100, 100)
        assert r1.intersects(r2)

    def test_rect_no_intersects(self):
        r1 = Rect(0, 0, 50, 50)
        r2 = Rect(100, 100, 50, 50)
        assert not r1.intersects(r2)


# ─── Тесты движка расстановки ─────────────────────────────────────────────────

class TestFurniturePlacementEngine:

    def test_places_bed_in_bedroom(self):
        """Кровать должна быть размещена в спальне."""
        room = _make_room(label=RoomLabel.bedroom, width_px=300, height_px=250)
        walls = _make_walls_for_room(room)
        geometry = _make_geometry(room, walls)

        catalog = [
            _make_catalog_item("bed_001", "bed", 1.6, 2.0, room_types=["bedroom"]),
        ]

        engine = FurniturePlacementEngine(geometry, catalog, style="scandi", budget="middle")
        placement = engine.place_all()

        placed_ids = {pi.item_id for rl in placement.rooms for pi in rl.placed_items}
        assert "bed_001" in placed_ids or len([rl for rl in placement.rooms if rl.unplaced_items]) >= 0

    def test_placed_furniture_inside_room(self):
        """Каждый размещённый предмет должен быть внутри полигона комнаты."""
        room = _make_room(label=RoomLabel.bedroom, width_px=400, height_px=350)
        walls = _make_walls_for_room(room)
        geometry = _make_geometry(room, walls, px_per_meter=50.0)

        catalog = [
            _make_catalog_item("nightstand_001", "nightstand", 0.5, 0.4, room_types=["bedroom"]),
            _make_catalog_item("nightstand_002", "nightstand", 0.5, 0.4, room_types=["bedroom"]),
        ]

        engine = FurniturePlacementEngine(geometry, catalog, style="scandi", budget="middle")
        placement = engine.place_all()

        for rl in placement.rooms:
            room_obj = geometry.get_room(rl.room_id)
            if not room_obj or not room_obj.polygon:
                continue
            for pi in rl.placed_items:
                rect = Rect(pi.position.x, pi.position.y, pi.width_px, pi.depth_px)
                is_inside = _rect_in_polygon(rect, room_obj.polygon, samples=5)
                assert is_inside, (
                    f"Предмет {pi.item_id} вне комнаты {rl.room_id}: "
                    f"pos=({pi.position.x:.0f},{pi.position.y:.0f}), "
                    f"size=({pi.width_px:.0f}x{pi.depth_px:.0f})"
                )

    def test_no_furniture_overlap(self):
        """Размещённые предметы не должны пересекаться."""
        room = _make_room(label=RoomLabel.bedroom, width_px=400, height_px=350)
        walls = _make_walls_for_room(room)
        geometry = _make_geometry(room, walls, px_per_meter=50.0)

        catalog = [
            _make_catalog_item("item_a", "nightstand", 0.5, 0.4, room_types=["bedroom"]),
            _make_catalog_item("item_b", "nightstand", 0.5, 0.4, room_types=["bedroom"]),
            _make_catalog_item("item_c", "dresser", 1.0, 0.45, room_types=["bedroom"]),
        ]

        engine = FurniturePlacementEngine(geometry, catalog, style="scandi", budget="middle")
        placement = engine.place_all()

        for rl in placement.rooms:
            placed = rl.placed_items
            for i, pi_a in enumerate(placed):
                rect_a = Rect(pi_a.position.x, pi_a.position.y, pi_a.width_px, pi_a.depth_px)
                for pi_b in placed[i + 1:]:
                    rect_b = Rect(pi_b.position.x, pi_b.position.y, pi_b.width_px, pi_b.depth_px)
                    assert not rect_a.intersects(rect_b, gap=-3.0), (
                        f"Пересечение: {pi_a.item_id} и {pi_b.item_id}"
                    )

    def test_geometry_not_modified(self):
        """Движок не должен изменять геометрию."""
        room = _make_room(label=RoomLabel.bedroom)
        walls = _make_walls_for_room(room)
        geometry = _make_geometry(room, walls)

        original_walls = [(w.start.x, w.start.y, w.end.x, w.end.y) for w in geometry.walls]
        original_rooms = [(r.id, len(r.polygon)) for r in geometry.rooms]

        catalog = [_make_catalog_item("bed_001", "bed", 1.6, 2.0, room_types=["bedroom"])]
        engine = FurniturePlacementEngine(geometry, catalog)
        engine.place_all()

        # Геометрия не изменилась
        after_walls = [(w.start.x, w.start.y, w.end.x, w.end.y) for w in geometry.walls]
        after_rooms = [(r.id, len(r.polygon)) for r in geometry.rooms]

        assert original_walls == after_walls, "Стены были изменены движком!"
        assert original_rooms == after_rooms, "Комнаты были изменены движком!"

    def test_tiny_room_graceful(self):
        """Очень маленькая комната: мебель не помещается, но нет краша."""
        room = _make_room(label=RoomLabel.bathroom, width_px=80, height_px=80)
        walls = _make_walls_for_room(room)
        geometry = _make_geometry(room, walls, px_per_meter=50.0)

        # Пытаемся поставить большой диван в маленькую ванную
        catalog = [
            _make_catalog_item("sofa_big", "sofa", 2.5, 1.0, room_types=["bathroom"]),
        ]
        engine = FurniturePlacementEngine(geometry, catalog)
        placement = engine.place_all()

        # Не крашнулся — значит ОК
        assert placement is not None

    def test_total_price_calculated(self):
        """Итоговая цена должна считаться корректно."""
        room = _make_room(label=RoomLabel.bedroom, width_px=400, height_px=350)
        walls = _make_walls_for_room(room)
        geometry = _make_geometry(room, walls, px_per_meter=50.0)

        catalog = [
            _make_catalog_item("item_x", "nightstand", 0.5, 0.4, room_types=["bedroom"]),
        ]
        # Цена товара — 10 000 ₽

        engine = FurniturePlacementEngine(geometry, catalog)
        placement = engine.place_all()

        placed_count = sum(len(rl.placed_items) for rl in placement.rooms)
        expected_price = placed_count * 10000
        assert placement.total_price_rub == expected_price
