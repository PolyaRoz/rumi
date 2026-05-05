"""
Сервис каталога мебели.

Загружает JSON-файлы из apps/web/data/ и строит FurnitureCatalogItem объекты
с правилами размещения, размерами и стилевыми тегами.

Дополняет исходные данные Hoff:
- Нормализует размеры в метры (Hoff хранит в сантиметрах)
- Добавляет PlacementRules на основе категории
- Добавляет room_types на основе категории
- Добавляет style_tags на основе названия/описания
"""

from __future__ import annotations

import json
import logging
import pathlib
from functools import lru_cache

from app.schemas.furniture import (
    CategoryKey,
    FurnitureCatalogItem,
    FurnitureDimensions,
    PlacementRules,
    RoomTypeKey,
    StyleTag,
)

logger = logging.getLogger(__name__)

# Путь к JSON-файлам каталога
# __file__ = apps/api/app/services/furniture_catalog.py
# .parent×4   = apps/
# / "web/data" = apps/web/data/
_CATALOG_DIR = (
    pathlib.Path(__file__).parent.parent.parent.parent
    / "web" / "data"
)

# ─── Маппинги ─────────────────────────────────────────────────────────────────

_HOFF_CATEGORY_TO_SCHEMA: dict[str, CategoryKey] = {
    "divany":  "sofa",
    "kresla":  "armchair",
    "shkafy":  "wardrobe",
    "komody":  "dresser",
    "tumby":   "nightstand",
    "pufy":    "ottoman",
    "kovry":   "rug",
}

_CATEGORY_ROOM_TYPES: dict[CategoryKey, list[RoomTypeKey]] = {
    "sofa":       ["living_room"],
    "armchair":   ["living_room", "bedroom", "kids_room"],
    "wardrobe":   ["bedroom", "corridor", "kids_room"],
    "dresser":    ["bedroom", "living_room", "kids_room"],
    "nightstand": ["bedroom", "kids_room"],
    "ottoman":    ["living_room", "bedroom", "corridor", "kids_room"],
    "rug":        ["living_room", "bedroom", "kids_room", "corridor"],
    "bed":        ["bedroom", "kids_room"],
    "table":      ["living_room", "kitchen"],
    "chair":      ["kitchen", "living_room"],
    "tv_unit":    ["living_room"],
    "bookshelf":  ["living_room", "bedroom", "kids_room"],
    "desk":       ["bedroom", "kids_room"],
    "kitchen_set":["kitchen"],
    "bathroom_fixture": ["bathroom"],
    "toilet":     ["toilet", "bathroom"],
    "bathtub":    ["bathroom"],
    "shower":     ["bathroom"],
}

_CATEGORY_PLACEMENT_RULES: dict[CategoryKey, PlacementRules] = {
    "sofa": PlacementRules(
        against_wall=True,
        min_clearance_front_m=1.0,
        min_clearance_sides_m=0.3,
        avoid_blocking_windows=False,
        avoid_blocking_doors=True,
    ),
    "armchair": PlacementRules(
        against_wall=False,
        min_clearance_front_m=0.5,
        min_clearance_sides_m=0.2,
        anchor_to="free_standing",
    ),
    "wardrobe": PlacementRules(
        against_wall=True,
        min_clearance_front_m=0.6,
        min_clearance_sides_m=0.05,
        avoid_blocking_windows=True,
    ),
    "dresser": PlacementRules(
        against_wall=True,
        min_clearance_front_m=0.6,
        min_clearance_sides_m=0.1,
    ),
    "nightstand": PlacementRules(
        against_wall=True,
        min_clearance_front_m=0.3,
        min_clearance_sides_m=0.05,
        min_clearance_back_m=0.02,
    ),
    "ottoman": PlacementRules(
        against_wall=False,
        min_clearance_front_m=0.3,
        min_clearance_sides_m=0.2,
        anchor_to="free_standing",
    ),
    "rug": PlacementRules(
        against_wall=False,
        min_clearance_front_m=0.0,
        min_clearance_sides_m=0.0,
        anchor_to="free_standing",
    ),
    "bed": PlacementRules(
        against_wall=True,
        min_clearance_front_m=0.6,
        min_clearance_sides_m=0.4,
        anchor_to="any_wall",
    ),
    "tv_unit": PlacementRules(
        against_wall=True,
        min_clearance_front_m=0.5,
        avoid_blocking_windows=True,
    ),
    "bookshelf": PlacementRules(
        against_wall=True,
        min_clearance_front_m=0.6,
        avoid_blocking_windows=True,
    ),
    "desk": PlacementRules(
        against_wall=True,
        min_clearance_front_m=0.7,
        min_clearance_sides_m=0.3,
    ),
    "kitchen_set": PlacementRules(
        against_wall=True,
        min_clearance_front_m=0.9,
        anchor_to="fixed",
    ),
    "table": PlacementRules(
        against_wall=False,
        min_clearance_front_m=0.8,
        min_clearance_sides_m=0.5,
        anchor_to="free_standing",
    ),
    "chair": PlacementRules(
        against_wall=False,
        min_clearance_front_m=0.3,
        anchor_to="free_standing",
    ),
    "bathroom_fixture": PlacementRules(against_wall=True, anchor_to="fixed", wet_zone_only=True),
    "toilet":           PlacementRules(against_wall=True, anchor_to="fixed", wet_zone_only=True),
    "bathtub":          PlacementRules(against_wall=True, anchor_to="fixed", wet_zone_only=True),
    "shower":           PlacementRules(against_wall=True, anchor_to="fixed", wet_zone_only=True),
}

