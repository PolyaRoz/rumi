"""
Тесты opening_detector — главный модуль для решения проблемы "64 двери".

Проверки:
1. Стена без разрывов → нет проёмов
2. Стена с одним gap'ом → один candidate
3. Дуга вне стены НЕ создаёт проём
4. Многократные мелкие разрывы → отфильтрованы по min_width
5. Огромный разрыв → отфильтрован по max_width
"""

import numpy as np
import cv2
import pytest

from app.schemas.geometry import Point, Wall, WallType
from app.services.opening_detector import find_openings


def _make_mask(shape=(200, 400), walls_to_draw=None):
    """Создать пустую маску, нарисовать на ней стены."""
    mask = np.zeros(shape, dtype=np.uint8)
    if walls_to_draw is None:
        return mask
    for (x1, y1, x2, y2) in walls_to_draw:
        cv2.line(mask, (x1, y1), (x2, y2), 255, 4)
    return mask


def _make_wall(wall_id: str, x1, y1, x2, y2, wtype=WallType.inner) -> Wall:
    return Wall(
        id=wall_id, type=wtype,
        start=Point(x=float(x1), y=float(y1)),
        end=Point(x=float(x2), y=float(y2)),
        thickness_px=4.0, locked=True, confidence=1.0,
    )


class TestOpeningDetector:

    def test_continuous_wall_no_openings(self):
        """Сплошная стена без разрывов → 0 проёмов."""
        mask = _make_mask((200, 400), [(50, 100, 350, 100)])
        wall = _make_wall("w0", 50, 100, 350, 100)
        openings = find_openings(mask, [wall], px_per_meter=50.0)
        assert len(openings) == 0

    def test_wall_with_one_gap_returns_one_opening(self):
        """Стена с одним разрывом 30px → один проём."""
        # Рисуем две части стены, оставляя разрыв в середине
        mask = _make_mask((200, 400), [
            (50, 100, 180, 100),
            (220, 100, 350, 100),  # gap в [180, 220] = 40px
        ])
        wall = _make_wall("w0", 50, 100, 350, 100)
        openings = find_openings(mask, [wall], px_per_meter=50.0)
        assert len(openings) == 1
        assert openings[0].wall_id == "w0"
        assert 30 <= openings[0].width_px <= 50

    def test_arc_outside_wall_creates_no_opening(self):
        """Дуга на пустом месте (без стены под ней) → нет проёма."""
        mask = np.zeros((200, 400), dtype=np.uint8)
        # Рисуем дугу (как от двери унитаза) но БЕЗ стены вокруг
        cv2.ellipse(mask, (100, 100), (15, 15), 0, 0, 90, 255, 2)
        wall = _make_wall("w0", 50, 100, 350, 100)
        openings = find_openings(mask, [wall], px_per_meter=50.0)
        # Без структурной стены вдоль линии — нет gap-кандидатов
        assert len(openings) == 0

    def test_too_small_gap_filtered(self):
        """Очень маленький разрыв (5px) → отфильтрован."""
        mask = _make_mask((200, 400), [
            (50, 100, 197, 100),
            (203, 100, 350, 100),  # gap всего 6px
        ])
        wall = _make_wall("w0", 50, 100, 350, 100)
        openings = find_openings(mask, [wall], px_per_meter=50.0)
        # 6px < 0.4m * 50 = 20px → отфильтрован
        assert len(openings) == 0

    def test_too_big_gap_filtered(self):
        """Огромный разрыв (200px) → отфильтрован."""
        mask = _make_mask((200, 400), [
            (50, 100, 80, 100),
            (320, 100, 350, 100),  # gap 240px
        ])
        wall = _make_wall("w0", 50, 100, 350, 100)
        openings = find_openings(mask, [wall], px_per_meter=50.0)
        # 240px > 1.8m * 50 = 90px → отфильтрован
        assert len(openings) == 0

    def test_multiple_walls_independent(self):
        """Несколько стен — каждая обрабатывается независимо."""
        mask = _make_mask((300, 400), [
            (50, 50, 350, 50),       # верхняя стена сплошная
            (50, 200, 180, 200),
            (220, 200, 350, 200),    # нижняя — с разрывом
        ])
        walls = [
            _make_wall("top", 50, 50, 350, 50),
            _make_wall("bottom", 50, 200, 350, 200),
        ]
        openings = find_openings(mask, walls, px_per_meter=50.0)
        assert len(openings) == 1
        assert openings[0].wall_id == "bottom"

    def test_opening_not_at_wall_endpoint(self):
        """Разрыв должен иметь 'хвосты' стены с обеих сторон."""
        # Если стена кончается, не считаем это разрывом
        mask = _make_mask((200, 400), [
            (50, 100, 200, 100),  # стена кончается в 200
        ])
        wall = _make_wall("w0", 50, 100, 350, 100)  # но мы её ожидаем до 350
        openings = find_openings(mask, [wall], px_per_meter=50.0)
        # Разрыв в конце не должен считаться (нет хвоста с правой стороны)
        assert len(openings) == 0
