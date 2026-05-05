// Строим детальные промпты для генерации реалистичных интерьеров
// с реальными предметами из каталога Hoff

export type RoomType = 'living' | 'bedroom' | 'kitchen' | 'kids' | 'hallway'
export type StyleType = 'scandi' | 'minimal' | 'loft' | 'classic'

interface FurnitureItem {
  name: string
  category: string
}

const STYLE_DESCRIPTIONS: Record<StyleType, string> = {
  scandi: 'Scandinavian interior design, light oak wood, white walls, natural linen textiles, hygge atmosphere, minimalist Nordic style',
  minimal: 'minimalist interior, clean lines, monochrome palette, open space, concrete and white surfaces, understated luxury',
  loft: 'industrial loft interior, exposed brick walls, metal accents, dark wood, Edison bulbs, urban industrial style',
  classic: 'classic elegant interior, warm cream tones, moldings, parquet herringbone floor, refined traditional decor',
}

const ROOM_DESCRIPTIONS: Record<RoomType, string> = {
  living: 'spacious living room with large windows',
  bedroom: 'serene master bedroom with soft lighting',
  kitchen: 'open-plan kitchen and dining area',
  kids: 'bright children\'s bedroom with playful details',
  hallway: 'elegant entrance hallway',
}

const ROOM_DETAILS: Record<RoomType, string> = {
  living: 'large floor-to-ceiling windows, hardwood parquet floor, decorative plants, coffee table with books, ambient floor lamp',
  bedroom: 'bedside lamps, soft curtains, decorative pillows, closet with mirror, calm atmosphere',
  kitchen: 'kitchen island, pendant lights above dining table, subway tile backsplash, open shelving',
  kids: 'colorful rug, bookshelf with toys, soft natural light, cozy reading nook',
  hallway: 'coat rack, mirror, shoe cabinet, warm lighting',
}

// Переводим русские названия мебели Hoff в английские описания для промпта
function translateFurnitureName(name: string, category: string): string {
  const n = name.toLowerCase()

  // Диваны
  if (n.includes('угловой диван') || n.includes('угловой дivan')) {
    if (n.includes('слим')) return 'Slim L-shaped corner sofa in grey fabric'
    if (n.includes('мэдисон') || n.includes('madison')) return 'Madison corner sectional sofa in beige velvet'
    if (n.includes('сиэтл') || n.includes('seattle')) return 'Seattle corner sofa in light brown fabric'
    if (n.includes('атланта')) return 'Atlanta corner sofa in charcoal grey'
    if (n.includes('тулуза')) return 'Toulouse L-shaped sofa in cream boucle'
    return 'large L-shaped corner sofa in neutral fabric'
  }
  if (n.includes('диван')) {
    if (n.includes('пекин')) return 'Pekin fabric sofa-bed in grey'
    if (n.includes('парма')) return 'Parma compact sofa in beige'
    if (n.includes('дрезден')) return 'Dresden velvet sofa in dusty rose'
    if (n.includes('аккорд')) return 'Accord sofa in dark blue velvet'
    if (n.includes('аризона')) return 'Arizona sofa in light olive green'
    if (n.includes('сеул') || n.includes('seoul')) return 'Seoul modern sofa in warm grey'
    if (n.includes('питсбург')) return 'Pittsburgh sofa in cognac leather'
    if (n.includes('атланта')) return 'Atlanta straight sofa in taupe'
    if (n.includes('норман')) return 'Norman compact sofa in sky blue'
    return 'modern fabric sofa in neutral tone'
  }

  // Кресла
  if (n.includes('кресло')) {
    if (n.includes('gap')) return 'Gap bean bag chair in mustard yellow'
    if (n.includes('скотт') || n.includes('scott')) return 'Scott accent armchair in light beige'
    if (n.includes('гауди')) return 'Gaudi curved armchair in terracotta fabric'
    if (n.includes('агата')) return 'Agata cozy armchair in warm grey'
    if (n.includes('людвиг')) return 'Ludwig barrel armchair in olive green'
    if (n.includes('оксфорд')) return 'Oxford wing armchair in navy blue'
    if (n.includes('патрик')) return 'Patrick modern armchair in cream boucle'
    if (n.includes('аликанте')) return 'Alicante lounge chair in caramel leather'
    if (n.includes('норд')) return 'Nord rocking armchair in light wood and fabric'
    if (n.includes('хортен')) return 'Horten accent chair in dusty rose'
    if (n.includes('палермо')) return 'Palermo sleeper armchair in dark grey'
    if (n.includes('вегас')) return 'Vegas convertible armchair in charcoal'
    if (n.includes('канзас')) return 'Kansas armchair-bed in warm brown'
    if (n.includes('скаген')) return 'Skagen rocking chair in light oak'
    return 'modern accent armchair in neutral fabric'
  }

  // Ковры
  if (n.includes('ковёр') || n.includes('ковер')) {
    if (n.includes('гиссар')) return 'Gissar geometric patterned area rug in beige and cream'
    if (n.includes('шегги') || n.includes('shaggy')) return 'fluffy shaggy rug in warm ivory'
    if (n.includes('боттичелли')) return 'Botticelli classic ornamental rug in terracotta and cream'
    if (n.includes('florance') || n.includes('флоранс')) return 'Florence floral area rug in dusty blue and beige'
    if (n.includes('teira') || n.includes('тейра')) return 'Teira modern geometric rug in grey tones'
    return 'decorative area rug with geometric pattern'
  }

  // Шкафы
  if (n.includes('шкаф')) {
    if (n.includes('витрина')) return 'glass-door display cabinet with drawers in white'
    if (n.includes('купе')) return 'sliding wardrobe in matte white'
    return 'modern storage cabinet in light wood finish'
  }

  // Комоды
  if (n.includes('комод')) return 'wooden chest of drawers in white oak finish'

  // Тумбы
  if (n.includes('тумб')) {
    if (n.includes('прикроватн') || n.includes('тумба')) return 'bedside table in light wood'
    if (n.includes('тв') || n.includes('tv')) return 'low TV console in white and wood'
    return 'small side table in natural wood'
  }

  // Пуфы
  if (n.includes('пуф') || n.includes('банкетк')) return 'upholstered ottoman in velvet'

  return name
}

