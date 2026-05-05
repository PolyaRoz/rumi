'use client'

import { useState, useMemo } from 'react'
import Image from 'next/image'
import Link from 'next/link'
import { ShoppingBag, Download, ArrowLeft, ExternalLink, Check, RefreshCw, X, Tag } from 'lucide-react'
import StepHeader from '@/components/StepHeader'
import { CATEGORIES, ALL_PRODUCTS, formatPrice, formatDimensions, type HoffProduct, type CategoryKey } from '@/lib/catalog'

// ─── Cart state ───────────────────────────────────────────────────────────────

type CartMap = Record<string, boolean>

// ─── Product Card ─────────────────────────────────────────────────────────────

function ProductCard({
  product,
  inCart,
  onToggle,
}: {
  product: HoffProduct
  inCart: boolean
  onToggle: () => void
}) {
  const hasDiscount = product.discount_percent && product.old_price_rub

  return (
    <div className="card flex flex-col overflow-hidden hover:shadow-md transition-shadow group">
      {/* Image */}
      <div className="relative h-48 bg-cream overflow-hidden">
        <Image
          src={product.image}
          alt={product.name}
          fill
          className="object-cover group-hover:scale-105 transition-transform duration-300"
          sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
          unoptimized // hoff.ru возвращает правильные изображения напрямую
        />
        {hasDiscount && (
          <div className="absolute top-2 left-2 px-2 py-0.5 rounded-full bg-terracotta text-white font-body text-[11px] font-medium">
            −{product.discount_percent}%
          </div>
        )}
        <div className="absolute top-2 right-2 px-2 py-0.5 rounded-full bg-white/80 backdrop-blur-sm text-[11px] font-body font-medium text-ink">
          Hoff
        </div>
      </div>

      {/* Info */}
      <div className="p-4 flex flex-col gap-3 flex-1">
        <div className="flex-1">
          <p className="font-body text-[11px] text-muted uppercase tracking-wide mb-1">
            {product.categoryLabel}
          </p>
          <h3 className="font-body text-[14px] font-semibold text-ink leading-snug line-clamp-2">
            {product.name}
          </h3>
          {formatDimensions(product.dimensions) && (
            <p className="font-body text-[12px] text-muted mt-1">{formatDimensions(product.dimensions)}</p>
          )}
        </div>

        {/* Price + actions */}
        <div className="flex items-end justify-between gap-2 pt-2 border-t border-border">
          <div>
            <p className="font-heading text-[18px] font-semibold text-ink leading-none">
              {formatPrice(product.price_rub)}
            </p>
            {hasDiscount && (
              <p className="font-body text-[12px] text-muted line-through mt-0.5">
                {formatPrice(product.old_price_rub!)}
              </p>
            )}
          </div>
          <div className="flex items-center gap-1.5 flex-shrink-0">
            <a
              href={product.url}
              target="_blank"
              rel="noopener noreferrer"
              className="w-8 h-8 rounded-lg border border-border flex items-center justify-center hover:border-muted transition-colors"
              title="Открыть на Hoff"
            >
              <ExternalLink size={13} className="text-muted" />
            </a>
            <button
              onClick={onToggle}
              className={`w-8 h-8 rounded-lg flex items-center justify-center transition-all
                ${inCart
                  ? 'bg-terracotta text-white'
                  : 'border border-border text-muted hover:border-terracotta hover:text-terracotta'
                }`}
              title={inCart ? 'Убрать из сметы' : 'Добавить в смету'}
            >
              {inCart ? <Check size={13} /> : <ShoppingBag size={13} />}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── Main Page ────────────────────────────────────────────────────────────────

type FilterTab = 'all' | CategoryKey

export default function ResultsPage() {
  const [cart, setCart] = useState<CartMap>({})
  const [activeTab, setActiveTab] = useState<FilterTab>('all')
  const [search, setSearch] = useState('')

  const toggleCart = (id: string) =>
    setCart(prev => ({ ...prev, [id]: !prev[id] }))

  const removeFromCart = (id: string) =>
    setCart(prev => ({ ...prev, [id]: false }))

  // Фильтрация товаров
  const filtered = useMemo(() => {
    let items = activeTab === 'all' ? ALL_PRODUCTS : ALL_PRODUCTS.filter(p => p.category === activeTab)
    if (search.trim()) {
      const q = search.toLowerCase()
      items = items.filter(p => p.name.toLowerCase().includes(q))
    }
    return items
  }, [activeTab, search])

  // Товары в смете
  const cartItems = useMemo(
    () => ALL_PRODUCTS.filter(p => cart[p.id]),
    [cart]
  )

  const cartTotal = cartItems.reduce((s, p) => s + p.price_rub, 0)
  const cartCount = cartItems.length

  return (
    <div className="min-h-screen bg-paper flex flex-col">
      <StepHeader current={3} backHref="/visualization" backLabel="Назад к визуализации" />

      <div className="flex flex-col lg:flex-row flex-1 min-h-0">
        {/* ── Main content ── */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Title + search */}
          <div className="px-6 md:px-10 pt-8 pb-4 flex flex-col gap-4">
            <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3">
              <div>
                <h1 className="font-heading text-[36px] font-semibold text-ink leading-tight">
                  Подборка из каталога Hoff
                </h1>
                <p className="font-body text-[14px] text-muted mt-1">
                  {ALL_PRODUCTS.length} реальных товаров · Скандинавский стиль · Средний бюджет
                </p>
              </div>
              <Link
                href="/visualization"
                className="hidden sm:flex items-center gap-1.5 font-body text-[13px] text-muted hover:text-terracotta transition-colors flex-shrink-0"
              >
                <RefreshCw size={13} /> Пересмотреть план
              </Link>
            </div>

            {/* Search */}
            <div className="relative max-w-[400px]">
              <input
                type="text"
                placeholder="Поиск по названию..."
                value={search}
                onChange={e => setSearch(e.target.value)}
                className="input pr-8 text-[14px]"
              />
              {search && (
                <button
                  onClick={() => setSearch('')}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-ink"
                >
                  <X size={14} />
                </button>
              )}
            </div>
          </div>

          {/* Category tabs */}
          <div className="px-6 md:px-10 pb-4">
            <div className="flex gap-2 overflow-x-auto pb-1" style={{ scrollbarWidth: 'none' }}>
              <button
                onClick={() => setActiveTab('all')}
                className={`flex-shrink-0 px-4 py-2 rounded-xl font-body text-[13px] font-medium transition-all
                  ${activeTab === 'all'
                    ? 'bg-terracotta text-white'
                    : 'bg-white border border-border text-ink hover:border-terracotta/40'
                  }`}
              >
                Всё ({ALL_PRODUCTS.length})
              </button>
              {CATEGORIES.map(cat => (
                <button
                  key={cat.key}
                  onClick={() => setActiveTab(cat.key)}
                  className={`flex-shrink-0 flex items-center gap-1.5 px-4 py-2 rounded-xl font-body text-[13px] font-medium transition-all
                    ${activeTab === cat.key
                      ? 'bg-terracotta text-white'
                      : 'bg-white border border-border text-ink hover:border-terracotta/40'
                    }`}
                >
                  <span>{cat.icon}</span>
                  {cat.label} ({cat.products.length})
                </button>
              ))}
            </div>
          </div>

          {/* Products grid */}
          <div className="px-6 md:px-10 pb-10 flex-1">
            {filtered.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 gap-3">
                <p className="font-body text-[15px] text-muted">Ничего не найдено</p>
                <button onClick={() => setSearch('')} className="btn-ghost text-[13px]">
                  Сбросить поиск
                </button>
              </div>
            ) : (
              <>
                <p className="font-body text-[12px] text-muted mb-4">
                  Показано {filtered.length} товаров
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
                  {filtered.map(product => (
                    <ProductCard
                      key={product.id}
                      product={product}
                      inCart={!!cart[product.id]}
                      onToggle={() => toggleCart(product.id)}
                    />
                  ))}
                </div>
              </>
            )}
          </div>
        </div>

        {/* ── Sidebar: Смета ── */}
        <div className="lg:w-[300px] xl:w-[320px] border-t lg:border-t-0 lg:border-l border-border bg-white flex flex-col lg:sticky lg:top-[112px] lg:h-[calc(100vh-112px)] overflow-y-auto flex-shrink-0">
          <div className="p-6 flex flex-col gap-5 flex-1">
            <div>
              <h2 className="font-heading text-[22px] font-semibold text-ink">Смета</h2>
              <p className="font-body text-[13px] text-muted mt-0.5">
                {cartCount > 0
                  ? `${cartCount} из ${ALL_PRODUCTS.length} товаров`
                  : 'Нажмите 🛍 чтобы добавить товар'}
              </p>
            </div>

            {/* Cart items */}
            {cartItems.length > 0 ? (
              <div className="flex flex-col gap-2 flex-1">
                {cartItems.map(item => (
                  <div key={item.id} className="flex items-center gap-2.5 group">
                    {/* Mini image */}
                    <div className="w-10 h-10 rounded-lg overflow-hidden flex-shrink-0 bg-cream relative">
                      <Image
                        src={item.image}
                        alt={item.name}
                        fill
                        className="object-cover"
                        sizes="40px"
                        unoptimized
                      />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="font-body text-[12px] text-ink font-medium truncate">{item.name}</p>
                      <p className="font-body text-[11px] text-terracotta font-semibold">
                        {formatPrice(item.price_rub)}
                      </p>
                    </div>
                    <button
                      onClick={() => removeFromCart(item.id)}
                      className="opacity-0 group-hover:opacity-100 transition-opacity text-muted hover:text-terracotta flex-shrink-0"
                    >
                      <X size={13} />
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center gap-3 py-8 text-center">
                <div className="w-12 h-12 rounded-2xl bg-paper flex items-center justify-center">
                  <ShoppingBag size={20} className="text-muted" />
                </div>
                <p className="font-body text-[13px] text-muted leading-relaxed">
                  Добавляйте понравившиеся товары — и здесь появится смета
                </p>
              </div>
            )}

            {/* Totals & CTA */}
            {cartItems.length > 0 && (
              <div className="flex flex-col gap-3 border-t border-border pt-4">
                {/* По категориям */}
                <div className="flex flex-col gap-1.5">
                  {CATEGORIES.filter(cat => cartItems.some(i => i.category === cat.key)).map(cat => {
                    const catItems = cartItems.filter(i => i.category === cat.key)
                    const catTotal = catItems.reduce((s, p) => s + p.price_rub, 0)
                    return (
                      <div key={cat.key} className="flex items-center justify-between">
                        <span className="font-body text-[12px] text-muted flex items-center gap-1">
                          {cat.icon} {cat.label} ({catItems.length})
                        </span>
                        <span className="font-body text-[12px] text-ink">{formatPrice(catTotal)}</span>
                      </div>
                    )
                  })}
                </div>

                {/* Итого */}
                <div className="flex items-center justify-between border-t border-border pt-3">
                  <span className="font-body text-[14px] font-medium text-ink">Итого</span>
                  <span className="font-heading text-[22px] font-semibold text-ink">
                    {formatPrice(cartTotal)}
                  </span>
                </div>

                {/* Скидки */}
                {cartItems.some(i => i.old_price_rub) && (
                  <div className="flex items-center gap-2 px-3 py-2 bg-sage-50 rounded-xl">
                    <Tag size={13} className="text-sage flex-shrink-0" />
                    <p className="font-body text-[12px] text-sage-dark">
                      Экономия:{' '}
                      <span className="font-semibold">
                        {formatPrice(
                          cartItems.reduce((s, p) => s + ((p.old_price_rub ?? p.price_rub) - p.price_rub), 0)
                        )}
                      </span>
                    </p>
                  </div>
                )}

                <button className="btn-primary py-3 text-[14px] flex items-center justify-center gap-2">
                  <Download size={15} /> Скачать смету PDF
                </button>

                <p className="font-body text-[11px] text-muted text-center">
                  Ссылки на товары сохраняются в PDF
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
