"""
Pydantic-схемы каталога мебели и результата расстановки.

FurnitureCatalogItem — расширенная схема товара с правилами размещения.
PlacedFurniture — результат layout-engine: позиция + ориентация.
FurniturePlacement — полный план расстановки для всей квартиры.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.geometry import Point


# ─── Каталог ─────────────────────────────────────────────────────────────────


class FurnitureDimensions(BaseModel):
    width_m: float      # ширина (вдоль стены)
    depth_m: float      # глубина (от стены в комнату)
    height_m: float     # высота


class PlacementRules(BaseModel):
    against_wall: bool = True          # должна стоять вплотную к стене
    min_clearance_front_m: float = 0.6  # минимальный проход спереди
    min_clearance_sides_m: float = 0.3  # минимальный зазор сбоку
    min_clearance_back_m: float = 0.05  # зазор сзади (к стене)
    avoid_blocking_windows: bool = False
    avoid_blocking_doors: bool = True
    wet_zone_only: bool = False        # только в санузлах (сантехника)
    kitchen_zone_only: bool = False    # только кухня
    anchor_to: Literal[
        "any_wall", "outer_wall", "free_standing",
        "fixed",    # нельзя двигать (сантехника, ванна, плита)
    ] = "any_wall"


RoomTypeKey = Literal[
    "living_room", "bedroom", "kitchen", "bathroom",
    "toilet", "corridor", "kids_room", "balcony", "storage"
]

StyleTag = Literal["scandi", "minimal", "loft", "classic", "any"]

CategoryKey = Literal[
    "sofa", "armchair", "bed", "wardrobe", "dresser",
    "nightstand", "table", "chair", "rug", "ottoman",
    "tv_unit", "bookshelf", "desk", "kitchen_set",
    "bathroom_fixture", "toilet", "bathtub", "shower",
]


class FurnitureCatalogItem(BaseModel):
    """Единица каталога мебели с полными данными для размещения."""
    id: str
    name: str
    category: CategoryKey
    store: str = "Hoff"
    price_rub: int
    old_price_rub: int | None = None
    discount_percent: int | None = None
    url: str
    image_url: str
    dimensions: FurnitureDimensions
    style_tags: list[StyleTag] = Field(default_factory=lambda: ["any"])
    room_types: list[RoomTypeKey] = Field(default_factory=list)
    placement_rules: PlacementRules = Field(default_factory=PlacementRules)
    color: str | None = None
    material: str | None = None


# ─── Результат расстановки ────────────────────────────────────────────────────


class PlacedFurniture(BaseModel):
    """Конкретный предмет мебели, размещённый в комнате."""
    item_id: str            # ссылка на FurnitureCatalogItem.id
    room_id: str            # ссылка на Room.id
    position: Point         # координата левого-нижнего угла (в пикселях)
    rotation_deg: float = 0.0   # угол поворота (0=у нижней стены, 90=у левой)
    # Копия размеров из каталога (для быстрой валидации без JOIN)
    width_px: float
    depth_px: float


class RoomLayout(BaseModel):
    """Результат расстановки для одной комнаты."""
    room_id: str
    room_label: str
    placed_items: list[PlacedFurniture] = Field(default_factory=list)
    unplaced_items: list[str] = Field(default_factory=list)  # item_id, не вошли
    warnings: list[str] = Field(default_factory=list)


class FurniturePlacement(BaseModel):
    """Полный план расстановки мебели для квартиры."""
    geometry_source: str = ""   # id/hash геометрии (для отслеживания версий)
    style: str
    budget: str
    rooms: list[RoomLayout] = Field(default_factory=list)
    validated: bool = False
    validation_errors: list[str] = Field(default_factory=list)
    total_price_rub: int = 0


# ─── Запросы/ответы API ───────────────────────────────────────────────────────


class AnalyzePlanRequest(BaseModel):
    image_url: str | None = None    # URL в fal.ai или S3
    # ИЛИ image_base64: str         # отправляется как multipart


class AnalyzePlanResponse(BaseModel):
    geometry: dict                  # ApartmentGeometry.model_dump()
    needs_validation: bool
    message: str = ""


class PlaceFurnitureRequest(BaseModel):
    geometry: dict                  # ApartmentGeometry (user-validated)
    style: str = "scandi"
    budget: str = "middle"
    priorities: list[str] = Field(default_factory=list)


class PlaceFurnitureResponse(BaseModel):
    placement: dict                 # FurniturePlacement.model_dump()
    debug_image_b64: str | None = None


class ValidateLayoutRequest(BaseModel):
    geometry: dict
    placement: dict


class ValidateLayoutResponse(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
