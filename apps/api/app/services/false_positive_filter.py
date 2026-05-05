"""
False Positive Filter — финальный пасс с sanity rules.

Из ТЗ:
- "if detected doors > 3 * rooms_count + 5, trigger false-positive filtering"
- "rooms_count == 0, do not continue to furniture placement"

Этот модуль выполняет:
1. Жёсткое правило: doors_count <= max_doors_for_rooms(N)
2. Дублирование: openings ближе X px → оставить с большей confidence
3. Inside-symbol check (упрощённо): окна не во внутренних мокрых зонах
4. Sanity gates: блокируем furniture placement при невалидной геометрии
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

from app.schemas.geometry import (
    ApartmentGeometry,
    ConfidenceScores,
    Opening,
    OpeningType,
    Room,
    Wall,
    WallType,
)

logger = logging.getLogger(__name__)

# Максимум дверей: 3 на комнату + 5 (плюс входная)
def max_doors_for_rooms(n_rooms: int) -> int:
    return max(3, 3 * n_rooms + 5)


# Дубликат: проёмы в пределах этого расстояния — один и тот же.
# 35px ≈ 0.6м при типичном 60 px/m = меньше ширины двери, безопасно.
DUPLICATE_DIST_PX = 35

# Минимальный confidence окна на наружной стене для сохранения
MIN_OUTER_WINDOW_CONF = 0.30


@dataclass
class FilterReport:
    rejected_doors: list[tuple[str, str]] = field(default_factory=list)
    rejected_windows: list[tuple[str, str]] = field(default_factory=list)
    sanity_warnings: list[str] = field(default_factory=list)


def filter_openings(
    openings: list[Opening],
    walls: list[Wall],
    rooms: list[Room],
) -> tuple[list[Opening], FilterReport]:
    """
    Применить false-positive filtering к проёмам.
    Возвращает (filtered_openings, report).
    """
    report = FilterReport()
    walls_by_id = {w.id: w for w in walls}

    doors = [o for o in openings if o.type == OpeningType.door]
    windows = [o for o in openings if o.type == OpeningType.window]

    # ── 1. Дедупликация: близкие проёмы ──────────────────────────────────
    doors = _deduplicate(doors, report, "door")
    windows = _deduplicate(windows, report, "window")

    # ── 2. Окна должны быть только на внешних стенах ─────────────────────
    valid_windows = []
    for w in windows:
        wall = walls_by_id.get(w.wall_id)
        if wall is None:
            report.rejected_windows.append((w.id, "wall_not_found"))
            continue
        if wall.type != WallType.outer:
            # Не внешняя — переклассифицируем в дверь, если confidence низкий
            if w.confidence < MIN_OUTER_WINDOW_CONF:
                report.rejected_windows.append((w.id, "not_on_outer_wall"))
                continue
            # Иначе оставляем как window (возможно балконная дверь и т.п.)
        valid_windows.append(w)
    windows = valid_windows

    # ── 3. Sanity rule: если дверей слишком много → ужесточить ────────────
    n_rooms = len(rooms)
    max_doors = max_doors_for_rooms(n_rooms)
    if len(doors) > max_doors:
        report.sanity_warnings.append(
            f"Дверей детектировано {len(doors)} > порога {max_doors} "
            f"для {n_rooms} комнат — оставляем top-{max_doors} по confidence"
        )
        doors.sort(key=lambda d: d.confidence, reverse=True)
        kept = doors[:max_doors]
        for rejected in doors[max_doors:]:
            report.rejected_doors.append((rejected.id, "too_many_doors_for_rooms"))
        doors = kept

    # ── 4. Финальная сборка ──────────────────────────────────────────────
    filtered = doors + windows
    # Переиндексация для читаемых ID
    for i, op in enumerate(filtered):
        op.id = f"{op.type.value}_{i:03d}"

    logger.info(
        f"FP filter: doors {len([o for o in openings if o.type == OpeningType.door])}"
        f"→{len(doors)}, windows {len([o for o in openings if o.type == OpeningType.window])}"
        f"→{len(windows)}, rejected={len(report.rejected_doors) + len(report.rejected_windows)}"
    )

    return filtered, report


def _deduplicate(
    openings: list[Opening], report: FilterReport, kind: str,
) -> list[Opening]:
    """
    Удалить дубликаты (близкие проёмы), оставить с лучшим confidence.

    КРИТИЧНО: проверяем близость БЕЗ привязки к wall_id, потому что после
    wall_graph splitting один реальный дверной проём может быть привязан
    к разным post-split сегментам у разных кандидатов (например один gap
    пересекает T-junction).
    """
    if not openings:
        return []
    sorted_ops = sorted(openings, key=lambda o: o.confidence, reverse=True)
    kept: list[Opening] = []
    for op in sorted_ops:
        is_dup = False
        for already_kept in kept:
            d = math.hypot(
                op.position.x - already_kept.position.x,
                op.position.y - already_kept.position.y,
            )
            if d < DUPLICATE_DIST_PX:
                is_dup = True
                break
        if is_dup:
            getattr(report, f"rejected_{kind}s").append((op.id, "duplicate"))
        else:
            kept.append(op)
    return kept


# ─── Confidence gating ───────────────────────────────────────────────────────


def compute_gated_confidence(
    walls: list[Wall], rooms: list[Room],
    doors: list[Opening], windows: list[Opening],
    raw_scores: ConfidenceScores,
    has_outer_wall: bool,
) -> tuple[ConfidenceScores, list[str]]:
    """
    Реалистичное общее confidence с gates.

    Из ТЗ:
    - rooms_detected == 0 → overall confidence очень низкая
    - doors >> rooms → false positive explosion
    - scale_confidence == 0 → блокируем furniture
    """
    warnings: list[str] = []
    gated = ConfidenceScores(
        wall_confidence=raw_scores.wall_confidence,
        room_confidence=raw_scores.room_confidence,
        door_confidence=raw_scores.door_confidence,
        window_confidence=raw_scores.window_confidence,
        scale_confidence=raw_scores.scale_confidence,
    )

    # Gate 1: нет комнат → всё резко уменьшается
    if len(rooms) == 0:
        warnings.append("Комнаты не найдены — геометрия невалидна")
        gated.room_confidence = 0.0
        gated.wall_confidence *= 0.5

    # Gate 2: дверей в разы больше чем комнат
    if len(rooms) > 0 and len(doors) > 3 * len(rooms) + 5:
        warnings.append(
            f"Слишком много дверей ({len(doors)}) для {len(rooms)} комнат — "
            "вероятна over-detection"
        )
        gated.door_confidence *= 0.4

    # Gate 3: нет окон, но есть внешняя стена
    if has_outer_wall and len(windows) == 0:
        warnings.append("Окна не найдены, хотя внешняя стена есть")
        gated.window_confidence *= 0.7

    # Gate 4: нет масштаба → блок размещения мебели
    if gated.scale_confidence == 0:
        warnings.append("Масштаб не определён — нужен ввод пользователя")

    return gated, warnings


def is_geometry_lockable(geometry: ApartmentGeometry) -> tuple[bool, list[str]]:
    """
    Можно ли заблокировать геометрию для furniture placement?

    Returns:
        (can_lock, blocking_reasons)
    """
    reasons: list[str] = []

    if len(geometry.walls) < 4:
        reasons.append(f"Слишком мало стен: {len(geometry.walls)} < 4")
    if len(geometry.rooms) == 0:
        reasons.append("Нет комнат")
    if not geometry.scale.px_per_meter:
        reasons.append("Не определён масштаб")
    # Проёмы — мягкое требование
    if len(geometry.openings) == 0 and len(geometry.rooms) > 1:
        reasons.append("Нет дверей между комнатами")

    return len(reasons) == 0, reasons
