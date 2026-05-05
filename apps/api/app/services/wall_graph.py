"""
Wall Graph — топологический граф стен.

Узлы графа: пересечения, T-стыки, углы, концы стен.
Рёбра: сегменты стен между узлами.

Это критически важная структура: без неё нельзя ни найти комнаты
(они = циклы в графе), ни найти проёмы (они = разрывы в рёбрах).

Алгоритм:
1. Snap: близкие концы стен сливаются в один узел.
2. Intersect: где две стены пересекаются — добавляем узел.
3. Split: стены разбиваются на сегменты по узлам.
4. Outer cycle: самый длинный простой цикл = внешняя граница.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Iterable

from app.schemas.geometry import Point, Wall, WallType

logger = logging.getLogger(__name__)

SNAP_DISTANCE_PX = 10           # концы стен в пределах этого расстояния — один узел
INTERSECT_TOLERANCE_PX = 4      # допуск для пересечений


# ─── Структуры ───────────────────────────────────────────────────────────────


@dataclass
class GraphNode:
    id: str
    x: float
    y: float
    wall_ids: set[str] = field(default_factory=set)  # стены, инцидентные узлу

    def distance_to(self, other: "GraphNode") -> float:
        return math.hypot(self.x - other.x, self.y - other.y)


@dataclass
class GraphEdge:
    """Стена-как-ребро между двумя узлами графа."""
    id: str
    node_a: str
    node_b: str
    wall: Wall


@dataclass
class WallGraph:
    nodes: dict[str, GraphNode] = field(default_factory=dict)
    edges: dict[str, GraphEdge] = field(default_factory=dict)
    outer_boundary_edge_ids: set[str] = field(default_factory=set)

    def add_node(self, x: float, y: float) -> GraphNode:
        nid = f"n{len(self.nodes):04d}"
        node = GraphNode(id=nid, x=x, y=y)
        self.nodes[nid] = node
        return node

    def find_or_create_node(self, x: float, y: float, snap: float = SNAP_DISTANCE_PX) -> GraphNode:
        """Найти ближайший узел в пределах snap, иначе создать."""
        best_node, best_dist = None, snap + 1
        for node in self.nodes.values():
            d = math.hypot(node.x - x, node.y - y)
            if d < best_dist:
                best_dist = d
                best_node = node
        if best_node is not None and best_dist <= snap:
            return best_node
        return self.add_node(x, y)

    def add_edge(self, wall: Wall, node_a: GraphNode, node_b: GraphNode) -> GraphEdge:
        edge = GraphEdge(id=wall.id, node_a=node_a.id, node_b=node_b.id, wall=wall)
        self.edges[wall.id] = edge
        node_a.wall_ids.add(wall.id)
        node_b.wall_ids.add(wall.id)
        return edge

    def neighbors(self, node_id: str) -> set[str]:
        node = self.nodes.get(node_id)
        if not node:
            return set()
        result = set()
        for eid in node.wall_ids:
            edge = self.edges.get(eid)
            if not edge:
                continue
            other = edge.node_b if edge.node_a == node_id else edge.node_a
            result.add(other)
        return result


# ─── Построение ──────────────────────────────────────────────────────────────


def _segments_intersect(
    a1: tuple[float, float], a2: tuple[float, float],
    b1: tuple[float, float], b2: tuple[float, float],
) -> tuple[float, float] | None:
    """Пересечение двух отрезков. Возвращает точку или None."""
    x1, y1 = a1
    x2, y2 = a2
    x3, y3 = b1
    x4, y4 = b2

    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-9:
        return None  # параллельны

    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / denom

    eps = 0.001
    if -eps <= t <= 1 + eps and -eps <= u <= 1 + eps:
        ix = x1 + t * (x2 - x1)
        iy = y1 + t * (y2 - y1)
        return (ix, iy)
    return None


def build_wall_graph(walls: list[Wall], img_w: int, img_h: int) -> WallGraph:
    """
    Построить граф из списка стен.

    Сначала разбиваем стены по пересечениям, потом snap-им концы.
    """
    if not walls:
        return WallGraph()

    # ── 1. Найти все пересечения — разбить стены на сегменты ─────────────
    split_walls: list[Wall] = []

    for i, wall in enumerate(walls):
        a1 = (wall.start.x, wall.start.y)
        a2 = (wall.end.x, wall.end.y)

        # Точки разбиения (включая концы)
        split_points = [a1, a2]

        for j, other in enumerate(walls):
            if i == j:
                continue
            b1 = (other.start.x, other.start.y)
            b2 = (other.end.x, other.end.y)
            ip = _segments_intersect(a1, a2, b1, b2)
            if ip is None:
                continue
            # Не считаем общие концы за внутренние пересечения
            for ep in [a1, a2]:
                if math.hypot(ip[0] - ep[0], ip[1] - ep[1]) < INTERSECT_TOLERANCE_PX:
                    break
            else:
                split_points.append(ip)

        # Сортируем точки вдоль стены и создаём сегменты
        # Проецируем на направление стены
        dx = a2[0] - a1[0]
        dy = a2[1] - a1[1]
        length = math.hypot(dx, dy)
        if length == 0:
            continue
        ux, uy = dx / length, dy / length

        def project(pt):
            return (pt[0] - a1[0]) * ux + (pt[1] - a1[1]) * uy

        split_points.sort(key=project)
        # Дедуп близких
        clean = [split_points[0]]
        for p in split_points[1:]:
            if math.hypot(p[0] - clean[-1][0], p[1] - clean[-1][1]) > 2:
                clean.append(p)

        for k in range(len(clean) - 1):
            sub = Wall(
                id=f"{wall.id}__{k}",
                type=wall.type,
                start=Point(x=clean[k][0], y=clean[k][1]),
                end=Point(x=clean[k + 1][0], y=clean[k + 1][1]),
                thickness_px=wall.thickness_px,
                locked=True,
                confidence=wall.confidence,
            )
            split_walls.append(sub)

    # ── 2. Построить граф со snap-узлов ──────────────────────────────────
    graph = WallGraph()
    for wall in split_walls:
        node_a = graph.find_or_create_node(wall.start.x, wall.start.y)
        node_b = graph.find_or_create_node(wall.end.x, wall.end.y)
        if node_a.id == node_b.id:
            continue  # вырожденная стена
        # Обновляем стену с новыми snap-координатами
        wall.start = Point(x=node_a.x, y=node_a.y)
        wall.end = Point(x=node_b.x, y=node_b.y)
        graph.add_edge(wall, node_a, node_b)

    # ── 3. Outer boundary через bounding box всех стен ────────────────────
    # Старая эвристика по % изображения не работала из-за белых полей плана.
    # Новая: находим bbox всех stенных узлов, и считаем стену внешней если
    # её концы ОБА попадают в margin от bbox-стен (не изображения).
    if graph.nodes:
        all_xs = [n.x for n in graph.nodes.values()]
        all_ys = [n.y for n in graph.nodes.values()]
        bbox_x0, bbox_x1 = min(all_xs), max(all_xs)
        bbox_y0, bbox_y1 = min(all_ys), max(all_ys)
        bbox_w = bbox_x1 - bbox_x0
        bbox_h = bbox_y1 - bbox_y0
        margin = max(bbox_w, bbox_h) * 0.06   # 6% от меньшей стороны bbox

        for edge in graph.edges.values():
            node_a = graph.nodes[edge.node_a]
            node_b = graph.nodes[edge.node_b]

            def is_on_bbox_edge(node):
                return (
                    node.x - bbox_x0 <= margin or
                    bbox_x1 - node.x <= margin or
                    node.y - bbox_y0 <= margin or
                    bbox_y1 - node.y <= margin
                )

            if is_on_bbox_edge(node_a) and is_on_bbox_edge(node_b):
                graph.outer_boundary_edge_ids.add(edge.id)
                edge.wall.type = WallType.outer

    logger.info(
        f"Wall graph: {len(graph.nodes)} nodes, {len(graph.edges)} edges, "
        f"{len(graph.outer_boundary_edge_ids)} outer"
    )

    return graph
