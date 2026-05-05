"""
Claude Vision Service для распознавания планов квартир.

Подход — гибридный:
  1. Claude Vision (claude-sonnet-4-5) распознаёт СЕМАНТИКУ:
       - какие комнаты есть, где их центры, площади, типы
       - где двери и окна
  2. OpenCV строит точную ГЕОМЕТРИЮ:
       - структурную маску стен (barrier для flood fill)
       - через flood fill из центроидов Клода → полигоны комнат
       - wall graph → стены с outer/inner классификацией
  3. Постобработка (room_expansion, door_validation) как прежде.

Это устраняет главные ошибки OpenCV-пайплайна:
  - "Лишние стены" от сантехники/мебели → Клод различает семантически
  - "Не все покрыто" → flood fill из реальных центроидов
  - "Двери непонятно где" → Клод читает дуги открывания визуально
"""

from __future__ import annotations

import base64
import json
import logging
import math
import os
import re

import cv2
import numpy as np

from app.schemas.geometry import (
    ApartmentGeometry,
    AreaLabel,
    ConfidenceScores,
    Constraints,
    Opening,
    OpeningType,
    Point,
    RejectedFragment,
    Room,
    RoomLabel,
    Scale,
    SwingDirection,
    Wall,
    WallType,
)
from app.services.door_validation import validate_doors_against_rooms
from app.services.preprocessing import preprocess
from app.services.room_anchoring import classify_room_by_area
from app.services.room_expansion import expand_rooms_to_walls
from app.services.structural_wall_mask import extract_wall_mask
from app.services.wall_detector import detect_walls
from app.services.wall_graph import build_wall_graph

logger = logging.getLogger(__name__)


# ─── Claude prompt ────────────────────────────────────────────────────────────

FLOOR_PLAN_PROMPT = """You are analyzing a Russian apartment floor plan image.

Your task: extract rooms, doors, and windows. Return ONLY valid JSON, no text.

JSON format:
{
  "rooms": [
    {
      "label": "living_room|bedroom|kitchen|bathroom|toilet|corridor|kids_room|balcony|storage|unknown",
      "area_m2": 16.3,
      "centroid_x": 0.45,
      "centroid_y": 0.32,
      "bbox": [x_min, y_min, x_max, y_max]
    }
  ],
  "openings": [
    {
      "type": "door|window",
      "x": 0.4,
      "y": 0.25,
      "width": 0.04,
      "swing": "left|right|inward|outward|unknown"
    }
  ]
}

All coordinates are NORMALIZED (0.0 = left/top, 1.0 = right/bottom).

ROOM IDENTIFICATION RULES:
- Look for numbers printed inside rooms — these are area in m² (e.g. "4.5", "16.3", "17.2")
- Use the number as area_m2
- Determine label by area AND shape:
  - corridor (коридор): elongated narrow space connecting rooms, 2-10 m²
  - bathroom (ванная): has bathtub/shower symbol, 2-8 m²
  - toilet (туалет/WC): very small isolated room, 1-4 m²
  - kitchen (кухня): has sink/counter symbols, 6-18 m²
  - living_room (гостиная): largest or second-largest room, 12-35 m²
  - bedroom (спальня): medium room, 9-22 m²
  - balcony: thin narrow room along outer wall
  - storage: very small room, 1-5 m², no fixtures

OPENING IDENTIFICATION (BE CONSERVATIVE):
- DOOR: a clear gap in a wall WITH a quarter-circle arc showing swing direction.
  The arc is drawn with its flat edge at the wall gap and curved edge sweeping the door path.
  Report only doors you are CERTAIN about — a typical apartment has 4-8 doors.
  DO NOT report: furniture curves, bathtub/toilet shapes, round objects as doors.
  Position x,y = center of the wall gap (not center of the arc).
- WINDOW: parallel double lines embedded in outer (exterior) wall only.
  Report only clear window symbols — a typical apartment has 3-7 windows.
  DO NOT report: interior wall gaps without clear double-line symbol as windows.

CRITICAL: Report ONLY real structural openings in walls.
A typical 2-bedroom apartment has: 5-7 doors, 3-6 windows.
If you see more than 10 doors total, you are likely misidentifying furniture as doors.

Return area_m2 exactly as written in the image. If you cannot read a number, estimate from room size.
Return ONLY JSON. No explanation, no markdown blocks."""