# Дефолтные размеры по категориям (если в JSON нет dimensions)
_DEFAULT_DIMENSIONS: dict[CategoryKey, FurnitureDimensions] = {
    "sofa":       FurnitureDimensions(width_m=2.2, depth_m=0.95, height_m=0.85),
    "armchair":   FurnitureDimensions(width_m=0.85, depth_m=0.85, height_m=0.90),
    "wardrobe":   FurnitureDimensions(width_m=1.8, depth_m=0.6, height_m=2.1),
    "dresser":    FurnitureDimensions(width_m=1.0, depth_m=0.45, height_m=1.0),
    "nightstand": FurnitureDimensions(width_m=0.5, depth_m=0.4, height_m=0.55),
    "ottoman":    FurnitureDimensions(width_m=0.6, depth_m=0.6, height_m=0.45),
    "rug":        FurnitureDimensions(width_m=2.0, depth_m=3.0, height_m=0.02),
    "bed":        FurnitureDimensions(width_m=1.6, depth_m=2.0, height_m=0.5),
    "tv_unit":    FurnitureDimensions(width_m=1.5, depth_m=0.4, height_m=0.5),
    "bookshelf":  FurnitureDimensions(width_m=0.8, depth_m=0.3, height_m=1.8),
    "desk":       FurnitureDimensions(width_m=1.2, depth_m=0.6, height_m=0.75),
    "kitchen_set":FurnitureDimensions(width_m=3.0, depth_m=0.6, height_m=0.85),
    "table":      FurnitureDimensions(width_m=1.2, depth_m=0.8, height_m=0.75),
    "chair":      FurnitureDimensions(width_m=0.5, depth_m=0.5, height_m=0.9),
    "bathroom_fixture": FurnitureDimensions(width_m=0.6, depth_m=0.45, height_m=0.85),
    "toilet":     FurnitureDimensions(width_m=0.4, depth_m=0.65, height_m=0.8),
    "bathtub":    FurnitureDimensions(width_m=0.75, depth_m=1.7, height_m=0.55),
    "shower":     FurnitureDimensions(width_m=0.9, depth_m=0.9, height_m=2.1),
}

# Стилевые теги по ключевым словам в названии
_STYLE_KEYWORDS: dict[str, StyleTag] = {
    "скандинавский": "scandi",
    "скандинав": "scandi",
    "scandica": "scandi",
    "лофт": "loft",
    "loft": "loft",
    "industrial": "loft",
    "минимализм": "minimal",
    "minimal": "minimal",
    "классика": "classic",
    "classic": "classic",
    "прованс": "classic",
}


def _infer_style_tags(name: str) -> list[StyleTag]:
    name_lower = name.lower()
    tags: list[StyleTag] = []
    for keyword, tag in _STYLE_KEYWORDS.items():
        if keyword in name_lower and tag not in tags:
            tags.append(tag)
    if not tags:
        tags = ["any"]
    return tags


