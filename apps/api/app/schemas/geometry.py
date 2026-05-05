"""
Pydantic-схемы структурированной геометрии квартиры.

Этот JSON создаётся CV-пайплайном по изображению плана и считается
источником истины для всех последующих шагов. После подтверждения
пользователем геометрия блокируется (locked=True) и не может изменяться
AI-модулем — ни стены, ни комнаты, ни проёмы.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# ─── Примитивы ───────────────────────────────────────────────────────────────


class Point(BaseModel):
    x: float
    y: float


class Scale(BaseModel):
    px_per_meter: float | None = None
    source: Literal[
        "detected_from_area_labels",
        "detected_from_scale_bar",
        "user_input",
        "calculated",
        "unknown",
    ] = "unknown"
    confidence: float = Field(0.0, ge=0.0, le=1.0)


# ─── Стены ───────────────────────────────────────────────────────────────────


class WallType(str, Enum):
    outer = "outer"
    inner = "inner"
    unknown = "unknown"


class Wall(BaseModel):
    id: str
    type: WallType = WallType.unknown
    start: Point
    end: Point
    thickness_px: float = 8.0
    locked: bool = True
    confidence: float = Field(1.0, ge=0.0, le=1.0)

    @property
    def length_px(self) -> float:
        dx = self.end.x - self.start.x
        dy = self.end.y - self.start.y
        return (dx**2 + dy**2) ** 0.5


# ─── Проёмы (двери, окна) ────────────────────────────────────────────────────


class OpeningType(str, Enum):
    door = "door"
    window = "window"


class SwingDirection(str, Enum):
    left = "left"
    right = "right"
    inward = "inward"
    outward = "outward"
    unknown = "unknown"


class Opening(BaseModel):
    id: str
    type: OpeningType
    wall_id: str
    position: Point          # центр проёма
    width_px: float
    width_m: float | None = None
    swing_direction: SwingDirection = SwingDirection.unknown
    # Зона запрета для мебели (ширина от проёма в каждую сторону, метры)
    clearance_m: float = 0.8
    locked: bool = True
    confidence: float = Field(1.0, ge=0.0, le=1.0)


# ─── Комнаты ─────────────────────────────────────────────────────────────────


class RoomLabel(str, Enum):
    living_room = "living_room"
    bedroom = "bedroom"
    kitchen = "kitchen"
    bathroom = "bathroom"
    toilet = "toilet"
    corridor = "corridor"
    kids_room = "kids_room"
    balcony = "balcony"
    storage = "storage"
    unknown = "unknown"


class Room(BaseModel):
    id: str
    label: RoomLabel = RoomLabel.unknown
    area_m2: float | None = None           # из OCR-подписей на плане
    area_px2: float | None = None          # площадь полигона в пикселях
    polygon: list[Point]                   # замкнутый полигон стен
    centroid: Point | None = None          # геометрический центр
    locked: bool = True
    confidence: float = Field(1.0, ge=0.0, le=1.0)

    # Стены, ограничивающие эту комнату (для правил размещения)
    wall_ids: list[str] = Field(default_factory=list)
    opening_ids: list[str] = Field(default_factory=list)


# ─── Ограничения ─────────────────────────────────────────────────────────────


class Constraints(BaseModel):
    do_not_move_walls: bool = True
    do_not_resize_rooms: bool = True
    do_not_block_doors: bool = True
    do_not_block_windows: bool = False    # окно можно загородить шкафом с разрешения
    keep_clearance_near_doors_m: float = 0.8
    keep_walkway_width_m: float = 0.7
    keep_kitchen_passage_m: float = 0.9  # рабочий проход перед кухней
    keep_wardrobe_clearance_m: float = 0.6
    mode: Literal["no_remodel", "light_remodel", "full_remodel"] = "no_remodel"


# ─── Confidence scores ───────────────────────────────────────────────────────


class ConfidenceScores(BaseModel):
    wall_confidence: float = Field(0.0, ge=0.0, le=1.0)
    room_confidence: float = Field(0.0, ge=0.0, le=1.0)
    door_confidence: float = Field(0.0, ge=0.0, le=1.0)
    window_confidence: float = Field(0.0, ge=0.0, le=1.0)
    scale_confidence: float = Field(0.0, ge=0.0, le=1.0)

    @property
    def overall(self) -> float:
        scores = [
            self.wall_confidence,
            self.room_confidence,
            self.door_confidence,
            self.window_confidence,
            self.scale_confidence,
        ]
        return sum(scores) / len(scores)

    def needs_user_validation(self, threshold: float = 0.6) -> bool:
        """Запросить у пользователя подтверждение, если уверенность низкая."""
        return self.overall < threshold


# ─── Отладочные данные ───────────────────────────────────────────────────────


class DebugLayers(BaseModel):
    """URL временных изображений для debug-оверлея (base64 или presigned URL)."""
    original: str | None = None
    preprocessed: str | None = None
    walls_detected: str | None = None
    rooms_detected: str | None = None
    doors_detected: str | None = None
    windows_detected: str | None = None
    scale_overlay: str | None = None
    final_geometry: str | None = None


class AreaLabel(BaseModel):
    """Распознанная OCR-метка площади на плане."""
    text: str                              # как Tesseract увидел: "14,4", "17,2", "27"
    value_m2: float                        # нормализовано в float
    position: Point                        # координата центра текста на изображении
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    # Если метка привязана к комнате — её id; иначе None (unresolved).
    # Unresolved label = критический сигнал для UI: пользователь должен либо
    # восстановить комнату через flood fill, либо подтвердить что это не комната.
    assigned_room_id: str | None = None
    # Если метку восстановили через recovery — id восстановленной комнаты
    recovered_room_id: str | None = None


class RejectedFragment(BaseModel):
    """
    Polygon-кандидат, который НЕ стал комнатой.
    Сохраняем чтобы UI мог показать пользователю и спросить — может это комната.
    """
    id: str
    polygon: list[Point]
    area_px2: float
    centroid: Point | None = None
    reason: str                            # "no_area_label_and_too_small" | "duplicate" | ...


# ─── Главная модель ───────────────────────────────────────────────────────────


class ApartmentGeometry(BaseModel):
    """
    Структурированная геометрическая модель квартиры.
    Создаётся CV-пайплайном. После user-валидации становится locked.

    Эта модель — единственный источник истины для:
    - расстановки мебели (FurniturePlacementEngine)
    - валидатора (LayoutValidator)
    - рендерера (FloorPlanRenderer)
    """
    source_image_width_px: int
    source_image_height_px: int
    scale: Scale = Field(default_factory=Scale)
    walls: list[Wall] = Field(default_factory=list)
    openings: list[Opening] = Field(default_factory=list)
    rooms: list[Room] = Field(default_factory=list)
    constraints: Constraints = Field(default_factory=Constraints)
    confidence: ConfidenceScores = Field(default_factory=ConfidenceScores)
    debug: DebugLayers | None = None

    # Прозрачность распознавания: всё что увидел CV для UI-валидации
    detected_area_labels: list[AreaLabel] = Field(default_factory=list)
    rejected_fragments: list[RejectedFragment] = Field(default_factory=list)

    # Подтверждена ли геометрия пользователем
    user_validated: bool = False
    validation_notes: str = ""

    def get_room(self, room_id: str) -> Room | None:
        return next((r for r in self.rooms if r.id == room_id), None)

    def get_wall(self, wall_id: str) -> Wall | None:
        return next((w for w in self.walls if w.id == wall_id), None)

    def get_opening(self, opening_id: str) -> Opening | None:
        return next((o for o in self.openings if o.id == opening_id), None)

    def doors(self) -> list[Opening]:
        return [o for o in self.openings if o.type == OpeningType.door]

    def windows(self) -> list[Opening]:
        return [o for o in self.openings if o.type == OpeningType.window]