# ─── Главная функция ──────────────────────────────────────────────────────────

def analyze_with_vision(image: np.ndarray, include_debug: bool = False) -> ApartmentGeometry:
    """
    Анализ плана квартиры через Claude Vision + OpenCV геометрия.

    Args:
        image: BGR numpy array (OpenCV)
        include_debug: включить base64 debug-слои

    Returns:
        ApartmentGeometry с заполненными rooms, openings, walls, scale
    """
    h, w = image.shape[:2]
    logger.info(f"[vision] Начинаем анализ плана {w}×{h}px")

    # ── 1. Вызов Claude Vision ─────────────────────────────────────────────────
    vision_result = _call_claude_vision(image)
    if vision_result is None:
        logger.warning("[vision] Claude Vision вернул None, используем заглушку")
        vision_result = {"rooms": [], "openings": []}

    raw_rooms = vision_result.get("rooms", [])
    raw_openings = vision_result.get("openings", [])
    logger.info(f"[vision] Claude распознал: {len(raw_rooms)} комнат, {len(raw_openings)} проёмов")

    # ── 2. OpenCV: предобработка + структурная маска стен ────────────────────
    plan = preprocess(image)
    structural_mask, _ = extract_wall_mask(plan.binary)
    plan.walls_mask = structural_mask

    # Закрываем проёмы чтобы flood fill не вытекал через двери
    closed_mask = _close_gaps(structural_mask)

    # ── 3. Комнаты через flood fill из центроидов Claude ──────────────────────
    rooms, area_labels = _build_rooms_from_vision(
        raw_rooms, closed_mask, structural_mask, w, h
    )
    logger.info(f"[vision] Построено {len(rooms)} полигонов комнат")

    # ── 4. Расширяем комнаты до стен (убираем белые зазоры) ──────────────────
    if rooms:
        rooms = expand_rooms_to_walls(rooms, structural_mask, max_expand_px=35)
        logger.info(f"[vision] После expansion: {len(rooms)} комнат")

    # ── 5. Wall graph (нужен для стен и wall_id у проёмов) ───────────────────
    walls_pre_split, _ = detect_walls(plan)
    graph = build_wall_graph(walls_pre_split, w, h)
    raw_walls = [edge.wall for edge in graph.edges.values()]
    logger.info(f"[vision] Стен до фильтрации: {len(raw_walls)}")

    # Фильтруем «стены», которые на самом деле находятся внутри комнат:
    # настоящая стена — на границе между комнатами или на периметре,
    # фиктивная — внутри комнаты (мебель, сантехника, дуги дверей).
    walls = _filter_walls_outside_rooms(raw_walls, rooms)
    logger.info(f"[vision] Стен после фильтрации: {len(walls)} (убрано {len(raw_walls)-len(walls)})")

    # ── 6. Масштаб из OCR-площадей ─────────────────────────────────────────────
    scale = _estimate_scale(rooms, w, h)
    px_per_meter = scale.px_per_meter

    # Обновляем area_m2 для комнат если есть масштаб
    if px_per_meter:
        for room in rooms:
            if room.area_px2 and not room.area_m2:
                room.area_m2 = round(room.area_px2 / (px_per_meter ** 2), 1)

    # ── 7. Проёмы из Claude Vision ─────────────────────────────────────────────
    openings = _build_openings_from_vision(
        raw_openings, walls_pre_split or walls, w, h, px_per_meter
    )
    logger.info(f"[vision] Проёмов: {len(openings)}")

    # ── 8. Валидация дверей по прилежанию к комнатам ─────────────────────────
    if rooms:
        openings, rejected_doors = validate_doors_against_rooms(openings, rooms, proximity_px=40)
        logger.info(
            f"[vision] Дверей после валидации: "
            f"{len([o for o in openings if o.type == OpeningType.door])}, "
            f"отброшено: {len(rejected_doors)}"
        )
        # Убираем двери глубоко внутри комнаты (мебельные дуги)
        openings = _filter_openings_outside_rooms(openings, rooms)

    # ── 8b. Хард-кап: не более 8 дверей и 8 окон ─────────────────────────────
    # Claude иногда видит 20+ "дверей" из мебельных дуг и символов.
    # Реальная квартира имеет 4-8 дверей и 3-7 окон.
    openings = _cap_openings(openings, max_doors=8, max_windows=8)

    # ── 9. Confidence scores ──────────────────────────────────────────────────
    n_rooms = len(rooms)
    n_doors = len([o for o in openings if o.type == OpeningType.door])
    n_windows = len([o for o in openings if o.type == OpeningType.window])

    confidence = ConfidenceScores(
        wall_confidence=0.75 if len(walls) >= 8 else 0.5,
        room_confidence=min(1.0, 0.6 + 0.05 * n_rooms) if n_rooms > 0 else 0.0,
        door_confidence=min(1.0, 0.6 + 0.05 * n_doors) if n_doors > 0 else 0.3,
        window_confidence=min(1.0, 0.5 + 0.05 * n_windows) if n_windows > 0 else 0.2,
        scale_confidence=scale.confidence,
    )

    # ── 10. Сборка ApartmentGeometry ─────────────────────────────────────────
    geometry = ApartmentGeometry(
        source_image_width_px=w,
        source_image_height_px=h,
        scale=scale,
        walls=walls,
        openings=openings,
        rooms=rooms,
        constraints=Constraints(),
        confidence=confidence,
        detected_area_labels=area_labels,
        rejected_fragments=[],
    )

    logger.info(
        f"[vision] Итог: {len(rooms)} комнат, {len(walls)} стен, "
        f"{n_doors} дверей, {n_windows} окон, "
        f"scale={px_per_meter:.1f}px/m" if px_per_meter else
        f"[vision] Итог: {len(rooms)} комнат, {len(walls)} стен, {n_doors} дверей"
    )
    return geometry