def _parse_dimensions(raw: dict | None, category: CategoryKey) -> FurnitureDimensions:
    """Конвертировать размеры из JSON (сантиметры) в метры."""
    if raw is None:
        return _DEFAULT_DIMENSIONS.get(category, FurnitureDimensions(width_m=1.0, depth_m=1.0, height_m=1.0))

    def to_m(val: float | int | None, default_m: float) -> float:
        if val is None:
            return default_m
        v = float(val)
        # Hoff хранит в сантиметрах (значения > 10 — это см, иначе уже метры)
        return round(v / 100 if v > 10 else v, 3)

    default = _DEFAULT_DIMENSIONS.get(category, FurnitureDimensions(width_m=1.0, depth_m=1.0, height_m=1.0))
    return FurnitureDimensions(
        width_m=to_m(raw.get("width_cm"), default.width_m),
        depth_m=to_m(raw.get("depth_cm"), default.depth_m),
        height_m=to_m(raw.get("height_cm"), default.height_m),
    )


def _load_category(json_path: pathlib.Path, hoff_key: str) -> list[FurnitureCatalogItem]:
    """Загрузить один JSON-файл каталога → список FurnitureCatalogItem."""
    if not json_path.exists():
        logger.warning(f"Файл каталога не найден: {json_path}")
        return []

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    products = data.get("products", [])
    schema_category: CategoryKey = _HOFF_CATEGORY_TO_SCHEMA.get(hoff_key, "armchair")
    items: list[FurnitureCatalogItem] = []

    for p in products:
        try:
            dims = _parse_dimensions(p.get("dimensions"), schema_category)
            item = FurnitureCatalogItem(
                id=str(p["id"]),
                name=p["name"],
                category=schema_category,
                store="Hoff",
                price_rub=int(p.get("price_rub", 0)),
                old_price_rub=p.get("old_price_rub"),
                discount_percent=p.get("discount_percent"),
                url=p.get("url", ""),
                image_url=p.get("image", ""),
                dimensions=dims,
                style_tags=_infer_style_tags(p["name"]),
                room_types=_CATEGORY_ROOM_TYPES.get(schema_category, []),
                placement_rules=_CATEGORY_PLACEMENT_RULES.get(
                    schema_category, PlacementRules()
                ),
            )
            items.append(item)
        except Exception as e:
            logger.debug(f"Пропускаем товар {p.get('id')}: {e}")

    return items


@lru_cache(maxsize=1)
def load_catalog() -> list[FurnitureCatalogItem]:
    """
    Загрузить весь каталог (кешируется в памяти).
    """
    all_items: list[FurnitureCatalogItem] = []
    for hoff_key in _HOFF_CATEGORY_TO_SCHEMA:
        json_path = _CATALOG_DIR / f"{hoff_key}.json"
        items = _load_category(json_path, hoff_key)
        all_items.extend(items)
        logger.info(f"Загружено {len(items)} товаров из {hoff_key}.json")

    logger.info(f"Каталог: {len(all_items)} товаров всего")
    return all_items


def filter_catalog(
    catalog: list[FurnitureCatalogItem],
    room_type: RoomTypeKey,
    budget: str,           # "economy" | "middle" | "premium"
    style: str,            # "scandi" | "minimal" | "loft" | "classic"
    categories: list[CategoryKey] | None = None,
) -> list[FurnitureCatalogItem]:
    """
    Отфильтровать каталог по комнате, бюджету и стилю.

    Бюджетные диапазоны:
    - economy: до 30 000 ₽
    - middle:  до 100 000 ₽
    - premium: без ограничения
    """
    budget_limits = {
        "economy": 30_000,
        "middle": 100_000,
        "premium": 10_000_000,
    }
    max_price = budget_limits.get(budget, 100_000)

    result = []
    for item in catalog:
        # Фильтр по комнате
        if room_type not in item.room_types:
            continue
        # Фильтр по бюджету
        if item.price_rub > max_price:
            continue
        # Фильтр по категориям (если задан)
        if categories and item.category not in categories:
            continue
        result.append(item)

    # Ранжирование: стилевые совпадения — выше
    def score(item: FurnitureCatalogItem) -> int:
        style_match = style in item.style_tags or "any" in item.style_tags
        has_discount = bool(item.discount_percent and item.discount_percent > 0)
        return int(style_match) * 10 + int(has_discount) * 3

    result.sort(key=score, reverse=True)
    return result


def get_item_by_id(catalog: list[FurnitureCatalogItem], item_id: str) -> FurnitureCatalogItem | None:
    return next((i for i in catalog if i.id == item_id), None)
