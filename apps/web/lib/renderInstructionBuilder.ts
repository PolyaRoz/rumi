/**
 * Render Instruction Builder (frontend mirror of Python service).
 *
 * Зеркало apps/api/app/services/render_instruction_builder.py.
 *
 * КРИТИЧЕСКИЕ ПРИНЦИПЫ:
 * 1. Render-style ФИКСИРОВАН (правило F).
 * 2. User-style влияет ТОЛЬКО на палитру материалов (правило G).
 * 3. Промпт содержит явные locked-ограничения для AI (правила A, C, D, E).
 * 4. Negative prompt запрещает изменение геометрии и добавление выдуманных элементов.
 * 5. Seed детерминирован: один и тот же layout → один и тот же seed.
 */

export type StyleKey = 'scandi' | 'minimal' | 'loft' | 'classic'

export interface PerRoomLockedContext {
  room_label: string         // 'living_room' | 'bedroom' | ...
  area_m2: number | null
  placed_count: number
}

export interface FurnitureNameDim {
  name: string               // как в каталоге Hoff
  category: string
  width_m?: number
  depth_m?: number
}

// ─── ФИКСИРОВАННЫЕ render-шаблоны ─────────────────────────────────────────────

const RENDER_STYLE_PER_ROOM_PHOTO = (
  'Ultra-realistic interior photograph, ' +
  '35mm lens, eye-level view, ' +
  'natural soft daylight from window, ' +
  'professional architectural photography, ' +
  'Architectural Digest magazine style, ' +
  'consistent neutral color grading, ' +
  'no people, no text, no labels, no measurement numbers, ' +
  'sharp focus, photorealistic, 4K resolution'
)

// ─── Палитры материалов ──────────────────────────────────────────────────────

const STYLE_MATERIALS: Record<StyleKey, string> = {
  scandi: (
    'Scandinavian palette: light oak hardwood floors, white painted walls, ' +
    'natural linen and wool textiles, warm beige and dusty rose accents, ' +
    'muted sage green plants, brushed brass fixtures'
  ),
  minimal: (
    'Minimalist palette: polished concrete floors, white walls, ' +
    'monochrome black-grey-white furniture, matte black metal accents, ' +
    'no patterns, no clutter'
  ),
  loft: (
    'Industrial loft palette: dark walnut hardwood floors, exposed grey brick walls, ' +
    'raw black metal pipes, cognac leather upholstery, charcoal and rust accents, ' +
    'Edison bulb warm lighting'
  ),
  classic: (
    'Classic palette: herringbone parquet oak floors, cream and warm gold walls, ' +
    'crown moldings, velvet upholstery in muted jewel tones, brass and marble accents'
  ),
}

const ROOM_LABEL_EN: Record<string, string> = {
  living_room: 'living room',
  bedroom:     'bedroom',
  kitchen:     'kitchen',
  bathroom:    'bathroom',
  toilet:      'toilet',
  corridor:    'hallway corridor',
  kids_room:   "children's bedroom",
  balcony:     'balcony',
  storage:     'storage room',
  unknown:     'room',
}

// ─── ФИКСИРОВАННЫЙ negative prompt ────────────────────────────────────────────

export const FIXED_NEGATIVE = (
  // Запрет AI на изменение геометрии
  'additional walls, missing walls, moved walls, repositioned doors, ' +
  'extra doors, missing doors, additional windows, missing windows, ' +
  'moved windows, changed room shape, distorted proportions, ' +
  // Запрет на текст и метки
  'text, letters, numbers, room labels, dimension labels, ' +
  'measurement annotations, watermarks, signatures, ' +
  // Запрет на общие визуальные дефекты
  'people, persons, humans, fictitious furniture, ' +
  'blurry, low quality, distorted, sketch, line art, drawing, ' +
  'cartoon, illustration, watercolor, painting, ' +
  // Запрет на смену стиля рендера
  'fisheye, wide angle distortion, perspective change'
)

// ─── Детерминированный seed (FNV-1a hash) ─────────────────────────────────────

function deterministicSeed(...keys: string[]): number {
  let hash = 2166136261  // FNV offset basis
  const text = keys.join('|')
  for (let i = 0; i < text.length; i++) {
    hash ^= text.charCodeAt(i)
    hash = Math.imul(hash, 16777619)  // FNV prime
  }
  return Math.abs(hash)
}

// ─── Public API ──────────────────────────────────────────────────────────────

export interface RenderInstruction {
  prompt: string
  negative_prompt: string
  seed: number
  render_style_id: string
  locked_constraints: string[]
}

export function buildPerRoomPhotoInstruction(
  context: PerRoomLockedContext,
  furniture: FurnitureNameDim[],
  userStyle: StyleKey,
): RenderInstruction {
  const roomTypeEn = ROOM_LABEL_EN[context.room_label] ?? 'room'
  const areaStr = context.area_m2 ? `, ${context.area_m2.toFixed(1)} sq.m` : ''

  let furnitureDesc: string
  if (furniture.length > 0) {
    // До 6 предметов в промпте, имена и размеры
    const names = furniture.slice(0, 6).map(f => {
      if (f.width_m && f.depth_m) {
        return `${f.name} (${f.width_m}×${f.depth_m}m)`
      }
      return f.name
    }).join(', ')
    furnitureDesc = (
      `The room contains EXACTLY these real furniture items: ${names}. ` +
      `Use the exact proportions and dimensions specified.`
    )
  } else {
    furnitureDesc = 'The room is sparsely furnished.'
  }

  const stylePalette = STYLE_MATERIALS[userStyle] ?? STYLE_MATERIALS.scandi

  const prompt = [
    RENDER_STYLE_PER_ROOM_PHOTO,
    `. A ${roomTypeEn}${areaStr}.`,
    furnitureDesc,
    stylePalette,
    '.',
    'Furniture proportions must match real product dimensions. ' +
    'Do not invent additional furniture. Do not add fictional decor.',
  ].join(' ').trim()

  // Стабильный seed: одна и та же комната + те же предметы → тот же seed
  const itemKey = furniture.map(f => f.name).sort().join(',')
  const seed = deterministicSeed(context.room_label, itemKey, userStyle)

  return {
    prompt,
    negative_prompt: FIXED_NEGATIVE,
    seed,
    render_style_id: 'per_room_photo_v1',
    locked_constraints: [
      `room_type=${context.room_label}`,
      `area=${context.area_m2 ?? 'unknown'}`,
      `items=${furniture.length} from catalog`,
    ],
  }
}
