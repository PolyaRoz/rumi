"""
Тесты false_positive_filter — sanity rules.

Проверки:
1. Слишком много дверей для маленькой квартиры → топ N по confidence
2. Дубликаты на одной стене близко → удалены
3. Окна на ВНУТРЕННИХ стенах с низким conf → отброшены
4. Confidence gating: rooms=0 → room_conf=0
5. is_geometry_lockable: блокирует размещение мебели при невалидной геометрии
"""

import pytest

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
    SwingDirection,
    Wall,
    WallType,
)
from app.services.false_positive_filter import (
    compute_gated_confidence,
    filter_openings,
    is_geometry_lockable,
    max_doors_for_rooms,
)


def _wall(wid, wtype=WallType.inner) -> Wall:
    return Wall(
        id=wid, type=wtype,
        start=Point(x=0, y=0), end=Point(x=100, y=0),
        thickness_px=4.0, locked=True, confidence=1.0,
    )


def _door(did, wall_id, x, y, conf=0.7) -> Opening:
    return Opening(
        id=did, type=OpeningType.door,
        wall_id=wall_id,
        position=Point(x=float(x), y=float(y)),
        width_px=30.0, width_m=0.6,
        swing_direction=SwingDirection.unknown,
        clearance_m=0.8, locked=True,
        confidence=conf,
    )


def _window(wid, wall_id, x, y, conf=0.6) -> Opening:
    return Opening(
        id=wid, type=OpeningType.window,
        wall_id=wall_id,
        position=Point(x=float(x), y=float(y)),
        width_px=40.0, width_m=0.8,
        swing_direction=SwingDirection.unknown,
        clearance_m=0.5, locked=True,
        confidence=conf,
    )


def _room(rid="r0", area=10000) -> Room:
    return Room(
        id=rid, label=RoomLabel.bedroom,
        area_m2=14.0, area_px2=area,
        polygon=[Point(x=0, y=0), Point(x=100, y=0),
                 Point(x=100, y=100), Point(x=0, y=100)],
        centroid=Point(x=50, y=50),
        wall_ids=["wall_001"],
    )


# ─── max_doors_for_rooms ──────────────────────────────────────────────────────

def test_max_doors_formula():
    assert max_doors_for_rooms(0) == 5
    assert max_doors_for_rooms(2) == 11
    assert max_doors_for_rooms(5) == 20


# ─── filter_openings ─────────────────────────────────────────────────────────

class TestFilterOpenings:

    def test_too_many_doors_keeps_top_n(self):
        """Из 64 дверей при 2 комнатах оставляем max 11."""
        walls = [_wall("wall_001"), _wall("wall_002")]
        rooms = [_room("r0"), _room("r1")]
        # 64 двери с разной confidence
        doors = [
            _door(f"d{i}", "wall_001", x=i*5, y=0, conf=0.9 - i*0.01)
            for i in range(64)
        ]
        filtered, report = filter_openings(doors, walls, rooms)
        assert len(filtered) <= 11, f"Прошло {len(filtered)}, ожидалось ≤11"
        assert any("too_many_doors" in reason for _, reason in report.rejected_doors)

    def test_duplicate_doors_deduplicated(self):
        """Двери на одной стене в близких точках → один остаётся."""
        walls = [_wall("wall_001")]
        rooms = [_room()]
        doors = [
            _door("d0", "wall_001", 100, 0, conf=0.9),
            _door("d1", "wall_001", 105, 0, conf=0.6),  # дубликат
            _door("d2", "wall_001", 200, 0, conf=0.7),  # отдельная
        ]
        filtered, report = filter_openings(doors, walls, rooms)
        assert len(filtered) == 2
        # d1 должна быть отброшена как дубликат
        ids_kept = [o.id for o in filtered]
        # ID после фильтра переиндексируются — проверяем по count
        rejected_ids = [r[0] for r in report.rejected_doors]
        assert "d1" in rejected_ids

    def test_window_on_inner_wall_low_conf_rejected(self):
        """Окно на ВНУТРЕННЕЙ стене с низкой conf → отброшено."""
        walls = [_wall("wall_001", WallType.inner)]  # внутренняя!
        rooms = [_room()]
        windows = [_window("w0", "wall_001", 50, 0, conf=0.20)]
        filtered, report = filter_openings(windows, walls, rooms)
        # Должно быть отброшено
        assert len([o for o in filtered if o.type == OpeningType.window]) == 0
        assert any("not_on_outer_wall" in reason for _, reason in report.rejected_windows)

    def test_window_on_outer_wall_kept(self):
        """Окно на ВНЕШНЕЙ стене сохраняется."""
        walls = [_wall("wall_001", WallType.outer)]
        rooms = [_room()]
        windows = [_window("w0", "wall_001", 50, 0, conf=0.6)]
        filtered, _ = filter_openings(windows, walls, rooms)
        assert len([o for o in filtered if o.type == OpeningType.window]) == 1


