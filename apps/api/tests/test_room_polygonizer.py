"""
Тесты room_polygonizer — главный модуль для решения "rooms = 0".

Проверки:
1. Замкнутый прямоугольник стен → 1 комната
2. Прямоугольник с дверным проёмом → ВСЁ ЕЩЁ 1 комната (gap closing)
3. Две комнаты, разделённые внутренней стеной с проёмом → 2 комнаты
4. Слишком маленькие "комнаты" → отфильтрованы
"""

import numpy as np
import cv2
import pytest

from app.schemas.geometry import Point, Wall, WallType
from app.services.room_polygonizer import polygonize_rooms


def _draw_walls(shape=(400, 500), wall_lines=None, thickness=5):
    mask = np.zeros(shape, dtype=np.uint8)
    if wall_lines:
        for (x1, y1, x2, y2) in wall_lines:
            cv2.line(mask, (x1, y1), (x2, y2), 255, thickness)
    return mask


def _wall(wid, x1, y1, x2, y2, wtype=WallType.outer):
    return Wall(
        id=wid, type=wtype,
        start=Point(x=float(x1), y=float(y1)),
        end=Point(x=float(x2), y=float(y2)),
        thickness_px=5.0, locked=True, confidence=1.0,
    )


class TestRoomPolygonizer:

    def test_closed_rectangle_one_room(self):
        """Замкнутый прямоугольник 400×300 → 1 комната."""
        mask = _draw_walls((400, 500), [
            (50, 50, 450, 50),     # top
            (450, 50, 450, 350),   # right
            (50, 350, 450, 350),   # bottom
            (50, 50, 50, 350),     # left
        ])
        walls = [
            _wall("w0", 50, 50, 450, 50),
            _wall("w1", 450, 50, 450, 350),
            _wall("w2", 50, 350, 450, 350),
            _wall("w3", 50, 50, 50, 350),
        ]
        rooms, _ = polygonize_rooms(mask, walls, px_per_meter=50.0)
        assert len(rooms) == 1
        assert rooms[0].polygon
        assert rooms[0].area_px2 > 50000

    def test_rectangle_with_door_gap_still_one_room(self):
        """Прямоугольник с разрывом 30px (дверь) — gap closing должен закрыть."""
        # Низ с разрывом в середине
        mask = _draw_walls((400, 500), [
            (50, 50, 450, 50),
            (450, 50, 450, 350),
            (50, 350, 230, 350),     # нижняя — левая часть
            (270, 350, 450, 350),    # нижняя — правая часть (gap 40px)
            (50, 50, 50, 350),
        ])
        walls = [
            _wall("w0", 50, 50, 450, 50),
            _wall("w1", 450, 50, 450, 350),
            _wall("w2", 50, 350, 230, 350),
            _wall("w3", 270, 350, 450, 350),
            _wall("w4", 50, 50, 50, 350),
        ]
        rooms, closed_mask = polygonize_rooms(mask, walls, px_per_meter=50.0)
        assert len(rooms) == 1, f"Ожидалась 1 комната, получено {len(rooms)}"

    def test_two_rooms_with_inner_wall(self):
        """Две комнаты, разделённые внутренней стеной с проёмом → 2 комнаты."""
        mask = _draw_walls((400, 600), [
            # Внешний прямоугольник
            (50, 50, 550, 50),
            (550, 50, 550, 350),
            (50, 350, 550, 350),
            (50, 50, 50, 350),
            # Внутренняя стена с разрывом
            (300, 50, 300, 180),
            (300, 220, 300, 350),
        ])
        walls = [
            _wall("w0", 50, 50, 550, 50),
            _wall("w1", 550, 50, 550, 350),
            _wall("w2", 50, 350, 550, 350),
            _wall("w3", 50, 50, 50, 350),
            _wall("w4", 300, 50, 300, 180, WallType.inner),
            _wall("w5", 300, 220, 300, 350, WallType.inner),
        ]
        rooms, _ = polygonize_rooms(mask, walls, px_per_meter=50.0)
        # Door gap 40px должен закрыться, но внутренняя стена остаётся
        # → 2 комнаты по обе стороны от внутренней стены
        assert len(rooms) == 2, f"Ожидалось 2 комнаты, получено {len(rooms)}"

    def test_too_small_blob_filtered(self):
        """Маленький замкнутый прямоугольник (типа санузла-иконки) → отфильтрован."""
        mask = _draw_walls((400, 500), [
            # Большая комната
            (50, 50, 450, 50),
            (450, 50, 450, 350),
            (50, 350, 450, 350),
            (50, 50, 50, 350),
            # Маленький "квадрат" внутри (как иконка)
            (100, 100, 130, 100),
            (130, 100, 130, 130),
            (130, 130, 100, 130),
            (100, 100, 100, 130),
        ])
        walls = [
            _wall(f"w{i}", *line) for i, line in enumerate([
                (50, 50, 450, 50), (450, 50, 450, 350),
                (50, 350, 450, 350), (50, 50, 50, 350),
            ])
        ]
        rooms, _ = polygonize_rooms(mask, walls, px_per_meter=50.0)
        # Должна быть только большая комната (маленький < MIN_ROOM_AREA_PX)
        assert len(rooms) == 1

    def test_no_walls_no_rooms(self):
        """Пустая маска → 0 комнат."""
        mask = np.zeros((300, 400), dtype=np.uint8)
        rooms, _ = polygonize_rooms(mask, [], px_per_meter=None)
        assert len(rooms) == 0

    def test_rooms_have_unique_ids(self):
        """Все комнаты имеют уникальные ID."""
        mask = _draw_walls((400, 600), [
            (50, 50, 550, 50), (550, 50, 550, 350),
            (50, 350, 550, 350), (50, 50, 50, 350),
            (300, 50, 300, 180), (300, 220, 300, 350),
        ])
        walls = [
            _wall(f"w{i}", *line) for i, line in enumerate([
                (50, 50, 550, 50), (550, 50, 550, 350),
                (50, 350, 550, 350), (50, 50, 50, 350),
                (300, 50, 300, 180), (300, 220, 300, 350),
            ])
        ]
        rooms, _ = polygonize_rooms(mask, walls, px_per_meter=50.0)
        ids = [r.id for r in rooms]
        assert len(ids) == len(set(ids))
