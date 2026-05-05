"""
Тесты room_anchoring — главный фикс "12 комнат вместо 7".

Проверки:
- Метка внутри полигона → полигон становится primary room
- Полигон без метки и маленький → отброшен как фрагмент
- Полигон без метки, но крупный → оставлен как unknown
- Несколько меток на один полигон → берётся ближайшая
- Классификация типов: 2.7→toilet, 4.0→bathroom, 10.5→kitchen, 14.4→bedroom
"""

import pytest

from app.schemas.geometry import Point, Room, RoomLabel
from app.services.room_anchoring import (
    anchor_rooms_to_labels,
    classify_room_by_area,
)
from app.services.scale_estimator import OcrArea


def _room(rid: str, x: int, y: int, w: int, h: int, area_px=None) -> Room:
    polygon = [
        Point(x=x, y=y), Point(x=x + w, y=y),
        Point(x=x + w, y=y + h), Point(x=x, y=y + h),
    ]
    return Room(
        id=rid, label=RoomLabel.unknown,
        area_m2=None,
        area_px2=area_px or (w * h),
        polygon=polygon,
        centroid=Point(x=x + w / 2, y=y + h / 2),
        confidence=0.7,
    )


# ─── Тесты anchoring ─────────────────────────────────────────────────────────


class TestAnchoring:

    def test_label_inside_polygon_anchored(self):
        """Метка внутри полигона → полигон получает label_m2."""
        rooms = [_room("r0", 0, 0, 200, 200)]
        labels = [OcrArea(value_m2=14.4, cx_px=100, cy_px=100, raw_text="14.4")]
        anchored, _unresolved, rejected = anchor_rooms_to_labels(rooms, labels, img_area_px=300*300)
        assert len(anchored) == 1
        assert anchored[0].area_m2 == 14.4
        assert anchored[0].label == RoomLabel.bedroom  # 14.4 m² → bedroom
        assert len(rejected) == 0

    def test_unlabeled_small_fragment_rejected(self):
        """Маленький фрагмент без метки → отброшен."""
        # Полигон 30x30 = 900 px² на изображении 1000x1000 (1М) → 0.09% — очень мало
        rooms = [_room("frag", 100, 100, 30, 30)]
        anchored, _unresolved, rejected = anchor_rooms_to_labels(
            rooms, [], img_area_px=1_000_000.0,
        )
        assert len(anchored) == 0
        assert len(rejected) == 1
        assert "no_area_label_and_too_small" in rejected[0][1]

    def test_unlabeled_large_polygon_kept_as_unknown(self):
        """Большой полигон без метки → unknown, не отброшен."""
        # 600x600 на изображении 1000x1000 → 36% — велик
        rooms = [_room("big", 100, 100, 600, 600)]
        anchored, _unresolved, rejected = anchor_rooms_to_labels(
            rooms, [], img_area_px=1_000_000.0,
        )
        assert len(anchored) == 1
        assert anchored[0].label == RoomLabel.unknown
        assert anchored[0].area_m2 is None

    def test_multiple_labels_same_polygon_takes_closest(self):
        """Если две метки попадают в один полигон — берём ту, чей центр ближе к центроиду."""
        rooms = [_room("r0", 0, 0, 400, 400)]
        labels = [
            OcrArea(value_m2=14.4, cx_px=50, cy_px=50, raw_text="14.4"),    # дальше от центра
            OcrArea(value_m2=16.3, cx_px=180, cy_px=180, raw_text="16.3"),  # ближе к центру 200,200
        ]
        anchored, _unresolved, _rejected = anchor_rooms_to_labels(rooms, labels, img_area_px=500*500)
        assert len(anchored) == 1
        assert anchored[0].area_m2 == 16.3

    def test_typical_apartment_filtering(self):
        """
        Симуляция реального плана: 12 raw кандидатов с 7 OCR-метками →
        должно остаться ~7 anchored + большие unlabeled.
        """
        # 7 крупных кандидатов внутри которых лежат метки
        rooms = []
        labels = []
        # Метки: 4.0, 17.2, 2.7, 14.4, 16.3, 10.5, 4.5
        positions = [
            (50, 50, 100, 100, 4.0),
            (200, 50, 300, 100, 17.2),
            (550, 50, 80, 80, 2.7),
            (50, 250, 200, 200, 14.4),
            (300, 250, 250, 200, 16.3),
            (600, 250, 150, 150, 10.5),
            (300, 500, 100, 100, 4.5),
        ]
        for i, (x, y, w, h, val) in enumerate(positions):
            rooms.append(_room(f"r{i}", x, y, w, h))
            labels.append(OcrArea(
                value_m2=val,
                cx_px=x + w / 2, cy_px=y + h / 2,
                raw_text=str(val),
            ))

        # 5 фрагментов от мебели (маленькие)
        for i in range(5):
            rooms.append(_room(f"frag_{i}", 100 + i * 30, 700, 25, 25))

        anchored, _unresolved, rejected = anchor_rooms_to_labels(
            rooms, labels, img_area_px=900 * 900,
        )
        labeled_count = sum(1 for r in anchored if r.area_m2 is not None)
        assert labeled_count == 7, f"Expected 7 labeled, got {labeled_count}"
        # Фрагменты должны быть отброшены
        assert len(rejected) >= 4


# ─── Тесты classify_room_by_area ─────────────────────────────────────────────


class TestClassifyRoomByArea:

    @pytest.mark.parametrize("area_m2,expected", [
        (2.7,  RoomLabel.toilet),
        (4.0,  RoomLabel.bathroom),
        (4.5,  RoomLabel.bathroom),  # без position-эвристики balcony — это OK для теста
        (10.5, RoomLabel.kitchen),
        (14.4, RoomLabel.bedroom),
        (16.3, RoomLabel.bedroom),
        (17.2, RoomLabel.bedroom),  # на границе → bedroom
        (22.0, RoomLabel.living_room),
    ])
    def test_classify_by_area_value(self, area_m2: float, expected: RoomLabel):
        result = classify_room_by_area(
            area_m2=area_m2, area_px2=10000,
            centroid=None, img_area_px=1_000_000,
        )
        assert result == expected, (
            f"area_m2={area_m2}: expected {expected}, got {result}"
        )
