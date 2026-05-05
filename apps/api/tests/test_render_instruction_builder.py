"""
Тесты построителя render-инструкций.

Проверяем:
- Render-style FIXED — не зависит от user-style (правило F)
- Один и тот же geometry+placement → один и тот же seed (детерминизм)
- Разные user-style → одинаковый render-style, разные палитры (правило G)
- Negative prompt запрещает изменение геометрии
- Размеры мебели включаются в промпт (правило E)
- Промпт ссылается на validated catalog items (правило D)
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
    Point,
    Room,
    RoomLabel,
    Scale,
    Wall,
    WallType,
)
from app.services.render_instruction_builder import (
    FIXED_NEGATIVE,
    RENDER_STYLE_PER_ROOM_PHOTO,
    RENDER_STYLE_TOP_DOWN_3D,
    STYLE_MATERIALS,
    build_per_room_photo_instruction,
    build_top_down_3d_instruction,
    deterministic_seed,
)


# ─── Фикстуры ────────────────────────────────────────────────────────────────

def _bedroom() -> Room:
    return Room(
        id="room_000",
        label=RoomLabel.bedroom,
        area_m2=14.5,
        polygon=[Point(x=0, y=0), Point(x=300, y=0),
                 Point(x=300, y=200), Point(x=0, y=200)],
        centroid=Point(x=150, y=100),
        wall_ids=["wall_000"],
    )


def _make_geometry() -> ApartmentGeometry:
    walls = [
        Wall(id="wall_000", type=WallType.outer,
             start=Point(x=0, y=0), end=Point(x=300, y=0))
    ]
    return ApartmentGeometry(
        source_image_width_px=400,
        source_image_height_px=300,
        scale=Scale(px_per_meter=50.0, source="user_input", confidence=1.0),
        walls=walls,
        openings=[],
        rooms=[_bedroom()],
        constraints=Constraints(),
        confidence=ConfidenceScores(
            wall_confidence=1.0, room_confidence=1.0,
            door_confidence=1.0, window_confidence=1.0, scale_confidence=1.0,
        ),
        user_validated=True,
    )


def _bed() -> FurnitureCatalogItem:
    return FurnitureCatalogItem(
        id="bed_001", name="Bed Stockholm",
        category="bed", store="Hoff", price_rub=39990,
        url="https://example.com", image_url="https://example.com/img.jpg",
        dimensions=FurnitureDimensions(width_m=1.6, depth_m=2.0, height_m=0.5),
        style_tags=["scandi"], room_types=["bedroom"],
        placement_rules=PlacementRules(),
    )


def _make_placement(item_id: str = "bed_001") -> FurniturePlacement:
    return FurniturePlacement(
        style="scandi", budget="middle",
        rooms=[RoomLayout(
            room_id="room_000", room_label="bedroom",
            placed_items=[PlacedFurniture(
                item_id=item_id, room_id="room_000",
                position=Point(x=20, y=20), rotation_deg=0,
                width_px=80, depth_px=100,
            )],
        )],
        validated=True,
    )


# ─── Тесты ────────────────────────────────────────────────────────────────────

class TestDeterministicSeed:

    def test_same_inputs_same_seed(self):
        """Один и тот же ввод → одинаковый seed."""
        s1 = deterministic_seed("geo_a", "layout_b", "scandi")
        s2 = deterministic_seed("geo_a", "layout_b", "scandi")
        assert s1 == s2

    def test_different_inputs_different_seed(self):
        """Разный ввод → разный seed."""
        s1 = deterministic_seed("geo_a", "layout_b", "scandi")
        s2 = deterministic_seed("geo_a", "layout_b", "loft")
        assert s1 != s2

    def test_seed_is_int(self):
        s = deterministic_seed("a", "b", "c")
        assert isinstance(s, int)
        assert s > 0


class TestRenderStyleFixed:

    def test_fixed_render_strings_dont_contain_user_style(self):
        """В шаблоне render-style НЕ должно быть упоминания user-style."""
        for style in ["scandi", "minimal", "loft", "classic"]:
            assert style not in RENDER_STYLE_TOP_DOWN_3D.lower()
            assert style not in RENDER_STYLE_PER_ROOM_PHOTO.lower()

    def test_top_down_uses_isometric_keyword(self):
        """Top-down render должен содержать слово 'isometric' / 'axonometric'."""
        text = RENDER_STYLE_TOP_DOWN_3D.lower()
        assert "isometric" in text or "axonometric" in text

    def test_fixed_negative_forbids_geometry_changes(self):
        """Negative prompt должен запрещать изменение геометрии."""
        text = FIXED_NEGATIVE.lower()
        assert "moved walls" in text or "additional walls" in text
        assert "moved windows" in text
        assert "repositioned doors" in text or "extra doors" in text

    def test_fixed_negative_forbids_text(self):
        """Negative prompt должен запрещать текст и метки."""
        text = FIXED_NEGATIVE.lower()
        assert "text" in text
        assert "labels" in text
        assert "numbers" in text


class TestPerRoomInstruction:

    def test_render_style_first_in_prompt(self):
        """ФИКСИРОВАННЫЙ render-style должен быть в начале промпта."""
        layout = _make_placement().rooms[0]
        inst = build_per_room_photo_instruction(
            _bedroom(), layout, [_bed()], "scandi"
        )
        # Первые 50 символов промпта должны совпадать с шаблоном
        assert inst.prompt.startswith(RENDER_STYLE_PER_ROOM_PHOTO[:50])

    def test_user_style_changes_palette_only(self):
        """User-style меняет ТОЛЬКО палитру, не render-format."""
        layout = _make_placement().rooms[0]
        inst_a = build_per_room_photo_instruction(
            _bedroom(), layout, [_bed()], "scandi"
        )
        inst_b = build_per_room_photo_instruction(
            _bedroom(), layout, [_bed()], "loft"
        )

        # Render-style части одинаковы
        assert RENDER_STYLE_PER_ROOM_PHOTO[:80] in inst_a.prompt
        assert RENDER_STYLE_PER_ROOM_PHOTO[:80] in inst_b.prompt

        # Палитры разные
        assert STYLE_MATERIALS["scandi"][:30] in inst_a.prompt
        assert STYLE_MATERIALS["loft"][:30] in inst_b.prompt
        assert STYLE_MATERIALS["scandi"][:30] not in inst_b.prompt

    def test_furniture_dimensions_in_prompt(self):
        """Размеры мебели должны быть в промпте (правило E)."""
        layout = _make_placement().rooms[0]
        inst = build_per_room_photo_instruction(
            _bedroom(), layout, [_bed()], "scandi"
        )
        # Размеры из каталога: 1.6×2.0
        assert "1.6" in inst.prompt
        assert "2.0" in inst.prompt

    def test_seed_deterministic_for_same_layout(self):
        """Тот же room + те же items → тот же seed."""
        layout = _make_placement().rooms[0]
        inst_1 = build_per_room_photo_instruction(_bedroom(), layout, [_bed()], "scandi")
        inst_2 = build_per_room_photo_instruction(_bedroom(), layout, [_bed()], "scandi")
        assert inst_1.seed == inst_2.seed

    def test_seed_changes_with_different_items(self):
        """Разные мебельные items → разный seed."""
        item_a = _bed()
        item_b = FurnitureCatalogItem(
            id="other_bed", name="Other Bed",
            category="bed", store="Hoff", price_rub=10000,
            url="", image_url="",
            dimensions=FurnitureDimensions(width_m=1.4, depth_m=1.9, height_m=0.4),
            style_tags=["any"], room_types=["bedroom"],
        )
        layout_a = RoomLayout(
            room_id="room_000", room_label="bedroom",
            placed_items=[PlacedFurniture(
                item_id="bed_001", room_id="room_000",
                position=Point(x=0, y=0), rotation_deg=0,
                width_px=80, depth_px=100,
            )],
        )
        layout_b = RoomLayout(
            room_id="room_000", room_label="bedroom",
            placed_items=[PlacedFurniture(
                item_id="other_bed", room_id="room_000",
                position=Point(x=0, y=0), rotation_deg=0,
                width_px=70, depth_px=95,
            )],
        )
        inst_a = build_per_room_photo_instruction(_bedroom(), layout_a, [item_a], "scandi")
        inst_b = build_per_room_photo_instruction(_bedroom(), layout_b, [item_b], "scandi")
        assert inst_a.seed != inst_b.seed

    def test_negative_prompt_attached(self):
        """Negative prompt должен быть приложен."""
        layout = _make_placement().rooms[0]
        inst = build_per_room_photo_instruction(_bedroom(), layout, [_bed()], "scandi")
        assert inst.negative_prompt == FIXED_NEGATIVE

    def test_locked_constraints_listed(self):
        """Locked-ограничения должны быть перечислены в результате."""
        layout = _make_placement().rooms[0]
        inst = build_per_room_photo_instruction(_bedroom(), layout, [_bed()], "scandi")
        assert any("room_type=bedroom" in c for c in inst.locked_constraints)
        assert any("items=" in c for c in inst.locked_constraints)


class TestTopDown3DInstruction:

    def test_locked_constraints_summarize_geometry(self):
        """Top-down инструкция должна явно сообщать AI о locked-геометрии."""
        geo = _make_geometry()
        pl = _make_placement()
        inst = build_top_down_3d_instruction(geo, pl, [_bed()], "scandi")

        assert any("walls=" in c and "locked" in c for c in inst.locked_constraints)
        assert any("rooms=" in c and "locked" in c for c in inst.locked_constraints)

    def test_prompt_states_walls_locked(self):
        """Промпт должен содержать явное указание AI не менять walls/doors/windows."""
        geo = _make_geometry()
        pl = _make_placement()
        inst = build_top_down_3d_instruction(geo, pl, [_bed()], "scandi")
        text = inst.prompt.lower()
        assert "locked" in text
        assert "preserved" in text or "must not be changed" in text

    def test_furniture_from_catalog_referenced(self):
        """Промпт должен ссылаться на real catalog items (not generic)."""
        geo = _make_geometry()
        pl = _make_placement()
        inst = build_top_down_3d_instruction(geo, pl, [_bed()], "scandi")
        assert "real products" in inst.prompt.lower() or "catalog" in inst.prompt.lower()

    def test_strength_low_when_reference_provided(self):
        """При наличии reference image strength должен быть низким (не img2img-перерисовка)."""
        geo = _make_geometry()
        pl = _make_placement()
        inst = build_top_down_3d_instruction(
            geo, pl, [_bed()], "scandi",
            reference_image_url="data:image/png;base64,..."
        )
        assert inst.strength is not None
        assert inst.strength <= 0.30, f"Strength слишком высокий: {inst.strength}"

    def test_strength_none_when_no_reference(self):
        """Без reference image → text2img (strength=None)."""
        geo = _make_geometry()
        pl = _make_placement()
        inst = build_top_down_3d_instruction(geo, pl, [_bed()], "scandi")
        assert inst.strength is None