# ─── compute_gated_confidence ─────────────────────────────────────────────────

class TestConfidenceGating:

    def test_zero_rooms_zeroes_room_conf(self):
        """Нет комнат → room_conf обнуляется."""
        raw = ConfidenceScores(
            wall_confidence=0.8, room_confidence=0.5,
            door_confidence=0.5, window_confidence=0.5, scale_confidence=0.5,
        )
        gated, warnings = compute_gated_confidence(
            walls=[_wall("w1")], rooms=[],  # нет комнат
            doors=[], windows=[],
            raw_scores=raw, has_outer_wall=True,
        )
        assert gated.room_confidence == 0.0
        assert any("Комнаты не найдены" in w for w in warnings)

    def test_excessive_doors_lowers_door_conf(self):
        """Дверей значительно больше комнат → door_conf снижен."""
        raw = ConfidenceScores(
            wall_confidence=0.8, room_confidence=0.7,
            door_confidence=0.8, window_confidence=0.5, scale_confidence=0.5,
        )
        many_doors = [_door(f"d{i}", "w1", i*10, 0) for i in range(50)]
        gated, warnings = compute_gated_confidence(
            walls=[_wall("w1")], rooms=[_room("r0"), _room("r1")],  # 2 комнаты
            doors=many_doors, windows=[],
            raw_scores=raw, has_outer_wall=True,
        )
        assert gated.door_confidence < 0.4
        assert any("Слишком много дверей" in w for w in warnings)


# ─── is_geometry_lockable ─────────────────────────────────────────────────────

class TestIsLockable:

    def test_no_rooms_not_lockable(self):
        geo = ApartmentGeometry(
            source_image_width_px=400, source_image_height_px=300,
            scale=Scale(px_per_meter=50.0, source="user_input", confidence=1.0),
            walls=[_wall("w1"), _wall("w2"), _wall("w3"), _wall("w4")],
            openings=[], rooms=[],  # нет комнат
            constraints=Constraints(),
            confidence=ConfidenceScores(),
        )
        ok, reasons = is_geometry_lockable(geo)
        assert not ok
        assert any("Нет комнат" in r for r in reasons)

    def test_no_scale_not_lockable(self):
        geo = ApartmentGeometry(
            source_image_width_px=400, source_image_height_px=300,
            scale=Scale(px_per_meter=None, source="unknown"),
            walls=[_wall("w1"), _wall("w2"), _wall("w3"), _wall("w4")],
            openings=[], rooms=[_room("r0")],
            constraints=Constraints(),
            confidence=ConfidenceScores(),
        )
        ok, reasons = is_geometry_lockable(geo)
        assert not ok
        assert any("масштаб" in r.lower() for r in reasons)

    def test_complete_geometry_lockable(self):
        geo = ApartmentGeometry(
            source_image_width_px=400, source_image_height_px=300,
            scale=Scale(px_per_meter=50.0, source="user_input", confidence=1.0),
            walls=[_wall("w1"), _wall("w2"), _wall("w3"), _wall("w4")],
            openings=[],
            rooms=[_room("r0")],
            constraints=Constraints(),
            confidence=ConfidenceScores(),
        )
        # Одиночная комната не требует дверей между комнатами
        ok, reasons = is_geometry_lockable(geo)
        assert ok, f"Expected lockable, got reasons: {reasons}"
