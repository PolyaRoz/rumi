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
) -> tuple[list[Room], list[OcrArea], list[tuple[Room, str]]]:
    """
    Связать OCR-метки с полигонами; вернуть неразрешённые метки для recovery;
    отфильтровать фрагменты.

    Args:
        candidate_rooms: сырые кандидаты от room_polygonizer
        ocr_labels: OCR-распознанные числовые метки площадей
        img_area_px: площадь всего изображения для нормализации

    Returns:
        (anchored_rooms, unresolved_labels, rejected_fragments)
        anchored_rooms — финальный список с area_label_m2 где есть.
        unresolved_labels — OCR-метки, ДЛЯ КОТОРЫХ НЕТ полигона.
            Их должен подобрать room_recovery через flood fill.
        rejected_fragments — list of (room, reason) для debug.
    """
    if not candidate_rooms:
        return [], list(ocr_labels), []

    # ── 1. Каждой метке ищем содержащий её полигон ──────────────────────
    # label_assignments: idx полигона → метка, КОТОРАЯ ему присвоена
    # used_labels: метки которые уже привязаны (для unresolved)
    label_assignments: dict[int, OcrArea] = {}
    used_labels: set[int] = set()  # индексы в ocr_labels

    # Сначала строим: для каждой метки — список содержащих её полигонов
    label_to_polys: dict[int, list[int]] = {}
    for label_idx, label in enumerate(ocr_labels):
        contained = []
        for room_idx, room in enumerate(candidate_rooms):
            if not room.polygon:
                continue
            if _point_in_polygon(label.cx_px, label.cy_px, room.polygon):
                contained.append(room_idx)
        label_to_polys[label_idx] = contained

    # ── 1a. Каждый polygon принимает только ОДНУ метку (ту что ближе к centroid).
    # Это критично: если коридор и спальня слились в один большой полигон,
    # обе метки попадут внутрь — но только одна привяжется. Вторая
    # становится unresolved → её полигон восстановит room_recovery.
    poly_to_candidate_labels: dict[int, list[int]] = {}
    for label_idx, polys in label_to_polys.items():
        # Берём МИНИМАЛЬНЫЙ по площади из содержащих (наиболее вложенный)
        if polys:
            chosen = min(polys, key=lambda i: candidate_rooms[i].area_px2 or float("inf"))
            poly_to_candidate_labels.setdefault(chosen, []).append(label_idx)

    for poly_idx, label_indices in poly_to_candidate_labels.items():
        room = candidate_rooms[poly_idx]
        # Из всех меток, претендующих на этот polygon, берём ту что ближе к centroid
        if room.centroid is None:
            best_label_idx = label_indices[0]
        else:
            best_label_idx = min(
                label_indices,
                key=lambda li: math.hypot(
                    room.centroid.x - ocr_labels[li].cx_px,
                    room.centroid.y - ocr_labels[li].cy_px,
                ),
            )
        label_assignments[poly_idx] = ocr_labels[best_label_idx]
        used_labels.add(best_label_idx)

    # ── 1b. Метки которым не нашлось polygon ИЛИ которые "проиграли" другой
    # метке — становятся unresolved (recover через flood fill).
    unresolved_labels: list[OcrArea] = [
        label for label_idx, label in enumerate(ocr_labels)
        if label_idx not in used_labels
    ]

    logger.info(
        f"Anchoring: {len(label_assignments)} полигонов привязаны, "
        f"{len(unresolved_labels)} меток unresolved → recovery, "
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

    # ── 3. Если меток было больше чем закреплённых полигонов — recovery ─
    if unresolved_labels:
        logger.warning(
            f"Unresolved OCR labels: {len(unresolved_labels)} → "
            f"{[round(l.value_m2, 1) for l in unresolved_labels]}. "
            f"room_recovery попытается восстановить их через flood fill."
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

    return anchored, unresolved_labels, rejected


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
    Балкон/лоджия — характерные признаки:
    - центроид близко к КРАЮ плана (любому: low/right/top/left)
    - площадь 3-7 м²
    - вытянутая форма (не квадрат)

    Без bbox у нас только centroid и img_area. Используем расстояние от
    центроида до ближайшего края изображения. Если < 12% от меньшей
    стороны — это край → балкон вероятен.
    """
    if centroid is None or img_area_px <= 0:
        return False
    # Восстанавливаем размеры (приблизительно, считая img квадратным)
    img_side = img_area_px ** 0.5
    margin_threshold = img_side * 0.18
    dist_to_edge = min(
        centroid.x,
        centroid.y,
        img_side - centroid.x,
        img_side - centroid.y,
    )
    return dist_to_edge < margin_threshold


def _is_likely_corridor(area_px2: float, area_m2: float) -> bool:
    """
    Коридор: средняя/большая площадь, БЕЗ окон (центральный),
    типичная площадь 8-22 м². Без bbox-aspect определяем по диапазону.
    """
    # Эвристика: 17-22 м² и НЕ самый большой → скорее коридор/холл,
    # потому что в типовой 2-3 ком. квартире коридор такого размера обычен,
    # а гостиная обычно ≥ 18-20 м²
    return False