# ─── Claude Vision API ────────────────────────────────────────────────────────

def _get_api_key() -> str:
    """Читать ANTHROPIC_API_KEY: сначала из os.environ, потом из .env через pydantic-settings."""
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return key
    try:
        from app.config import get_settings
        key = get_settings().anthropic_api_key
    except Exception:
        pass
    if not key:
        # Последняя попытка: читаем .env напрямую
        import pathlib
        env_path = pathlib.Path(__file__).parents[2] / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("ANTHROPIC_API_KEY="):
                    key = line.split("=", 1)[1].strip()
                    break
    return key


def _call_claude_vision(image: np.ndarray) -> dict | None:
    """
    Отправить изображение в Claude Vision и получить распознанную геометрию.
    """
    api_key = _get_api_key()
    if not api_key:
        logger.error("[vision] ANTHROPIC_API_KEY не задан!")
        return None

    try:
        import anthropic
    except ImportError:
        logger.error("[vision] anthropic SDK не установлен. pip install anthropic")
        return None

    # Конвертируем в JPEG для API
    _, jpeg_bytes = cv2.imencode(
        ".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 90]
    )
    b64_image = base64.b64encode(jpeg_bytes.tobytes()).decode("utf-8")

    logger.info(f"[vision] Отправляем {len(jpeg_bytes)} байт в Claude Vision...")

    client = anthropic.Anthropic(api_key=api_key)

    try:
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": b64_image,
                            },
                        },
                        {
                            "type": "text",
                            "text": FLOOR_PLAN_PROMPT,
                        },
                    ],
                }
            ],
        )

        raw_text = message.content[0].text
        logger.info(f"[vision] Claude ответил: {len(raw_text)} символов")
        logger.debug(f"[vision] Ответ: {raw_text[:500]}")

        return _parse_vision_response(raw_text)

    except Exception as e:
        logger.exception(f"[vision] Ошибка вызова Claude Vision: {e}")
        return None


def _parse_vision_response(text: str) -> dict | None:
    """Распарсить JSON из ответа Claude."""
    # Claude может добавить markdown ```json ... ```
    text = text.strip()
    text = re.sub(r"^```json\s*", "", text)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    try:
        result = json.loads(text)
        return result
    except json.JSONDecodeError as e:
        logger.error(f"[vision] JSON parse error: {e}")
        logger.error(f"[vision] Текст ответа: {text[:500]}")
        # Попробуем найти JSON в тексте
        match = re.search(r"\{[\s\S]+\}", text)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
        return None


# ─── Построение комнат через flood fill ──────────────────────────────────────

