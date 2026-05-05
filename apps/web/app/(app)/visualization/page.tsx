'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import Image from 'next/image'
import { ArrowRight, RefreshCw, Loader2, ZoomIn, X, Upload, Sparkles, AlertCircle, RotateCcw } from 'lucide-react'
import StepHeader from '@/components/StepHeader'
import { usePlanStore } from '@/store/planStore'
import { DEFAULT_FURNITURE, type RoomType, type StyleType } from '@/lib/promptBuilder'

// ─── Types ────────────────────────────────────────────────────────────────────

type MainTab = 'plan' | 'photo'
type PlanMode = 'original' | 'furniture'

interface GeneratedRoom {
  id: RoomType
  label: string
  imageUrl: string | null
  status: 'idle' | 'loading' | 'done' | 'error'
  error?: string
  prompt?: string
}

const ROOMS: { id: RoomType; label: string; emoji: string }[] = [
  { id: 'living', label: 'Гостиная', emoji: '🛋' },
  { id: 'bedroom', label: 'Спальня', emoji: '🛏' },
  { id: 'kitchen', label: 'Кухня-столовая', emoji: '🍽' },
  { id: 'kids', label: 'Детская', emoji: '🧸' },
]

// ─── SVG Furniture overlay (same as before) ───────────────────────────────────

const FURNITURE_ITEMS = [
  { id: 's1', color: '#D4795C', opacity: 0.52, x: 68, y: 7, w: 26, h: 12, rx: 1.5, label: 'Диван Мэдисон' },
  { id: 's2', color: '#D4795C', opacity: 0.42, x: 68, y: 19, w: 9, h: 8, rx: 1.5, label: '' },
  { id: 's3', color: '#C8B4A0', opacity: 0.62, x: 80, y: 20, w: 8, h: 6, rx: 1, label: 'Столик' },
  { id: 's4', color: '#7A8F7A', opacity: 0.52, x: 90, y: 7, w: 5, h: 18, rx: 0.5, label: 'ТВ-тумба' },
  { id: 's5', color: '#D4795C', opacity: 0.42, x: 79, y: 30, w: 8, h: 8, rx: 1.5, label: 'Кресло Скотт' },
  { id: 'b1', color: '#7A8F7A', opacity: 0.52, x: 4, y: 8, w: 18, h: 22, rx: 1.5, label: 'Кровать' },
  { id: 'b2', color: '#A0B0A0', opacity: 0.58, x: 4, y: 16, w: 4, h: 6, rx: 0.5, label: '' },
  { id: 'b3', color: '#A0B0A0', opacity: 0.58, x: 18, y: 16, w: 4, h: 6, rx: 0.5, label: '' },
  { id: 'b4', color: '#C8B4A0', opacity: 0.58, x: 4, y: 33, w: 20, h: 5, rx: 0.5, label: 'Шкаф Эванс' },
  { id: 'b5', color: '#D4795C', opacity: 0.38, x: 22, y: 30, w: 6, h: 7, rx: 2, label: 'Кресло Норд' },
  { id: 'k1', color: '#7A8F7A', opacity: 0.48, x: 14, y: 55, w: 15, h: 10, rx: 1.5, label: 'Кровать детская' },
  { id: 'k2', color: '#C8B4A0', opacity: 0.58, x: 4, y: 55, w: 9, h: 8, rx: 1, label: 'Стол' },
  { id: 'k3', color: '#D4795C', opacity: 0.38, x: 10, y: 80, w: 18, h: 8, rx: 1.5, label: 'Диван Gap' },
  { id: 'd1', color: '#C8B4A0', opacity: 0.62, x: 75, y: 58, w: 14, h: 18, rx: 1, label: 'Стол обеденный' },
  { id: 'd2', color: '#C8B4A0', opacity: 0.48, x: 72, y: 62, w: 3.5, h: 5, rx: 1, label: '' },
  { id: 'd3', color: '#C8B4A0', opacity: 0.48, x: 72, y: 69, w: 3.5, h: 5, rx: 1, label: '' },
  { id: 'd4', color: '#C8B4A0', opacity: 0.48, x: 89.5, y: 62, w: 3.5, h: 5, rx: 1, label: '' },
  { id: 'd5', color: '#C8B4A0', opacity: 0.48, x: 89.5, y: 69, w: 3.5, h: 5, rx: 1, label: '' },
  { id: 'e1', color: '#7A8F7A', opacity: 0.48, x: 57, y: 55, w: 16, h: 5, rx: 0.5, label: 'Кухня' },
  { id: 'g1', color: '#C8B4A0', opacity: 0.52, x: 55, y: 58, w: 4, h: 22, rx: 0.5, label: 'Гардероб' },
]

