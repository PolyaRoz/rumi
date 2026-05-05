"""
Тесты детектора стен.

Используем синтетические изображения простых планов:
- Простой прямоугольник (4 внешних стены)
- Прямоугольник с внутренней перегородкой
- Прямоугольник с разрывами (дверные проёмы)
"""

import pytest
import numpy as np
import cv2

from app.services.preprocessing import preprocess
from app.services.wall_detector import detect_walls, MIN_WALL_LENGTH_PX


def _make_simple_plan(
    width: int = 400,
    height: int = 300,
    wall_thickness: int = 8,
    inner_wall: bool = False,
    door_gap: bool = False,
) -> np.ndarray:
    """
    Создать синтетическое изображение плана:
    - Белый фон
    - Чёрный прямоугольник (внешние стены)
    - Опционально: внутренняя перегородка
    - Опционально: разрыв в стене (дверь)
    """
    img = np.ones((height, width, 3), dtype=np.uint8) * 255

    # Внешние стены
    margin = 50
    cv2.rectangle(img,
                  (margin, margin),
                  (width - margin, height - margin),
                  (0, 0, 0), wall_thickness)

    if inner_wall:
        # Вертикальная перегородка посередине
        mid_x = width // 2
        cv2.line(img,
                 (mid_x, margin),
                 (mid_x, height - margin),
                 (0, 0, 0), wall_thickness // 2)

    if door_gap:
        # Разрыв в нижней стене (дверной проём)
        gap_start = width // 2 - 25
        gap_end = width // 2 + 25
        cv2.line(img,
                 (gap_start, height - margin - wall_thickness // 2),
                 (gap_end, height - margin - wall_thickness // 2),
                 (255, 255, 255), wall_thickness + 2)

    return img


class TestWallDetector:

    def test_simple_rectangle_detects_walls(self):
        """Простой прямоугольник должен дать хотя бы 4 стены."""
        img = _make_simple_plan()
        plan = preprocess(img)
        walls, confidence = detect_walls(plan)

        assert len(walls) >= 4, f"Ожидалось >= 4 стен, получено {len(walls)}"
        assert confidence > 0.3, f"Слишком низкий confidence: {confidence}"

    def test_walls_have_valid_ids(self):
        """Все стены должны иметь уникальные ID."""
        img = _make_simple_plan()
        plan = preprocess(img)
        walls, _ = detect_walls(plan)

        ids = [w.id for w in walls]
        assert len(ids) == len(set(ids)), "Дублирующиеся ID стен"

    def test_walls_are_locked(self):
        """Все стены должны быть locked по умолчанию."""
        img = _make_simple_plan()
        plan = preprocess(img)
        walls, _ = detect_walls(plan)

        for wall in walls:
            assert wall.locked is True, f"Стена {wall.id} не locked"

    def test_wall_length_above_minimum(self):
        """Все стены должны быть длиннее минимума."""
        img = _make_simple_plan()
        plan = preprocess(img)
        walls, _ = detect_walls(plan)

        for wall in walls:
            length = wall.length_px
            assert length >= MIN_WALL_LENGTH_PX, (
                f"Стена {wall.id} слишком короткая: {length:.1f} < {MIN_WALL_LENGTH_PX}"
            )

    @pytest.mark.xfail(reason="V2: разделение outer/inner теперь в wall_graph, не в wall_detector")
    def test_inner_wall_detected(self):
        """С внутренней перегородкой количество стен должно быть больше."""
        img_no_inner = _make_simple_plan(inner_wall=False)
        img_with_inner = _make_simple_plan(inner_wall=True)

        plan_no = preprocess(img_no_inner)
        plan_yes = preprocess(img_with_inner)

        walls_no, _ = detect_walls(plan_no)
        walls_yes, _ = detect_walls(plan_yes)

        assert len(walls_yes) > len(walls_no), (
            f"С перегородкой стен должно быть больше: {len(walls_yes)} vs {len(walls_no)}"
        )

    def test_wall_confidence_range(self):
        """Confidence должен быть в [0, 1]."""
        img = _make_simple_plan()
        plan = preprocess(img)
        walls, overall_conf = detect_walls(plan)

        for wall in walls:
            assert 0.0 <= wall.confidence <= 1.0, (
                f"Confidence вне диапазона: {wall.confidence}"
            )
        assert 0.0 <= overall_conf <= 1.0

    @pytest.mark.xfail(reason="V2: outer-классификация теперь в wall_graph.build_wall_graph()")
    def test_outer_walls_classified(self):
        """Внешние стены простого прямоугольника должны классифицироваться как 'outer'."""
        img = _make_simple_plan(width=400, height=300)
        plan = preprocess(img)
        walls, _ = detect_walls(plan)

        outer_walls = [w for w in walls if w.type.value == "outer"]
        assert len(outer_walls) >= 2, (
            f"Ожидалось >= 2 внешних стен, получено {len(outer_walls)}"
        )

    def test_empty_image_returns_no_walls(self):
        """Пустое белое изображение = нет стен."""
        img = np.ones((200, 200, 3), dtype=np.uint8) * 255
        plan = preprocess(img)
        walls, confidence = detect_walls(plan)

        # Допускаем небольшое количество ложных срабатываний
        assert len(walls) <= 3, f"На пустом изображении найдено {len(walls)} стен"

    def test_wall_start_end_within_image(self):
        """Координаты стен должны быть внутри изображения."""
        img = _make_simple_plan(width=400, height=300)
        plan = preprocess(img)
        walls, _ = detect_walls(plan)
        h, w = plan.walls_mask.shape

        for wall in walls:
            for pt in [wall.start, wall.end]:
                assert 0 <= pt.x <= w, f"x={pt.x} вне изображения (w={w})"
                assert 0 <= pt.y <= h, f"y={pt.y} вне изображения (h={h})"
