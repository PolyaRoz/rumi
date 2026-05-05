"""
Room Anchoring — связывает OCR-метки площадей с полигонами комнат.

ПРОБЛЕМА: room_polygonizer находит много кандидатов, в т.ч. ложных:
- бокс ванны внутри ванной — отдельный полигон
- кухонный гарнитур — отдельный полигон
- внутренний коридор + основной коридор как 2 разных полигона
=> На реальном плане получается 12 "комнат" вместо 7.

РЕШЕНИЕ:
Используем OCR-распознанные числа ("4.0", "17.2", ...) как АНКЕРНЫЕ ТОЧКИ.

Алгоритм:
1. Каждой метке → найти полигон, ВНУТРИ которого она лежит. Этот полигон
   становится "primary room" с area_label_m2 = значение метки.
2. Полигоны без меток:
   - если МАЛЫЕ → отбрасываем (фрагменты от ванной/кухни/мебели)
   - если БОЛЬШИЕ → оставляем как unknown (вестибюль/балкон без подписи)
3. Финальная классификация типа комнаты по area_label_m2:
   - 1.5 ≤ x < 3.5  → toilet/wc
   - 3.5 ≤ x < 7    → bathroom (или balcony если у внешней стены)
   - 7 ≤ x < 12     → kitchen
   - 12 ≤ x < 18    → bedroom (или living_room по позиции)
   - 18 ≤ x < 30    → living_room
   - x ≥ 30         → big living/studio
   - corridor — если elongated и большой
"""

from __future__ import annotations

import logging
import math

from app.schemas.geometry import Point, Room, RoomLabel
from app.services.scale_estimator import OcrArea

logger = logging.getLogger(__name__)


# Минимальная фракция площади изображения для unlabeled полигона.
# Меньше — отбрасываем как фрагмент.
MIN_UNLABELED_FRACTION = 0.04


def _point_in_polygon(px: float, py: float, polygon: list[Point]) -> bool:
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i].x, polygon[i].y
        xj, yj = polygon[j].x, polygon[j].y
        if ((yi > py) != (yj > py)) and \
           (px < (xj - xi) * (py - yi) / (yj - yi + 1e-10) + xi):
            inside = not inside
        j = i
    return inside


def anchor_rooms_to_labels(
    candidate_rooms: list[Room],
    ocr_labels: list[OcrArea],
    img_area_px: float,
) -> tuple[list[Room], list[tuple[Room, str]]]:
    """
    Связать OCR-метки с полигонами; отфильтровать фрагменты.

    Args:
        candidate_rooms: сырые кандидаты от room_polygonizer
        ocr_labels: OCR-распознанные числовые метки площадей
        img_area_px: площадь всего изображения для нормализации

    Returns:
        (anchored_rooms, rejected_fragments)
        anchored_rooms — финальный список с area_label_m2 где есть.
        rejected_fragments — list of (room, reason) для debug.
    """
    if not candidate_rooms:
        return [], []

    # ── 1. Каждой метке ищем содержащий её полигон ──────────────────────
    # label_to_room_idx: index полигона, в который попадает метка
    label_assignments: dict[int, OcrArea] = {}  # idx → лучшая метка для этого полигона

    for label in ocr_labels:
        candidates_with_label = []
        for idx, room in enumerate(candidate_rooms):
            if not room.polygon:
                continue
            if _point_in_polygon(label.cx_px, label.cy_px, room.polygon):
                candidates_with_label.append(idx)

        if not candidates_with_label:
            # Метка не попала ни в один полигон — найти ближайший
            best_idx, best_dist = None, float("inf")
            for idx, room in enumerate(candidate_rooms):
                if room.centroid is None:
                    continue
                d = math.hypot(room.centroid.x - label.cx_px,
                               room.centroid.y - label.cy_px)
                if d < best_dist:
                    best_dist = d
                    best_idx = idx
            if best_idx is not None:
                candidates_with_label = [best_idx]

        if not candidates_with_label:
            continue

        # Если несколько полигонов содержат точку (вложенные?), берём наименьший
        # — он "ближайший" контекстно
        chosen_idx = min(
            candidates_with_label,
            key=lambda i: candidate_rooms[i].area_px2 or float("inf"),
        )

        # Резервируем за этим индексом метку. Если уже была — оставляем ту,
        # центроид которой ближе к метке.
        existing = label_assignments.get(chosen_idx)
        if existing is None:
            label_assignments[chosen_idx] = label
        else:
            room = candidate_rooms[chosen_idx]
            if room.centroid:
                d_new = math.hypot(room.centroid.x - label.cx_px,
                                   room.centroid.y - label.cy_px)
                d_old = math.hypot(room.centroid.x - existing.cx_px,
                                   room.centroid.y - existing.cy_px)
                if d_new < d_old:
                    label_assignments[chosen_idx] = label

    logger.info(
        f"Anchoring: {len(label_assignments)} полигонов привязаны к меткам, "
        f"из {len(ocr_labels)} OCR-меток и {len(candidate_rooms)} кандидатов"
    )

    # ── 2. Сборка финального списка ─────────────────────────────────────
    min_unlabeled_area = img_area_px * MIN_UNLABELED_FRACTION
    anchored: list[Room] = []
    rejected: list[tuple[Room, str]] = []

    for idx, room in enumerate(candidate_rooms):
        if idx in label_assignments:
            label = label_assignments[idx]
            room.area_m2 = label.value_m2
            # Перекласcифицируем по реальной площади
            room.label = classify_room_by_area(
                area_m2=label.value_m2,
                area_px2=room.area_px2 or 0,
                centroid=room.centroid,
                img_area_px=img_area_px,
            )
            # Bonus to confidence — у нас есть ground truth
            room.confidence = min(1.0, room.confidence + 0.25)
            anchored.append(room)
        else:
            # Без метки — фильтруем по размеру
            if (room.area_px2 or 0) >= min_unlabeled_area:
                # Большой unlabeled полигон — оставляем как unknown
                room.label = RoomLabel.unknown
                room.confidence *= 0.6
                anchored.append(room)
            else:
                rejected.append((room, "no_area_label_and_too_small"))

    # ── 3. Если меток было больше чем закреплённых полигонов ────────────
    # — это сигнал что polygonizer не нашёл некоторые комнаты.
    # Но не критично: показываем то, что нашли.
    if len(ocr_labels) > len(label_assignments):
        logger.warning(
            f"OCR labels: {len(ocr_labels)}, anchored: {len(label_assignments)}. "
            f"Возможны ненайденные полигоны — уменьшите MIN_ROOM_AREA_PX или "
            f"используйте user-correction UI."
        )

    # ── 4. Сортировка: сначала labeled, потом по убыванию площади ────────
    anchored.sort(key=lambda r: (
        0 if r.area_m2 is not None else 1,
        -(r.area_px2 or 0),
    ))
    # Переиндексация
    for i, r in enumerate(anchored):
        r.id = f"room_{i:03d}"

    logger.info(
        f"After anchoring: {len(anchored)} rooms "
        f"(labeled: {sum(1 for r in anchored if r.area_m2 is not None)}, "
        f"unlabeled: {sum(1 for r in anchored if r.area_m2 is None)}), "
        f"rejected fragments: {len(rejected)}"
    )

    return anchored, rejected