def _close_gaps(wall_mask: np.ndarray) -> np.ndarray:
    """Закрыть дверные проёмы для надёжного flood fill."""
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    closed = cv2.morphologyEx(wall_mask, cv2.MORPH_CLOSE, kernel, iterations=3)
    return closed


def _build_rooms_from_vision(
    raw_rooms: list[dict],
    closed_mask: np.ndarray,
    wall_mask: np.ndarray,
    img_w: int,
    img_h: int,
) -> tuple[list[Room], list[AreaLabel]]:
    """
    Для каждой комнаты из Claude:
    1. Конвертируем нормализованный центроид → пиксели
    2. Flood fill из этой точки на closed_mask
    3. Извлекаем полигон

    Returns:
        (rooms, area_labels)
    """
    h, w = closed_mask.shape
    interior = cv2.bitwise_not(closed_mask)

    rooms: list[Room] = []
    area_labels: list[AreaLabel] = []
    img_area_px = float(img_w * img_h)

    for idx, r in enumerate(raw_rooms):
        area_m2 = _safe_float(r.get("area_m2"))
        cx_norm = _safe_float(r.get("centroid_x", 0.5))
        cy_norm = _safe_float(r.get("centroid_y", 0.5))
        label_str = r.get("label", "unknown")

        # Пиксельные координаты центроида
        cx_px = int(cx_norm * img_w)
        cy_px = int(cy_norm * img_h)
        cx_px = max(0, min(img_w - 1, cx_px))
        cy_px = max(0, min(img_h - 1, cy_px))

        # AreaLabel для UI
        if area_m2 is not None:
            area_labels.append(AreaLabel(
                text=str(area_m2),
                value_m2=area_m2,
                position=Point(x=float(cx_px), y=float(cy_px)),
                confidence=0.9,
                assigned_room_id=None,  # обновим после flood fill
                recovered_room_id=None,
            ))

        # Поиск ближайшей точки interior если seed на стене
        seed_x, seed_y = _find_interior_seed(interior, cx_px, cy_px, w, h)
        if seed_x is None:
            logger.warning(f"[vision] Комната {idx} ({area_m2}м²) — нет interior рядом с ({cx_px},{cy_px})")
            continue

        # Flood fill
        scratch = interior.copy()
        flood_mask = np.zeros((h + 2, w + 2), dtype=np.uint8)
        cv2.floodFill(scratch, flood_mask, (seed_x, seed_y), 128)
        room_mask = (scratch == 128).astype(np.uint8) * 255
        area_px = int(np.sum(room_mask > 0))

        if area_px < 500:
            logger.warning(f"[vision] Комната {idx} ({area_m2}м²) слишком мала: {area_px}px²")
            continue

        # Проверка на overflow (flood fill вышел за пределы комнаты)
        # Комната не может занимать > 60% площади изображения
        if area_px > img_area_px * 0.60:
            logger.warning(
                f"[vision] Комната {idx} ({area_m2}м²) overflow: "
                f"{area_px}px² = {area_px/img_area_px:.0%} image — пропускаем"
            )
            continue

        # Если знаем площадь от Claude — проверяем что flood fill не в 10× больше ожидаемого
        if area_m2 and area_m2 > 0 and len(rooms) > 0:
            # Оценим px_per_m² из уже построенных комнат
            known = [(r.area_m2, r.area_px2) for r in rooms if r.area_m2 and r.area_px2 and r.area_m2 > 1.0]
            if known:
                median_ratio = sorted(p / m for m, p in known)[len(known) // 2]
                expected_px = area_m2 * median_ratio
                if area_px > expected_px * 10:
                    logger.warning(
                        f"[vision] Комната {idx} ({area_m2}м²) overflow по соотношению: "
                        f"{area_px}px² ожидалось ≈{expected_px:.0f}px² — пропускаем"
                    )
                    continue

        # Контур → полигон
        contours, _ = cv2.findContours(room_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue
        cnt = max(contours, key=cv2.contourArea)
        perimeter = cv2.arcLength(cnt, True)
        epsilon = 0.008 * perimeter
        approx = cv2.approxPolyDP(cnt, epsilon, True)
        polygon = [Point(x=float(p[0][0]), y=float(p[0][1])) for p in approx]

        if len(polygon) < 3:
            continue

        # Centroid из моментов
        M = cv2.moments(cnt)
        if M["m00"] > 0:
            actual_cx = M["m10"] / M["m00"]
            actual_cy = M["m01"] / M["m00"]
        else:
            actual_cx, actual_cy = float(cx_px), float(cy_px)

        # Тип комнаты
        room_label = _parse_room_label(label_str, area_m2)

        room_id = f"room_{idx:03d}"
        room = Room(
            id=room_id,
            label=room_label,
            area_m2=area_m2,
            area_px2=float(area_px),
            polygon=polygon,
            centroid=Point(x=round(actual_cx, 1), y=round(actual_cy, 1)),
            locked=True,
            confidence=0.90,
        )
        rooms.append(room)

        # Привязываем AreaLabel к комнате
        if area_labels:
            area_labels[-1].assigned_room_id = room_id

        logger.info(
            f"[vision] Комната {room_id}: {room_label.value}, "
            f"{area_m2}м², area_px={area_px}"
        )

    return rooms, area_labels


def _find_interior_seed(
    interior: np.ndarray,
    cx: int,
    cy: int,
    w: int,
    h: int,
    max_radius: int = 40,
) -> tuple[int | None, int | None]:
    """Найти ближайший interior-пиксель к (cx, cy)."""
    if 0 <= cx < w and 0 <= cy < h and interior[cy, cx] > 0:
        return cx, cy

    for r in range(1, max_radius + 1):
        for dx in range(-r, r + 1):
            for dy in (-r, r):
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < w and 0 <= ny < h and interior[ny, nx] > 0:
                    return nx, ny
        for dy in range(-r + 1, r):
            for dx in (-r, r):
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < w and 0 <= ny < h and interior[ny, nx] > 0:
                    return nx, ny
    return None, None


# ─── Построение проёмов ───────────────────────────────────────────────────────

def _build_openings_from_vision(
    raw_openings: list[dict],
    walls: list[Wall],
    img_w: int,
    img_h: int,
    px_per_meter: float | None,
) -> list[Opening]:
    """Конвертируем проёмы из нормализованных координат Claude в Opening объекты."""
    openings: list[Opening] = []

    for idx, o in enumerate(raw_openings):
        x_norm = _safe_float(o.get("x", 0.5))
        y_norm = _safe_float(o.get("y", 0.5))
        width_norm = _safe_float(o.get("width", 0.04)) or 0.04
        type_str = o.get("type", "door").lower()
        swing_str = o.get("swing", "unknown").lower()

        # Пиксельные координаты
        px = x_norm * img_w
        py = y_norm * img_h
        width_px = width_norm * img_w

        # Тип
        opening_type = OpeningType.door if type_str == "door" else OpeningType.window

        # Направление открывания
        swing_map = {
            "left": SwingDirection.left,
            "right": SwingDirection.right,
            "inward": SwingDirection.inward,
            "outward": SwingDirection.outward,
        }
        swing = swing_map.get(swing_str, SwingDirection.unknown)

        # Ближайшая стена
        wall_id = _find_nearest_wall(px, py, walls)

        width_m = round(width_px / px_per_meter, 2) if px_per_meter and width_px else None

        op = Opening(
            id=f"{type_str}_{idx:03d}",
            type=opening_type,
            wall_id=wall_id or "wall_unknown",
            position=Point(x=round(px, 1), y=round(py, 1)),
            width_px=round(float(width_px), 1),
            width_m=width_m,
            swing_direction=swing,
            clearance_m=0.8 if opening_type == OpeningType.door else 0.5,
            locked=True,
            confidence=0.85,
        )
        openings.append(op)

    return openings


def _find_nearest_wall(px: float, py: float, walls: list[Wall]) -> str | None:
    """Найти ближайшую стену к точке."""
    if not walls:
        return None
    min_dist = float("inf")
    best_id = None
    for wall in walls:
        d = _dist_point_to_segment(
            px, py,
            wall.start.x, wall.start.y,
            wall.end.x, wall.end.y,
        )
        if d < min_dist:
            min_dist = d
            best_id = wall.id
    return best_id


def _dist_point_to_segment(
    px: float, py: float,
    ax: float, ay: float,
    bx: float, by: float,
) -> float:
    dx, dy = bx - ax, by - ay
    ll = dx * dx + dy * dy
    if ll == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / ll))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