// ─── Plan overlay ─────────────────────────────────────────────────────────────

function PlanView({ planUrl, mode }: { planUrl: string; mode: PlanMode }) {
  const [zoomed, setZoomed] = useState(false)

  const Overlay = () => (
    <svg className="absolute inset-0 w-full h-full pointer-events-none" viewBox="0 0 100 100" preserveAspectRatio="none">
      <defs>
        <filter id="fs"><feDropShadow dx="0.3" dy="0.5" stdDeviation="0.8" floodOpacity="0.22" /></filter>
      </defs>
      {FURNITURE_ITEMS.map(f => (
        <g key={f.id}>
          <rect x={f.x} y={f.y} width={f.w} height={f.h} rx={f.rx} fill={f.color} opacity={f.opacity} filter="url(#fs)" />
          <rect x={f.x + 0.3} y={f.y + 0.3} width={f.w - 0.6} height={Math.min(f.h * 0.3, 1.8)} rx={f.rx} fill="white" opacity={0.18} />
          {f.label && f.w > 8 && f.h > 5 && (
            <text x={f.x + f.w / 2} y={f.y + f.h / 2 + 0.8} textAnchor="middle" fontSize="1.9" fontFamily="Onest, sans-serif" fill="white" fontWeight="600" opacity={0.88}>{f.label.length > 14 ? f.label.slice(0, 13) + '…' : f.label}</text>
          )}
        </g>
      ))}
    </svg>
  )

  return (
    <>
      <div className="relative w-full rounded-2xl overflow-hidden border border-border shadow-sm bg-white cursor-zoom-in" onClick={() => setZoomed(true)}>
        <img src={planUrl} alt="План" className="w-full h-auto block" style={{ filter: mode === 'furniture' ? 'brightness(0.9) contrast(1.08)' : 'none' }} draggable={false} />
        {mode === 'furniture' && <Overlay />}
        <div className="absolute bottom-3 right-3 flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-black/30 backdrop-blur-sm">
          <ZoomIn size={12} className="text-white" /><span className="font-body text-[11px] text-white">Увеличить</span>
        </div>
      </div>
      {mode === 'furniture' && (
        <div className="flex flex-wrap gap-3">
          {[{ color: '#D4795C', label: 'Мягкая мебель' }, { color: '#7A8F7A', label: 'Спальные места' }, { color: '#C8B4A0', label: 'Столы и хранение' }].map(l => (
            <div key={l.label} className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-sm" style={{ background: l.color, opacity: 0.72 }} />
              <span className="font-body text-[12px] text-muted">{l.label}</span>
            </div>
          ))}
        </div>
      )}
      {zoomed && (
        <div className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4" onClick={() => setZoomed(false)}>
          <div className="relative max-w-5xl max-h-[90vh] w-full">
            <button onClick={() => setZoomed(false)} className="absolute -top-9 right-0 flex items-center gap-2 text-white/70 hover:text-white font-body text-[14px]">
              <X size={16} /> Закрыть
            </button>
            <div className="relative rounded-xl overflow-hidden">
              <img src={planUrl} alt="План" className="w-full h-auto max-h-[85vh] object-contain" draggable={false} style={{ filter: mode === 'furniture' ? 'brightness(0.9) contrast(1.08)' : 'none' }} />
              {mode === 'furniture' && <Overlay />}
            </div>
          </div>
        </div>
      )}
    </>
  )
}

// ─── Single Room Photo Card ───────────────────────────────────────────────────