# ─── Классификация типа комнаты по площади + позиции ─────────────────────────


def classify_room_by_area(
    area_m2: float,
    area_px2: float,
    centroid: Point | None,
    img_area_px: float,
) -> RoomLabel:
    """
    Классификация типа комнаты по реальной площади (м²) и позиции.

    Намного надёжнее чем угадывать по фигурам/иконкам внутри.
    """
    # Очень маленькие — туалеты/санузлы
    if area_m2 < 3.5:
        # 2.7 в плане → туалет/совмещённый сантехузел
        return RoomLabel.toilet

    # 3.5–6.0 — обычно ванная или маленький балкон/кладовая
    if area_m2 < 6.0:
        # Балкон обычно вытянутый и у края изображения
        if centroid and _is_likely_balcony(centroid, area_px2, img_area_px):
            return RoomLabel.balcony
        return RoomLabel.bathroom

    # 6–9 — может быть санузел совмещённый, маленькая кухня, или коридор
    if area_m2 < 9.0:
        if _is_likely_corridor(area_px2, area_m2):
            return RoomLabel.corridor
        return RoomLabel.bathroom

    # 9–13 — кухня
    if area_m2 < 13.0:
        return RoomLabel.kitchen

    # 13–18 — спальня
    if area_m2 < 18.0:
        return RoomLabel.bedroom

    # 18+ — гостиная или большой коридор
    # Если очень вытянутая → коридор
    if _is_likely_corridor(area_px2, area_m2):
        return RoomLabel.corridor
    return RoomLabel.living_room


def _is_likely_balcony(
    centroid: Point, area_px2: float, img_area_px: float,
) -> bool:
    """
    Балконы и лоджии обычно у нижнего/верхнего края плана (не сбоку),
    и небольшой площади.
    Для упрощения считаем как balcony любую маленькую комнату 4-5м².
    Точнее — UI пусть пользователь поправит.
    """
    return False  # консервативно, чтобы не путать с ванной


def _is_likely_corridor(area_px2: float, area_m2: float) -> bool:
    """Коридор: средняя/большая площадь и обычно вытянутый.
    Без bbox информации — эвристика по соотношению."""
    # Без полигона тяжело сказать — оставляем False, классифицируем по area
    # Можно расширить если нужно: добавить параметр bbox aspect
    return False
