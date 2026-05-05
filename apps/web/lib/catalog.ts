import divanyRaw from '@/data/divany.json'
import kreslaRaw from '@/data/kresla.json'
import shkafyRaw from '@/data/shkafy.json'
import komodyRaw from '@/data/komody.json'
import tumbyRaw from '@/data/tumby.json'
import pufyRaw from '@/data/pufy.json'
import kovryRaw from '@/data/kovry.json'

// ─── Types ────────────────────────────────────────────────────────────────────

export interface HoffDimensions {
  width_cm?: number | null
  depth_cm?: number | null
  height_cm?: number | null
  source?: string | null
  note?: string | null
  [key: string]: unknown
}

export interface HoffProduct {
  id: string
  name: string
  image: string
  url: string
  price_rub: number
  old_price_rub: number | null
  discount_percent: number | null
  dimensions: HoffDimensions | null
  // добавляем для удобства
  category: CategoryKey
  categoryLabel: string
}

// Форматируем размеры в строку
export function formatDimensions(d: HoffDimensions | null): string | null {
  if (!d) return null
  const parts: string[] = []
  if (d.width_cm) parts.push(`Ш ${d.width_cm} см`)
  if (d.depth_cm) parts.push(`Г ${d.depth_cm} см`)
  if (d.height_cm) parts.push(`В ${d.height_cm} см`)
  return parts.length ? parts.join(' · ') : null
}

export type CategoryKey =
  | 'divany'
  | 'kresla'
  | 'shkafy'
  | 'komody'
  | 'tumby'
  | 'pufy'
  | 'kovry'

export interface Category {
  key: CategoryKey
  label: string
  icon: string
  products: HoffProduct[]
}

// ─── Raw → typed ─────────────────────────────────────────────────────────────

function hydrate(
  raw: { category: string; products: Omit<HoffProduct, 'category' | 'categoryLabel'>[] },
  key: CategoryKey
): HoffProduct[] {
  return raw.products
    .filter(p => p.price_rub > 0 && p.price_rub < 1_000_000) // убираем ошибки данных
    .map(p => ({ ...p, category: key, categoryLabel: raw.category }))
}

// ─── Catalog ─────────────────────────────────────────────────────────────────

export const CATEGORIES: Category[] = [
  {
    key: 'divany',
    label: 'Диваны',
    icon: '🛋',
    products: hydrate(divanyRaw as any, 'divany'),
  },
  {
    key: 'kresla',
    label: 'Кресла',
    icon: '🪑',
    products: hydrate(kreslaRaw as any, 'kresla'),
  },
  {
    key: 'shkafy',
    label: 'Шкафы',
    icon: '🗄',
    products: hydrate(shkafyRaw as any, 'shkafy'),
  },
  {
    key: 'komody',
    label: 'Комоды',
    icon: '🗃',
    products: hydrate(komodyRaw as any, 'komody'),
  },
  {
    key: 'tumby',
    label: 'Тумбы',
    icon: '🪟',
    products: hydrate(tumbyRaw as any, 'tumby'),
  },
  {
    key: 'pufy',
    label: 'Пуфы',
    icon: '🛏',
    products: hydrate(pufyRaw as any, 'pufy'),
  },
  {
    key: 'kovry',
    label: 'Ковры',
    icon: '🎨',
    products: hydrate(kovryRaw as any, 'kovry'),
  },
]

// Все товары в одном массиве
export const ALL_PRODUCTS: HoffProduct[] = CATEGORIES.flatMap(c => c.products)

// Итого товаров
export const TOTAL_COUNT = ALL_PRODUCTS.length

// Поиск по id
export function getProductById(id: string): HoffProduct | undefined {
  return ALL_PRODUCTS.find(p => p.id === id)
}

// Товары по категории
export function getByCategory(key: CategoryKey): HoffProduct[] {
  return CATEGORIES.find(c => c.key === key)?.products ?? []
}

// Форматирование цены
export function formatPrice(rub: number): string {
  return rub.toLocaleString('ru-RU') + ' ₽'
}
