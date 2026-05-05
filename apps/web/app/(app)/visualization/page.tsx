'use client'

/**
 * Финальная визуализация квартиры.
 *
 * АРХИТЕКТУРА (новая):
 *  - 3D-план рендерится ДЕТЕРМИНИРОВАННО из locked geometry + validated placement.
 *    Никакой AI-img2img — невозможно "увести" стены или окна.
 *  - Per-room фото генерируется AI, но ТОЛЬКО с validated catalog items
 *    и FIXED render-style template.
 *
 * Pipeline-инвариант: эта страница не доступна, пока:
 *  - geometry.user_validated === true
 *  - placement существует и validated
 */

import { useCallback, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import Image from 'next/image'
import {
  ArrowRight, Loader2, ZoomIn, X, Sparkles, AlertCircle,
  RotateCcw, Building2, Camera, Play, Lock, Download,
  Box, Grid3X3, AlertTriangle,
} from 'lucide-react'
import StepHeader from '@/components/StepHeader'
import { TopDownPlanRenderer, canvasToDataURL } from '@/components/TopDownPlanRenderer'
import { useGeometryStore, ROOM_LABEL_RU, type Room } from '@/store/geometryStore'
import { useVisualizationStore } from '@/store/visualizationStore'
import { usePreferencesStore, STYLE_LABELS } from '@/store/preferencesStore'
import { ALL_PRODUCTS } from '@/lib/catalog'
import type { RoomType, StyleType } from '@/lib/promptBuilder'

type ViewMode = 'isometric' | 'plan'
type MainTab = '3d' | 'photo'

// Маппинг RoomLabel → RoomType для AI-промптов
const ROOM_LABEL_TO_TYPE: Record<string, RoomType> = {
  living_room: 'living',
  bedroom:     'bedroom',
  kitchen:     'kitchen',
  kids_room:   'kids',
  corridor:    'hallway',
  bathroom:    'hallway',  // fallback
  toilet:      'hallway',
  balcony:     'living',
  storage:     'hallway',
  unknown:     'living',
}

export default function VisualizationPage() {
  const router = useRouter()
  const { geometry, placement, validationErrors, validationWarnings } = useGeometryStore()
  const { rooms: roomPhotos, setRoom: setRoomPhoto } = useVisualizationStore()
  const { style: selectedStyle } = usePreferencesStore()
  const currentStyle: StyleType = selectedStyle ?? 'scandi'

  const [mainTab, setMainTab] = useState<MainTab>('3d')
  const [viewMode, setViewMode] = useState<ViewMode>('isometric')
  const [zoomedPlan, setZoomedPlan] = useState(false)
  const [planCanvasRef, setPlanCanvasRef] = useState<HTMLCanvasElement | null>(null)

  // Каталог по item_id (для отображения)
  const catalogIndex = useMemo(() => {
    const map = new Map<string, { name: string; category: string; image_url?: string }>()
    for (const p of ALL_PRODUCTS) {
      map.set(p.id, { name: p.name, category: p.category, image_url: p.image })
    }
    return map
  }, [])

  // ── Guard: если нет валидированной геометрии — отправить в pipeline ──────
  if (!geometry || !geometry.user_validated) {
    return (
      <div className="min-h-screen bg-paper flex flex-col">
        <StepHeader current={3} backHref="/upload" backLabel="К началу" />
        <div className="flex-1 flex flex-col items-center justify-center gap-6 px-6">
          <Lock size={48} className="text-muted" />
          <div className="text-center max-w-md">
            <p className="font-heading text-[24px] font-semibold text-ink">
              Геометрия ещё не подтверждена
            </p>
            <p className="font-body text-[14px] text-muted mt-2">
              Сначала нужно загрузить план и подтвердить распознанную геометрию.
            </p>
          </div>
          <button
            onClick={() => router.push('/upload')}
            className="btn-primary px-8 py-3 flex items-center gap-2"
          >
            Начать заново <ArrowRight size={16} />
          </button>
        </div>
      </div>
    )
  }

  // ── Подсчёты ──────────────────────────────────────────────────────────────
  const totalItems   = placement?.rooms.reduce((s, r) => s + r.placed_items.length, 0) ?? 0
  const totalPrice   = placement?.total_price_rub ?? 0
  const placedRooms  = placement?.rooms.filter(r => r.placed_items.length > 0) ?? []

  // ── Per-room фото генерация ───────────────────────────────────────────────
  const generateRoomPhoto = useCallback(async (room: Room) => {
    const roomType: RoomType = ROOM_LABEL_TO_TYPE[room.label] ?? 'living'
    const roomLayout = placement?.rooms.find(rl => rl.room_id === room.id)

    setRoomPhoto(roomType, { status: 'loading', error: undefined })

    try {
      // Validated catalog items для этой комнаты (НЕ DEFAULT_FURNITURE)
      const validatedItems = (roomLayout?.placed_items ?? [])
        .map(pi => {
          const cat = catalogIndex.get(pi.item_id)
          return cat ? { name: cat.name, category: cat.category } : null
        })
        .filter((x): x is { name: string; category: string } => x !== null)

      const res = await fetch('/api/visualize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          room: roomType,
          style: currentStyle,
          furniture: validatedItems,
          // Передаём locked-данные для строгого промпта
          locked: {
            room_label: room.label,
            area_m2: room.area_m2,
            placed_count: validatedItems.length,
          },
        }),
      })
      const data = await res.json()
      if (!res.ok || data.error) {
        setRoomPhoto(roomType, { status: 'error', error: data.error ?? 'Ошибка' })
        return
      }
      setRoomPhoto(roomType, { status: 'done', imageUrl: data.imageUrl })
    } catch (err: any) {
      setRoomPhoto(roomType, { status: 'error', error: err?.message ?? 'Ошибка сети' })
    }
  }, [placement, catalogIndex, currentStyle, setRoomPhoto])

  // Скачать PNG плана
  const handleDownload = () => {
    if (!planCanvasRef) return
    const url = canvasToDataURL(planCanvasRef)
    const a = document.createElement('a')
    a.href = url
    a.download = `apartment-${currentStyle}.png`
    a.click()
  }

  return (
    <div className="min-h-screen bg-paper flex flex-col">
      <StepHeader current={3} backHref="/analysis" backLabel="К геометрии" />

      <main className="flex-1 flex flex-col px-6 md:px-10 py-8 gap-6 max-w-[1200px] w-full mx-auto">

        {/* Title + locked badge */}
        <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
          <div>
            <h1 className="font-heading text-[38px] font-semibold text-ink leading-tight">
              Ваша квартира
            </h1>
            <p className="font-body text-[15px] text-muted mt-1">
              {STYLE_LABELS[currentStyle]} · {totalItems} предметов из каталога Hoff · {totalPrice.toLocaleString('ru-RU')} ₽
            </p>
          </div>
          <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-sage-50 border border-sage/30">
            <Lock size={14} className="text-sage-dark" />
            <span className="font-body text-[12px] text-sage-dark font-medium">
              Геометрия зафиксирована
            </span>
          </div>
        </div>

        {/* Validation alerts */}
        {validationErrors.length > 0 && (
          <div className="flex items-start gap-3 px-4 py-3 bg-red-50 border border-red-200 rounded-xl">
            <AlertCircle size={18} className="text-red-600 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="font-body text-[13px] font-semibold text-red-700">
                Найдены ошибки расстановки ({validationErrors.length})
              </p>
              <ul className="font-body text-[12px] text-red-600 mt-1 list-disc pl-5 space-y-0.5">
                {validationErrors.slice(0, 3).map((e, i) => <li key={i}>{e}</li>)}
                {validationErrors.length > 3 && <li>…ещё {validationErrors.length - 3}</li>}
              </ul>
            </div>
          </div>
        )}
        {validationWarnings.length > 0 && (
          <div className="flex items-start gap-3 px-4 py-3 bg-yellow-50 border border-yellow-200 rounded-xl">
            <AlertTriangle size={18} className="text-yellow-600 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="font-body text-[13px] font-semibold text-yellow-700">
                Предупреждения ({validationWarnings.length})
              </p>
              <ul className="font-body text-[12px] text-yellow-700 mt-1 list-disc pl-5 space-y-0.5">
                {validationWarnings.slice(0, 2).map((w, i) => <li key={i}>{w}</li>)}
              </ul>
            </div>
          </div>
        )}

        {/* Tabs */}
        <div className="flex gap-1 p-1 bg-white rounded-xl border border-border w-fit">
          <button
            onClick={() => setMainTab('3d')}
            className={`px-5 py-2 rounded-lg font-body text-[14px] font-medium transition-all flex items-center gap-2
              ${mainTab === '3d' ? 'bg-terracotta text-white shadow-sm' : 'text-muted hover:text-ink'}`}
          >
            <Building2 size={15} /> План квартиры
          </button>
          <button
            onClick={() => setMainTab('photo')}
            className={`px-5 py-2 rounded-lg font-body text-[14px] font-medium transition-all flex items-center gap-2
              ${mainTab === 'photo' ? 'bg-terracotta text-white shadow-sm' : 'text-muted hover:text-ink'}`}
          >
            <Camera size={15} /> Фото интерьеров
          </button>
        </div>

        {/* ── 3D PLAN TAB ─────────────────────────────────────────────────── */}
        <div style={{ display: mainTab === '3d' ? 'flex' : 'none' }} className="flex-col gap-4">

          {/* View mode toggle */}
          <div className="flex items-center justify-between gap-4">
            <div className="flex gap-1 p-1 bg-white rounded-xl border border-border w-fit">
              <button
                onClick={() => setViewMode('isometric')}
                className={`px-4 py-1.5 rounded-lg font-body text-[12px] font-medium transition-all flex items-center gap-1.5
                  ${viewMode === 'isometric' ? 'bg-terracotta text-white' : 'text-muted hover:text-ink'}`}
              >
                <Box size={13} /> Изометрия 3D
              </button>
              <button
                onClick={() => setViewMode('plan')}
                className={`px-4 py-1.5 rounded-lg font-body text-[12px] font-medium transition-all flex items-center gap-1.5
                  ${viewMode === 'plan' ? 'bg-terracotta text-white' : 'text-muted hover:text-ink'}`}
              >
                <Grid3X3 size={13} /> 2D план
              </button>
            </div>

            <div className="flex gap-2">
              <button
                onClick={() => setZoomedPlan(true)}
                className="flex items-center gap-2 px-3 py-2 rounded-xl border border-border bg-white font-body text-[12px] text-muted hover:border-terracotta hover:text-terracotta transition-colors"
              >
                <ZoomIn size={13} /> Увеличить
              </button>
              <button
                onClick={handleDownload}
                className="flex items-center gap-2 px-3 py-2 rounded-xl border border-border bg-white font-body text-[12px] text-muted hover:border-terracotta hover:text-terracotta transition-colors"
              >
                <Download size={13} /> PNG
              </button>
            </div>
          </div>

          {/* Detached canvas */}
          <div className="relative rounded-2xl overflow-hidden border border-border bg-white shadow-md">
            <TopDownPlanRenderer
              geometry={geometry}
              placement={placement}
              catalog={catalogIndex}
              style={currentStyle}
              mode={viewMode}
              showLabels
              onCanvasReady={setPlanCanvasRef}
            />
            <div className="absolute top-3 left-3 flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-black/25 backdrop-blur-sm">
              <Lock size={11} className="text-white" />
              <span className="font-body text-[11px] text-white">
                {viewMode === 'isometric' ? 'Изометрия 3D' : 'Top-down 2D'} · детерминированный рендер
              </span>
            </div>
          </div>

          {/* Info card */}
          <div className="flex items-start gap-2 px-4 py-3 bg-sage-50 rounded-xl">
            <Sparkles size={14} className="text-sage-dark flex-shrink-0 mt-0.5" />
            <div>
              <p className="font-body text-[12px] text-sage-dark font-semibold">
                Стены, окна и двери — точно как на вашем плане
              </p>
              <p className="font-body text-[11px] text-sage-dark/80 mt-0.5">
                Этот вид рендерится напрямую из подтверждённой геометрии без участия AI.
                Каждая регенерация даст ровно тот же результат.
              </p>
            </div>
          </div>

          {/* Zoom modal */}
          {zoomedPlan && (
            <div className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center p-4" onClick={() => setZoomedPlan(false)}>
              <button onClick={() => setZoomedPlan(false)} className="absolute top-4 right-4 w-10 h-10 rounded-full bg-white/10 flex items-center justify-center hover:bg-white/20">
                <X size={18} className="text-white" />
              </button>
              <div className="max-w-[90vw] max-h-[90vh]" onClick={e => e.stopPropagation()}>
                <TopDownPlanRenderer
                  geometry={geometry}
                  placement={placement}
                  catalog={catalogIndex}
                  style={currentStyle}
                  mode={viewMode}
                  showLabels
                />
              </div>
            </div>
          )}
        </div>

        {/* ── PHOTO TAB ────────────────────────────────────────────────────── */}
        <div style={{ display: mainTab === 'photo' ? 'flex' : 'none' }} className="flex-col gap-4">
          <p className="font-body text-[13px] text-muted">
            AI генерирует фото каждой комнаты с реальной мебелью из расстановки. Стили рендера фиксированы.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {placedRooms.map(rl => {
              const room = geometry.rooms.find(r => r.id === rl.room_id)
              if (!room) return null
              const roomType: RoomType = ROOM_LABEL_TO_TYPE[room.label] ?? 'living'
              const photo = roomPhotos.find(p => p.id === roomType)
              const status = photo?.status ?? 'idle'

              return (
                <div key={room.id} className="card overflow-hidden flex flex-col">
                  <div className="relative bg-cream overflow-hidden" style={{ aspectRatio: '16/9' }}>
                    {status === 'done' && photo?.imageUrl ? (
                      <Image src={photo.imageUrl} alt={ROOM_LABEL_RU[room.label]}
                             fill className="object-cover" sizes="(max-width: 768px) 100vw, 50vw" unoptimized />
                    ) : status === 'loading' ? (
                      <div className="absolute inset-0 flex flex-col items-center justify-center gap-3">
                        <div className="absolute inset-0 bg-gradient-to-br from-cream via-[#E8D8C8] to-[#D8C8B8] animate-pulse" />
                        <div className="relative flex flex-col items-center gap-3">
                          <Sparkles size={22} className="text-terracotta animate-pulse" />
                          <p className="font-body text-[13px] text-ink/70">AI рисует интерьер…</p>
                        </div>
                      </div>
                    ) : status === 'error' ? (
                      <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 px-4">
                        <AlertCircle size={28} className="text-terracotta/60" />
                        <button onClick={() => generateRoomPhoto(room)}
                                className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-white border border-border font-body text-[13px] text-ink hover:border-terracotta">
                          <RotateCcw size={13} /> Попробовать снова
                        </button>
                      </div>
                    ) : (
                      <div className="absolute inset-0 flex items-center justify-center">
                        <button onClick={() => generateRoomPhoto(room)}
                                className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-terracotta text-white font-body text-[13px] font-medium hover:bg-terracotta/90 shadow-md">
                          <Play size={13} fill="white" /> Сгенерировать фото
                        </button>
                      </div>
                    )}
                  </div>
                  <div className="px-4 py-3 flex items-center justify-between">
                    <div>
                      <p className="font-body text-[13px] font-semibold text-ink">
                        {ROOM_LABEL_RU[room.label]}
                      </p>
                      <p className="font-body text-[11px] text-muted">
                        {rl.placed_items.length} предметов
                        {room.area_m2 && ` · ${room.area_m2} м²`}
                      </p>
                    </div>
                    {status === 'done' && (
                      <button onClick={() => generateRoomPhoto(room)}
                              className="flex items-center gap-1 px-2.5 py-1 rounded-lg border border-border font-body text-[11px] text-muted hover:border-terracotta hover:text-terracotta">
                        <RotateCcw size={11} />
                      </button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* CTA */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pt-4 border-t border-border">
          <div>
            <p className="font-body text-[14px] font-medium text-ink">Нравится план?</p>
            <p className="font-body text-[13px] text-muted">
              Перейдите к списку реальных товаров — всё уже подобрано
            </p>
          </div>
          <div className="flex gap-3">
            <button onClick={() => router.push('/analysis')} className="btn-ghost py-3 px-5 text-[14px]">
              ← Изменить геометрию
            </button>
            <button onClick={() => router.push('/results')} className="btn-primary py-3 px-7 text-[15px] flex items-center gap-2">
              К списку товаров <ArrowRight size={16} />
            </button>
          </div>
        </div>
      </main>
    </div>
  )
}
