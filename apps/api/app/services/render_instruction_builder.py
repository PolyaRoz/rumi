"""
Построитель инструкций для рендера (Render Instruction Builder).

КРИТИЧЕСКИЕ ПРИНЦИПЫ:
1. Render-style ФИКСИРОВАН и НЕ зависит от user-style.
2. User-style влияет ТОЛЬКО на материалы, палитру, выбор мебели.
3. Геометрия передаётся как явный список ОГРАНИЧЕНИЙ — AI не имеет права её менять.
4. Имена и размеры мебели берутся ТОЛЬКО из validated catalog items.
5. Промпт детерминирован: одинаковый JSON → одинаковый промпт → стабильное изображение.

Этот модуль заменяет старый promptBuilder.ts, в котором render-style варьировался
между запусками и AI имел свободу интерпретировать геометрию.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.schemas.furniture import (
    FurnitureCatalogItem,
    FurniturePlacement,
    PlacedFurniture,
    RoomLayout,
)
from app.schemas.geometry import ApartmentGeometry, Room, RoomLabel


# ─── ФИКСИРОВАННЫЕ render-шаблоны ─────────────────────────────────────────────
# Эти строки НЕ зависят от user-style и НЕ меняются между запусками.

RENDER_STYLE_TOP_DOWN_3D = (
    "Top-down 3D isometric architectural visualization of an apartment, "
    "axonometric perspective at 30-degree elevation angle, "
    "clean white architectural background, "
    "matte structural walls with realistic thickness in dark grey, "
    "consistent soft natural daylight from above, "
    "neutral color grading, "
    "professional architectural presentation, "
    "Architectural Digest magazine quality, "
    "no text, no labels, no measurement numbers, no room names visible, "
    "no people, no fictitious decorative elements"
)

RENDER_STYLE_PER_ROOM_PHOTO = (
    "Ultra-realistic interior photograph, "
    "35mm lens, eye-level view, "
    "natural soft daylight from window, "
    "professional architectural photography, "
    "Architectural Digest magazine style, "
    "consistent neutral color grading, "
    "no people, no text, no labels, no measurement numbers, "
    "sharp focus, photorealistic, 4K resolution"
)

# ─── User-style → материалы и палитра ─────────────────────────────────────────
# Эти переменные влияют ТОЛЬКО на материалы и цвета, НЕ на render-format.

UserStyle = Literal["scandi", "minimal", "loft", "classic"]

STYLE_MATERIALS: dict[UserStyle, str] = {
    "scandi": (
        "Scandinavian palette: light oak hardwood floors, white painted walls, "
        "natural linen and wool textiles, warm beige and dusty rose accents, "
        "muted sage green plants, brushed brass fixtures"
    ),
    "minimal": (
        "Minimalist palette: polished concrete floors, white walls, "
        "monochrome black-grey-white furniture, matte black metal accents, "
        "no patterns, no clutter"
    ),
    "loft": (
        "Industrial loft palette: dark walnut hardwood floors, exposed grey brick walls, "
        "raw black metal pipes, cognac leather upholstery, charcoal and rust accents, "
        "Edison bulb warm lighting"
    ),
    "classic": (
        "Classic palette: herringbone parquet oak floors, cream and warm gold walls, "
        "crown moldings, velvet upholstery in muted jewel tones, brass and marble accents, "
        "refined traditional decor"
    ),
}


# ─── Маппинги для типов комнат на английский ──────────────────────────────────

ROOM_LABEL_EN: dict[RoomLabel, str] = {
    RoomLabel.living_room: "living room",
    RoomLabel.bedroom:     "bedroom",
    RoomLabel.kitchen:     "kitchen",
    RoomLabel.bathroom:    "bathroom",
    RoomLabel.toilet:      "toilet",
    RoomLabel.corridor:    "hallway corridor",
    RoomLabel.kids_room:   "children's bedroom",
    RoomLabel.balcony:     "balcony",
    RoomLabel.storage:     "storage room",
    RoomLabel.unknown:     "room",
}


# ─── Структуры результата ─────────────────────────────────────────────────────


@dataclass
class RenderInstruction:
    """Финальная инструкция для генеративной модели."""
    prompt: str                       # текстовый промпт
    negative_prompt: str              # что нельзя
    seed: int                          # для воспроизводимости
    strength: float | None = None      # для img2img (0.0-1.0); None = text2img
    reference_image_url: str | None = None
    render_style_id: str = ""          # идентификатор фиксированного шаблона
    locked_constraints: list[str] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.locked_constraints is None:
            self.locked_constraints = []


# ─── Фиксированный negative prompt ────────────────────────────────────────────
# Эти запреты идут с КАЖДЫМ запросом, всегда одни и те же.

FIXED_NEGATIVE = (
    # Запрет AI на изменение геометрии
    "additional walls, missing walls, moved walls, repositioned doors, "
    "extra doors, missing doors, additional windows, missing windows, "
    "moved windows, changed room shape, distorted proportions, "
    # Запрет на текст и метки
    "text, letters, numbers, room labels, dimension labels, "
    "measurement annotations, watermarks, signatures, "
    # Запрет на общие визуальные дефекты
    "people, persons, humans, fictitious furniture, "
    "blurry, low quality, distorted, sketch, line art, drawing, "
    "cartoon, illustration, watercolor, painting, "
    # Запрет на смену стиля рендера
    "fisheye, wide angle distortion, perspective change"
)


# ─── Детерминированный seed ───────────────────────────────────────────────────


def deterministic_seed(geometry_id: str, layout_id: str = "", style: str = "") -> int:
    """
    Генерируем стабильный seed из ID геометрии и layout.
    Один и тот же план → один и тот же seed → одинаковая визуализация.
    """
    import hashlib
    key = f"{geometry_id}|{layout_id}|{style}".encode()
    return int(hashlib.sha256(key).hexdigest()[:8], 16)


# ─── Билдеры промптов ─────────────────────────────────────────────────────────


def build_top_down_3d_instruction(
    geometry: ApartmentGeometry,
    placement: FurniturePlacement,
    catalog: list[FurnitureCatalogItem],
    user_style: UserStyle,
    reference_image_url: str | None = None,
) -> RenderInstruction:
    """
    Построить инструкцию для top-down 3D рендера всей квартиры.

    Использует ФИКСИРОВАННЫЙ render-style template + переменную часть с
    locked-геометрией и validated мебелью.

    Если передан reference_image_url (canvas-rendered план из geometry JSON) —
    используется как img2img reference со strength=0.20-0.30 (только стилизация,
    не изменение геометрии).
    """
    catalog_index = {item.id: item for item in catalog}

    # ── Описание геометрии (locked) ──────────────────────────────────────────
    room_count = len(geometry.rooms)
    rooms_desc = []
    for room in geometry.rooms:
        if room.area_m2:
            rooms_desc.append(
                f"{ROOM_LABEL_EN.get(room.label, 'room')} ({room.area_m2:.1f} sq.m)"
            )
        else:
            rooms_desc.append(ROOM_LABEL_EN.get(room.label, "room"))

    geometry_summary = (
        f"Apartment with {room_count} rooms: " + ", ".join(rooms_desc) + ". "
        f"The exact wall layout, room shapes, door positions, and window positions "
        f"are PRE-DEFINED and must be preserved EXACTLY as in the reference. "
    )

    # ── Описание мебели (только из каталога) ─────────────────────────────────
    furniture_desc = _describe_placed_furniture(placement, catalog_index)

    # ── Сборка промпта ────────────────────────────────────────────────────────
    style_palette = STYLE_MATERIALS.get(user_style, STYLE_MATERIALS["scandi"])

    prompt_parts = [
        # 1. ФИКСИРОВАННЫЙ render-style (всегда первый!)
        RENDER_STYLE_TOP_DOWN_3D,
        ".",
        # 2. Locked-геометрия (явное указание AI не менять)
        geometry_summary,
        # 3. Validated мебель из каталога
        furniture_desc,
        # 4. Палитра в зависимости от user-style
        style_palette,
        ".",
        # 5. Финальные ограничения (повтор для надёжности)
        "Walls, doors, windows, and room boundaries are LOCKED and must not be changed. "
        "Only the materials, colors, and furniture finish vary by style.",
    ]
    prompt = " ".join(p for p in prompt_parts if p).strip()

    # ── Locked constraints (для логирования и debug) ─────────────────────────
    locked_constraints = [
        f"walls={len(geometry.walls)} (locked)",
        f"rooms={len(geometry.rooms)} (locked)",
        f"doors={len(geometry.doors())} (locked)",
        f"windows={len(geometry.windows())} (locked)",
        f"furniture={sum(len(rl.placed_items) for rl in placement.rooms)} (catalog-only)",
    ]

    geo_id = f"w{len(geometry.walls)}_r{len(geometry.rooms)}_d{len(geometry.doors())}"
    layout_id = f"items{sum(len(rl.placed_items) for rl in placement.rooms)}"
    seed = deterministic_seed(geo_id, layout_id, user_style)

    return RenderInstruction(
        prompt=prompt,
        negative_prompt=FIXED_NEGATIVE,
        seed=seed,
        strength=0.25 if reference_image_url else None,  # очень низкий — только стилизация
        reference_image_url=reference_image_url,
        render_style_id="top_down_3d_v1",
        locked_constraints=locked_constraints,
    )


def build_per_room_photo_instruction(
    room: Room,
    room_layout: RoomLayout,
    catalog: list[FurnitureCatalogItem],
    user_style: UserStyle,
) -> RenderInstruction:
    """
    Построить инструкцию для фото отдельной комнаты.
    Render-style ФИКСИРОВАН. User-style влияет только на палитру.
    """
    catalog_index = {item.id: item for item in catalog}

    # Описание комнаты
    room_type_en = ROOM_LABEL_EN.get(room.label, "room")
    area_str = f", {room.area_m2:.1f} sq.m" if room.area_m2 else ""

    # Validated мебель в этой комнате
    furniture_items = [
        catalog_index.get(pi.item_id) for pi in room_layout.placed_items
    ]
    furniture_items = [i for i in furniture_items if i is not None]

    if furniture_items:
        furniture_names = ", ".join(
            f"{item.name} ({item.dimensions.width_m}×{item.dimensions.depth_m}m)"
            for item in furniture_items[:6]   # не больше 6 предметов в промпте
        )
        furniture_desc = (
            f"The room contains EXACTLY these real furniture items: {furniture_names}. "
            f"Use the exact proportions and dimensions specified."
        )
    else:
        furniture_desc = "The room is sparsely furnished."

    style_palette = STYLE_MATERIALS.get(user_style, STYLE_MATERIALS["scandi"])

    prompt_parts = [
        RENDER_STYLE_PER_ROOM_PHOTO,
        f". A {room_type_en}{area_str}.",
        furniture_desc,
        style_palette,
        ".",
        "Furniture proportions must match real product dimensions. "
        "Do not invent additional furniture. Do not add fictional decor.",
    ]
    prompt = " ".join(p for p in prompt_parts if p).strip()

    # Детерминированный seed: одна и та же комната + те же предметы → тот же seed
    item_ids = sorted(pi.item_id for pi in room_layout.placed_items)
    seed = deterministic_seed(room.id, "_".join(item_ids), user_style)

    locked_constraints = [
        f"room_type={room.label.value}",
        f"area={room.area_m2 or 'unknown'}",
        f"items={len(furniture_items)} from catalog",
    ]

    return RenderInstruction(
        prompt=prompt,
        negative_prompt=FIXED_NEGATIVE,
        seed=seed,
        strength=None,  # text2img для отдельной комнаты
        render_style_id="per_room_photo_v1",
        locked_constraints=locked_constraints,
    )


def _describe_placed_furniture(
    placement: FurniturePlacement,
    catalog_index: dict[str, FurnitureCatalogItem],
) -> str:
    """Описание расставленной мебели для промпта."""
    if not placement.rooms:
        return "The apartment is unfurnished."

    parts = []
    for rl in placement.rooms:
        if not rl.placed_items:
            continue
        room_items = []
        for pi in rl.placed_items:
            item = catalog_index.get(pi.item_id)
            if item is None:
                continue
            short_name = item.name.split(" ", 2)
            short_name = " ".join(short_name[:2]) if len(short_name) >= 2 else item.name
            room_items.append(short_name)
        if room_items:
            parts.append(f"{rl.room_label}: {', '.join(room_items[:4])}")

    if not parts:
        return "The apartment is unfurnished."
    return "Furniture (real products from catalog): " + "; ".join(parts) + "."