# ─── Масштаб из площадей комнат ──────────────────────────────────────────────

def _estimate_scale(rooms: list[Room], img_w: int, img_h: int) -> Scale:
    """Оценить масштаб по площадям из Claude Vision."""
    if not rooms:
        return Scale(source="unknown", confidence=0.0)

    # Собираем пары (area_m2, area_px2)
    valid_pairs = [
        (r.area_m2, r.area_px2)
        for r in rooms
        if r.area_m2 and r.area_px2 and r.area_m2 > 1.0
    ]

    if not valid_pairs:
        return Scale(source="unknown", confidence=0.0)

    # px_per_meter = sqrt(area_px2 / area_m2)
    estimates = [
        math.sqrt(area_px / area_m2)
        for area_m2, area_px in valid_pairs
    ]

    # Медиана
    estimates.sort()
    mid = len(estimates) // 2
    px_per_m = estimates[mid]

    # Confidence: чем больше согласованных оценок, тем выше
    if len(estimates) >= 3:
        spread = max(estimates) - min(estimates)
        relative_spread = spread / px_per_m if px_per_m > 0 else 1.0
        conf = max(0.5, min(0.95, 1.0 - relative_spread * 0.5))
    elif len(estimates) == 2:
        conf = 0.7
    else:
        conf = 0.6

    logger.info(
        f"[vision] Масштаб: {px_per_m:.1f} px/m "
        f"(из {len(estimates)} оценок, conf={conf:.2f})"
    )

    return Scale(
        px_per_meter=round(px_per_m, 2),
        source="detected_from_area_labels",
        confidence=conf,
    )