function RoomPhotoCard({
  room,
  style,
  onGenerate,
}: {
  room: GeneratedRoom
  style: StyleType
  onGenerate: (id: RoomType) => void
}) {
  const [zoomed, setZoomed] = useState(false)

  return (
    <>
      <div className="card overflow-hidden flex flex-col">
        {/* Image area */}
        <div className="relative bg-cream overflow-hidden" style={{ aspectRatio: '16/9' }}>
          {room.status === 'done' && room.imageUrl ? (
            <>
              <Image
                src={room.imageUrl}
                alt={room.label}
                fill
                className="object-cover"
                sizes="(max-width: 768px) 100vw, 50vw"
                unoptimized
              />
              {/* Actions overlay */}
              <div className="absolute inset-0 bg-gradient-to-t from-black/40 via-transparent to-transparent opacity-0 hover:opacity-100 transition-opacity">
                <div className="absolute bottom-3 left-3 right-3 flex items-center justify-between">
                  <button onClick={() => setZoomed(true)} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/20 backdrop-blur-sm font-body text-[12px] text-white hover:bg-white/30 transition-colors">
                    <ZoomIn size={13} /> Открыть
                  </button>
                  <button onClick={() => onGenerate(room.id)} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/20 backdrop-blur-sm font-body text-[12px] text-white hover:bg-white/30 transition-colors">
                    <RotateCcw size={12} /> Перегенерировать
                  </button>
                </div>
              </div>
            </>
          ) : room.status === 'loading' ? (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-3">
              {/* Animated placeholder */}
              <div className="absolute inset-0 bg-gradient-to-br from-cream via-[#E8D8C8] to-[#D8C8B8] animate-pulse" />
              <div className="relative flex flex-col items-center gap-3">
                <div className="relative">
                  <div className="w-12 h-12 rounded-2xl bg-white/60 backdrop-blur-sm flex items-center justify-center">
                    <Sparkles size={22} className="text-terracotta animate-pulse" />
                  </div>
                </div>
                <div className="text-center">
                  <p className="font-body text-[13px] font-medium text-ink/70">AI рисует интерьер…</p>
                  <p className="font-body text-[11px] text-muted mt-0.5">обычно 5–15 секунд</p>
                </div>
                {/* Progress dots */}
                <div className="flex gap-1.5">
                  {[0, 1, 2, 3].map(i => (
                    <div key={i} className="w-1.5 h-1.5 rounded-full bg-terracotta animate-bounce" style={{ animationDelay: `${i * 180}ms` }} />
                  ))}
                </div>
              </div>
            </div>
          ) : room.status === 'error' ? (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 px-4">
              <AlertCircle size={28} className="text-terracotta/60" />
              <div className="text-center">
                <p className="font-body text-[13px] font-medium text-ink">Ошибка генерации</p>
                <p className="font-body text-[11px] text-muted mt-0.5 line-clamp-2">{room.error}</p>
              </div>
              <button onClick={() => onGenerate(room.id)} className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-white border border-border font-body text-[13px] text-ink hover:border-terracotta hover:text-terracotta transition-colors">
                <RotateCcw size={13} /> Попробовать снова
              </button>
            </div>
          ) : (
            /* idle */
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-4">
              <div className="w-14 h-14 rounded-2xl bg-white/80 backdrop-blur-sm border border-border flex items-center justify-center shadow-sm">
                <Sparkles size={24} className="text-terracotta/60" />
              </div>
              <button onClick={() => onGenerate(room.id)} className="btn-primary py-2.5 px-5 text-[13px] flex items-center gap-2 shadow-md">
                <Sparkles size={14} /> Сгенерировать
              </button>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-4 py-3 flex items-center justify-between">
          <div>
            <p className="font-body text-[13px] font-semibold text-ink">{room.label}</p>
            <p className="font-body text-[11px] text-muted">
              {DEFAULT_FURNITURE[room.id].slice(0, 2).map(f => f.name.split(' ').slice(0, 2).join(' ')).join(', ')}
            </p>
          </div>
          <span className={`font-body text-[11px] px-2.5 py-1 rounded-full flex-shrink-0 ${
            room.status === 'done' ? 'bg-sage-50 text-sage-dark' :
            room.status === 'loading' ? 'bg-terracotta-100 text-terracotta' :
            room.status === 'error' ? 'bg-red-50 text-red-500' :
            'bg-border text-muted'
          }`}>
            {room.status === 'done' ? '✓ Готово' :
             room.status === 'loading' ? 'Генерируется…' :
             room.status === 'error' ? 'Ошибка' : 'Ожидание'}
          </span>
        </div>
      </div>

      {/* Zoom modal */}
      {zoomed && room.imageUrl && (
        <div className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center p-4" onClick={() => setZoomed(false)}>
          <button onClick={() => setZoomed(false)} className="absolute top-4 right-4 w-10 h-10 rounded-full bg-white/10 flex items-center justify-center hover:bg-white/20 transition-colors">
            <X size={18} className="text-white" />
          </button>
          <div className="max-w-5xl max-h-[90vh] w-full" onClick={e => e.stopPropagation()}>
            <p className="font-heading text-[22px] text-white mb-3">{room.label}</p>
            <div className="relative rounded-2xl overflow-hidden" style={{ aspectRatio: '16/9' }}>
              <Image src={room.imageUrl} alt={room.label} fill className="object-cover" unoptimized />
            </div>
            <p className="font-body text-[12px] text-white/50 mt-3 line-clamp-2">{room.prompt}</p>
          </div>
        </div>
      )}
    </>
  )
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function VisualizationPage() {
  const router = useRouter()
  const { planUrl } = usePlanStore()
  const [mainTab, setMainTab] = useState<MainTab>('photo')
  const [planMode, setPlanMode] = useState<PlanMode>('furniture')
  const [currentStyle] = useState<StyleType>('scandi')

  const [rooms, setRooms] = useState<GeneratedRoom[]>(
    ROOMS.map(r => ({ id: r.id, label: r.label, imageUrl: null, status: 'idle' }))
  )

  const generateRoom = useCallback(async (roomId: RoomType) => {
    setRooms(prev => prev.map(r => r.id === roomId ? { ...r, status: 'loading', error: undefined } : r))

    try {
      const res = await fetch('/api/visualize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          room: roomId,
          style: currentStyle,
          furniture: DEFAULT_FURNITURE[roomId],
        }),
      })

      const data = await res.json()

      if (!res.ok || data.error) {
        const msg = data.code === 'NO_KEY'
          ? 'API ключ не настроен. Добавьте FAL_KEY в .env.local'
          : (data.error ?? 'Неизвестная ошибка')
        setRooms(prev => prev.map(r => r.id === roomId ? { ...r, status: 'error', error: msg } : r))
        return
      }

      setRooms(prev => prev.map(r =>
        r.id === roomId ? { ...r, status: 'done', imageUrl: data.imageUrl, prompt: data.prompt } : r
      ))
    } catch (err: any) {
      setRooms(prev => prev.map(r =>
        r.id === roomId ? { ...r, status: 'error', error: err?.message ?? 'Ошибка сети' } : r
      ))
    }
  }, [currentStyle])

  // Автоматически генерируем первые 2 комнаты при открытии
  useEffect(() => {
    generateRoom('living')
    const t = setTimeout(() => generateRoom('bedroom'), 800)
    return () => clearTimeout(t)
  }, []) // eslint-disable-line

  const allDone = rooms.every(r => r.status === 'done')
  const anyLoading = rooms.some(r => r.status === 'loading')

  const generateAll = () => {
    ROOMS.forEach((r, i) => {
      setTimeout(() => generateRoom(r.id), i * 600)
    })
  }

  return (
    <div className="min-h-screen bg-paper flex flex-col">
      <StepHeader current={2} backHref="/preferences" backLabel="Назад к предпочтениям" />

      <main className="flex-1 flex flex-col px-6 md:px-10 py-8 gap-6 max-w-[1100px] w-full mx-auto">
        {/* Title */}
        <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
          <div>
            <h1 className="font-heading text-[38px] font-semibold text-ink leading-tight">
              Ваша квартира с мебелью
            </h1>
            <p className="font-body text-[15px] text-muted mt-1">
              Скандинавский стиль · товары из каталога Hoff
            </p>
          </div>
          <div className="flex items-center gap-2">
            {anyLoading && (
              <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-terracotta-50 border border-terracotta/20">
                <Loader2 size={14} className="text-terracotta animate-spin" />
                <span className="font-body text-[13px] text-terracotta">Генерируется…</span>
              </div>
            )}
            <button
              onClick={generateAll}
              disabled={anyLoading}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl border border-border bg-white font-body text-[13px] text-muted hover:border-terracotta hover:text-terracotta transition-colors disabled:opacity-40"
            >
              <Sparkles size={14} /> Сгенерировать все
            </button>
          </div>
        </div>

        {/* Main tabs */}
        <div className="flex gap-1 p-1 bg-white rounded-xl border border-border w-fit">
          {([
            { id: 'photo' as MainTab, label: '📸 Фото интерьера' },
            { id: 'plan' as MainTab, label: '📐 На плане' },
          ]).map(tab => (
            <button key={tab.id} onClick={() => setMainTab(tab.id)}
              className={`px-5 py-2 rounded-lg font-body text-[14px] font-medium transition-all
                ${mainTab === tab.id ? 'bg-terracotta text-white shadow-sm' : 'text-muted hover:text-ink'}`}>
              {tab.label}
            </button>
          ))}
        </div>

        {/* ── Tab: Фото интерьера ── */}
        {mainTab === 'photo' && (
          <div className="flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <p className="font-body text-[14px] text-muted">
                AI генерирует реалистичные фото каждой комнаты с реальными товарами из каталога Hoff
              </p>
            </div>

            {/* 2×2 grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {rooms.map(room => (
                <RoomPhotoCard
                  key={room.id}
                  room={room}
                  style={currentStyle}
                  onGenerate={generateRoom}
                />
              ))}
            </div>

            <div className="flex items-start gap-2 px-4 py-3 bg-terracotta-50 rounded-xl">
              <Sparkles size={14} className="text-terracotta flex-shrink-0 mt-0.5" />
              <p className="font-body text-[12px] text-[#7A4033]">
                Визуализации генерируются через fal.ai (FLUX). Мебель подобрана из реального каталога Hoff.
                Нажмите на любую комнату чтобы перегенерировать с другим ракурсом.
              </p>
            </div>
          </div>
        )}

        {/* ── Tab: На плане ── */}
        {mainTab === 'plan' && (
          <div className="flex flex-col gap-4">
            <div className="flex items-center gap-2 flex-wrap">
              {([
                { id: 'original' as PlanMode, label: 'Исходный план' },
                { id: 'furniture' as PlanMode, label: 'С расстановкой мебели' },
              ]).map(mode => (
                <button key={mode.id} onClick={() => setPlanMode(mode.id)}
                  className={`px-4 py-2 rounded-xl font-body text-[13px] font-medium border transition-all
                    ${planMode === mode.id ? 'border-terracotta bg-terracotta-50 text-terracotta' : 'border-border bg-white text-muted hover:border-terracotta/40'}`}>
                  {mode.label}
                </button>
              ))}
            </div>

            {planUrl ? (
              <PlanView planUrl={planUrl} mode={planMode} />
            ) : (
              <div className="bg-white rounded-2xl border-2 border-dashed border-border flex flex-col items-center justify-center gap-4 py-20">
                <div className="w-14 h-14 rounded-2xl bg-terracotta-100 flex items-center justify-center">
                  <Upload size={24} className="text-terracotta" />
                </div>
                <div className="text-center">
                  <p className="font-body text-[15px] font-medium text-ink">План не загружен</p>
                  <p className="font-body text-[13px] text-muted mt-1">Вернитесь на первый шаг</p>
                </div>
                <button onClick={() => router.push('/upload')} className="btn-primary py-2.5 px-6 text-[14px]">
                  Загрузить план
                </button>
              </div>
            )}
          </div>
        )}

        {/* CTA */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pt-4 border-t border-border">
          <div>
            <p className="font-body text-[14px] font-medium text-ink">Нравится как выглядит?</p>
            <p className="font-body text-[13px] text-muted">Перейдите к выбору реальных товаров</p>
          </div>
          <div className="flex gap-3">
            <button onClick={() => router.push('/preferences')} className="btn-ghost py-3 px-5 text-[14px]">
              ← Изменить
            </button>
            <button onClick={() => router.push('/results')} className="btn-primary py-3 px-7 text-[15px] flex items-center gap-2">
              Выбрать товары <ArrowRight size={16} />
            </button>
          </div>
        </div>
      </main>
    </div>
  )
}