export interface VisualizationRequest {
  room: RoomType
  style: StyleType
  furniture: FurnitureItem[]
}

export function buildPrompt(req: VisualizationRequest): string {
  const { room, style, furniture } = req

  const styleDesc = STYLE_DESCRIPTIONS[style]
  const roomDesc = ROOM_DESCRIPTIONS[room]
  const roomDetails = ROOM_DETAILS[room]

  // Берём до 4 предметов мебели для промпта
  const furnitureDescs = furniture
    .slice(0, 4)
    .map(f => translateFurnitureName(f.name, f.category))
    .filter(Boolean)
    .join(', ')

  const furniturePart = furnitureDescs
    ? `The room is furnished with: ${furnitureDescs}.`
    : ''

  const prompt = [
    `Ultra-realistic interior design photography, ${roomDesc},`,
    `${styleDesc}.`,
    furniturePart,
    `${roomDetails}.`,
    'Professional architectural photography, 35mm lens, natural daylight, beautifully styled,',
    'no people, photorealistic render, 8K resolution, Architectural Digest magazine style,',
    'sharp focus, HDR, depth of field.',
  ].join(' ')

  return prompt
}

// Дефолтная мебель для каждой комнаты (из каталога Hoff)
export const DEFAULT_FURNITURE: Record<RoomType, FurnitureItem[]> = {
  living: [
    { name: 'Угловой диван-кровать SOLANA Мэдисон с правым углом', category: 'divany' },
    { name: 'Кресло SCANDICA Скотт', category: 'kresla' },
    { name: 'Ковёр Гиссар 200х300 см', category: 'kovry' },
    { name: 'Шкаф-витрина с 3 ящиками Эванс', category: 'shkafy' },
  ],
  bedroom: [
    { name: 'Тумба прикроватная с ящиком', category: 'tumby' },
    { name: 'Кресло для отдыха SCANDICA Норд', category: 'kresla' },
    { name: 'Ковёр Шегги 200х300 см', category: 'kovry' },
    { name: 'Комод с ящиками', category: 'komody' },
  ],
  kitchen: [
    { name: 'Кресло Гауди', category: 'kresla' },
    { name: 'Пуф банкетка', category: 'pufy' },
    { name: 'Ковёр Teira 160х230 см', category: 'kovry' },
    { name: 'Комод Эванс', category: 'komody' },
  ],
  kids: [
    { name: 'Кресло Gap', category: 'kresla' },
    { name: 'Ковёр Шегги', category: 'kovry' },
    { name: 'Пуф мягкий', category: 'pufy' },
    { name: 'Комод детский', category: 'komody' },
  ],
  hallway: [
    { name: 'Пуф банкетка', category: 'pufy' },
    { name: 'Шкаф для прихожей', category: 'shkafy' },
    { name: 'Комод с зеркалом', category: 'komody' },
  ],
}