# ─── Вспомогательные функции ──────────────────────────────────────────────────

def _safe_float(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _point_in_poly(px: float, py: float, polygon: list[Point]) -> bool:
    """Ray-casting: точка внутри полигона."""
    n = len(polygon)
    if n < 3:
        return False
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i].x, polygon[i].y
        xj, yj = polygon[j].x, polygon[j].y
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi + 1e-10) + xi):
            inside = not inside
        j = i
    return inside


def _filter_walls_outside_rooms(walls: list, rooms: list) -> list:
    """
    Убрать стены, чья средняя точка лежит ВНУТРИ комнатного полигона.

    Настоящая стена — на ГРАНИЦЕ между комнатами или по периметру.
    Ложная стена (мебель, сантехника, дуга двери) — нарисована ВНУТРИ комнаты.

    Логика: flood fill заполняет интерьер, поэтому пиксели внутри комнаты
    попадают в room.polygon. Пиксели структурных стен — между полигонами.
    """
    if not rooms or not walls:
        return walls

    filtered = []
    for wall in walls:
        mid_x = (wall.start.x + wall.end.x) / 2
        mid_y = (wall.start.y + wall.end.y) / 2

        in_room = any(
            _point_in_poly(mid_x, mid_y, room.polygon)
            for room in rooms
            if room.polygon and len(room.polygon) >= 3
        )

        if not in_room:
            filtered.append(wall)
        else:
            logger.debug(
                f"[vision] Удалена ложная стена {wall.id} "
                f"({wall.start.x:.0f},{wall.start.y:.0f})→"
                f"({wall.end.x:.0f},{wall.end.y:.0f}): внутри комнаты"
            )

    return filtered


def _cap_openings(openings: list, max_doors: int = 8, max_windows: int = 8) -> list:
    """
    Ограничить количество дверей и окон.
    Если Claude нашёл >max_doors дверей, оставляем только наиболее широкие
    (настоящие двери шире, чем мебельные дуги).
    """
    doors   = [o for o in openings if o.type == OpeningType.door]
    windows = [o for o in openings if o.type == OpeningType.window]
    others  = [o for o in openings if o.type not in (OpeningType.door, OpeningType.window)]

    if len(doors) > max_doors:
        # Сортируем по ширине убывая: реальные двери (0.6-1.0м) шире мебельных дуг
        doors.sort(key=lambda d: d.width_px, reverse=True)
        logger.info(
            f"[vision] Хард-кап дверей: {len(doors)} → {max_doors} "
            f"(оставляем самые широкие)"
        )
        doors = doors[:max_doors]

    if len(windows) > max_windows:
        windows.sort(key=lambda w: w.width_px, reverse=True)
        logger.info(f"[vision] Хард-кап окон: {len(windows)} → {max_windows}")
        windows = windows[:max_windows]

    return others + doors + windows


def _filter_openings_outside_rooms(openings: list, rooms: list) -> list:
    """
    Убрать двери/окна, чья позиция лежит глубоко ВНУТРИ комнаты.

    Настоящий проём — в стене, то есть на КРАЮ комнатного полигона.
    Ложный проём (мебель-дуга) — в центре комнаты.

    Допускаем расстояние до края полигона ≤ 30px, иначе — ложный.
    """
    if not rooms or not openings:
        return openings

    MAX_INTERIOR_DIST = 30  # px

    filtered = []
    for op in openings:
        px, py = op.position.x, op.position.y

        # Найти минимальное расстояние до границы любой комнаты
        min_dist_to_edge = float("inf")
        for room in rooms:
            if not room.polygon or len(room.polygon) < 3:
                continue
            if not _point_in_poly(px, py, room.polygon):
                continue
            # Точка внутри этой комнаты — найти расстояние до её края
            n = len(room.polygon)
            for i in range(n):
                a = room.polygon[i]
                b = room.polygon[(i + 1) % n]
                dx, dy = b.x - a.x, b.y - a.y
                ll = dx * dx + dy * dy
                if ll == 0:
                    d = math.hypot(px - a.x, py - a.y)
                else:
                    t = max(0.0, min(1.0, ((px - a.x) * dx + (py - a.y) * dy) / ll))
                    d = math.hypot(px - (a.x + t * dx), py - (a.y + t * dy))
                min_dist_to_edge = min(min_dist_to_edge, d)

        if min_dist_to_edge <= MAX_INTERIOR_DIST or min_dist_to_edge == float("inf"):
            # На краю комнаты или снаружи комнат → настоящий проём
            filtered.append(op)
        else:
            logger.info(
                f"[vision] Удалён ложный проём {op.id} "
                f"({px:.0f},{py:.0f}): глубина внутри комнаты {min_dist_to_edge:.0f}px"
            )

    return filtered


def _parse_room_label(label_str: str, area_m2: float | None) -> RoomLabel:
    """Конвертировать строку типа комнаты в RoomLabel enum.
    Обрабатывает snake_case и Plain English (Bathroom, Hallway, etc.)
    """
    s = label_str.lower().strip()
    mapping = {
        # snake_case (из prompt)
        "living_room": RoomLabel.living_room,
        "bedroom": RoomLabel.bedroom,
        "kitchen": RoomLabel.kitchen,
        "bathroom": RoomLabel.bathroom,
        "toilet": RoomLabel.toilet,
        "corridor": RoomLabel.corridor,
        "kids_room": RoomLabel.kids_room,
        "balcony": RoomLabel.balcony,
        "storage": RoomLabel.storage,
        # Plain English words Claude иногда возвращает
        "living room": RoomLabel.living_room,
        "living": RoomLabel.living_room,
        "lounge": RoomLabel.living_room,
        "sitting room": RoomLabel.living_room,
        "room": RoomLabel.unknown,   # generic, fallback по площади
        "bath": RoomLabel.bathroom,
        "wc": RoomLabel.toilet,
        "restroom": RoomLabel.toilet,
        "hallway": RoomLabel.corridor,
        "hall": RoomLabel.corridor,
        "entrance": RoomLabel.corridor,
        "entryway": RoomLabel.corridor,
        "foyer": RoomLabel.corridor,
        "pantry": RoomLabel.storage,
        "closet": RoomLabel.storage,
        "wardrobe": RoomLabel.storage,
        "laundry": RoomLabel.bathroom,
        "utility": RoomLabel.storage,
        "kids": RoomLabel.kids_room,
        "child": RoomLabel.kids_room,
        "nursery": RoomLabel.kids_room,
        "terrace": RoomLabel.balcony,
        "patio": RoomLabel.balcony,
        "loggia": RoomLabel.balcony,
    }
    label = mapping.get(s, RoomLabel.unknown)

    # Частичное совпадение если нет точного
    if label == RoomLabel.unknown:
        for key, val in mapping.items():
            if key in s or s in key:
                label = val
                break

    # Fallback по площади если всё ещё unknown
    if label == RoomLabel.unknown and area_m2 is not None:
        label = classify_room_by_area(area_m2, area_m2 * 3600, None, 1_000_000)

    return label
