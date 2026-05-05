'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import Image from 'next/image'
import {
  ArrowRight, Loader2, ZoomIn, X,
  Sparkles, AlertCircle, RotateCcw, Upload,
  Building2, Camera,
} from 'lucide-react'
import StepHeader from '@/components/StepHeader'
import { usePlanStore } from '@/store/planStore'
import { DEFAULT_FURNITURE, type RoomType, type StyleType } from '@/lib/promptBuilder'

// ─── Types ────────────────────────────────────────────────────────────────────

type MainTab = '3d' | 'photo'

interface GeneratedRoom {
  id: RoomType
  label: string
  imageUrl: string | null
  status: 'idle' | 'loading' | 'done' | 'error'
  error?: string
  prompt?: string
}

interface FloorplanState {
  imageUrl: string | null
  status: 'idle' | 'uploading' | 'generating' | 'done' | 'error'
  error?: string
}

const ROOMS: { id: RoomType; label: string; emoji: string }[] = [
  { id: 'living',  label: 'Гостиная',       emoji: '🛋' },
  { id: 'bedroom', label: 'Спальня',         emoji: '🛏' },
  { id: 'kitchen', label: 'Кухня-столовая',  emoji: '🍽' },
  { id: 'kids',    label: 'Детская',         emoji: '🧸' },
]

// ─── 3D Floor Plan View ───────────────────────────────────────────────────────

function FloorplanView({
  planUrl,
  planFile,
  style,
}: {
  planUrl: string | null
  planFile: File | null
  style: StyleType
}) {
  const { planFalUrl, setPlanFalUrl } = usePlanStore()
  const [state, setState] = useState<FloorplanState>({ imageUrl: null, status: 'idle' })
  const [zoomed, setZoomed] = useState(false)

  const generate = useCallback(async () => {
    setState({ imageUrl: null, status: 'uploading' })

    try {
      // Шаг 1: загружаем план в fal.ai storage (если ещё не загружен)
      let falUrl = planFalUrl
      if (!falUrl && planFile) {
        const fd = new FormData()
        fd.append('file', planFile)
        const uploadRes = await fetch('/api/upload-plan', { method: 'POST', body: fd })
        const uploadData = await uploadRes.json()
        if (!uploadRes.ok || uploadData.error) throw new Error(uploadData.error ?? 'Ошибка загрузки файла')
        falUrl = uploadData.url
        setPlanFalUrl(falUrl!)
      }

      if (!falUrl) throw new Error('Не удалось загрузить план')

      // Шаг 2: генерируем 3D визуализацию
      setState(s => ({ ...s, status: 'generating' }))
      const res = await fetch('/api/floorplan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ planUrl: falUrl, style }),
      })
      const data = await res.json()
      if (!res.ok || data.error) throw new Error(data.error ?? 'Ошибка генерации')

      setState({ imageUrl: data.imageUrl, status: 'done' })
    } catch (err: any) {
      setState({ imageUrl: null, status: 'error', error: err?.message ?? 'Ошибка' })
    }
  }, [planFile, planFalUrl, style, setPlanFalUrl])

  if (!planUrl || !planFile) {
    return (
      <div className="bg-white rounded-2xl border-2 border-dashed border-border flex flex-col items-center justify-center gap-4 py-20">
        <div className="w-14 h-14 rounded-2xl bg-terracotta-100 flex items-center justify-center">
          <Upload size={24} className="text-terracotta" />
        </div>
        <p className="font-body text-[15px] font-medium text-ink">План не загружен</p>
        <p className="font-body text-[13px] text-muted">Вернитесь на первый шаг</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-5">
      {/* Ваш план — референс */}
      <div className="flex items-start gap-4 p-4 bg-white rounded-2xl border border-border">
        <div className="relative w-24 h-16 rounded-xl overflow-hidden flex-shrink-0 border border-border">
          <img src={planUrl} alt="Ваш план" className="w-full h-full object-cover" />
        </div>
        <div className="flex-1 flex flex-col gap-1">
          <p className="font-body text-[13px] font-semibold text-ink">Ваш план</p>
          <p className="font-body text-[12px] text-muted leading-relaxed">
            ИИ анализирует планировку и строит реалистичную 3D-визуализацию с мебелью из каталога Hoff
          </p>
        </div>
        {state.status === 'idle' && (
          <button onClick={generate} className="btn-primary py-2.5 px-5 text-[13px] flex items-center gap-2 flex-shrink-0">
            <Building2 size={14} /> Построить 3D
          </button>
        )}
        {(state.status === 'uploading' || state.status === 'generating') && (
          <div className="flex items-center gap-2 flex-shrink-0 px-4 py-2.5 rounded-xl bg-terracotta-50 border border-terracotta/20">
            <Loader2 size={14} className="text-terracotta animate-spin" />
            <span className="font-body text-[13px] text-terracotta">
              {state.status === 'uploading' ? 'Загружаем план…' : 'Строим 3D вид…'}
            </span>
          </div>
        )}
        {state.status === 'done' && (
          <button onClick={generate} className="flex items-center gap-2 px-4 py-2.5 rounded-xl border border-border bg-white font-body text-[13px] text-muted hover:border-terracotta hover:text-terracotta transition-colors flex-shrink-0">
            <RotateCcw size={13} /> Перегенерировать
          </button>
        )}
      </div>

      {/* Результат */}
      {(state.status === 'uploading' || state.status === 'generating') && (
        <div className="relative w-full rounded-2xl overflow-hidden border border-border bg-cream" style={{ aspectRatio: '1/1' }}>
          {/* Animated background */}
          <div className="absolute inset-0 bg-gradient-to-br from-cream via-[#E8D4C4] to-[#DCC8B4] animate-pulse" />
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-4">
            <div className="w-16 h-16 rounded-2xl bg-white/70 backdrop-blur-sm flex items-center justify-center shadow-sm">
              <Building2 size={28} className="text-terracotta animate-pulse" />
            </div>
            <div className="text-center">
              <p className="font-heading text-[20px] text-ink/80">
                {state.status === 'uploading' ? 'Загружаем план…' : 'Строим 3D-визуализацию…'}
              </p>
              <p className="font-body text-[13px] text-muted mt-1">
                {state.status === 'generating' ? 'обычно 15–30 секунд' : ''}
              </p>
            </div>
            <div className="flex gap-2">
              {[0, 1, 2, 3, 4].map(i => (
                <div
                  key={i}
                  className="w-2 h-2 rounded-full bg-terracotta animate-bounce"
                  style={{ animationDelay: `${i * 150}ms` }}
                />
              ))}
            </div>
          </div>
        </div>
      )}

      {state.status === 'done' && state.imageUrl && (
        <>
          <div
            className="relative w-full rounded-2xl overflow-hidden border border-border shadow-md cursor-zoom-in"
            style={{ aspectRatio: '1/1' }}
            onClick={() => setZoomed(true)}
          >
            <Image
              src={state.imageUrl}
              alt="3D визуализация квартиры"
              fill
              className="object-cover"
              unoptimized
            />
            <div className="absolute bottom-3 right-3 flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-black/30 backdrop-blur-sm">
              <ZoomIn size={12} className="text-white" />
              <span className="font-body text-[11px] text-white">Увеличить</span>
            </div>
            <div className="absolute top-3 left-3 flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-black/25 backdrop-blur-sm">
              <Sparkles size={11} className="text-white" />
              <span className="font-body text-[11px] text-white">AI 3D · Hoff</span>
            </div>
          </div>

          {/* Инфо */}
          <div className="flex items-start gap-2 px-4 py-3 bg-terracotta-50 rounded-xl">
            <Sparkles size={14} className="text-terracotta flex-shrink-0 mt-0.5" />
            <p className="font-body text-[12px] text-[#7A4033]">
              ИИ построил 3D-визуализацию вашей квартиры на основе загруженного плана
              с мебелью из каталога Hoff. Нажмите «Перегенерировать» для нового варианта.
            </p>
          </div>

          {/* Zoom modal */}
          {zoomed && (
            <div className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center p-4" onClick={() => setZoomed(false)}>
              <button onClick={() => setZoomed(false)} className="absolute top-4 right-4 w-10 h-10 rounded-full bg-white/10 flex items-center justify-center hover:bg-white/20">
                <X size={18} className="text-white" />
              </button>
              <div className="max-w-3xl max-h-[90vh] w-full aspect-square" onClick={e => e.stopPropagation()}>
                <Image src={state.imageUrl} alt="3D план" fill className="object-contain rounded-2xl" unoptimized />
              </div>
            </div>
          )}
        </>
      )}

      {state.status === 'error' && (
        <div className="flex flex-col items-center justify-center gap-4 py-16 bg-white rounded-2xl border border-border">
          <AlertCircle size={32} className="text-terracotta/60" />
          <div className="text-center">
            <p className="font-body text-[14px] font-medium text-ink">Ошибка генерации</p>
            <p className="font-body text-[12px] text-muted mt-1 max-w-xs">{state.error}</p>
          </div>
          <button onClick={generate} className="btn-primary py-2.5 px-6 text-[14px] flex items-center gap-2">
            <RotateCcw size={14} /> Попробовать снова
          </button>
        </div>
      )}
    </div>
  )
}

// ─── Room Photo Card ──────────────────────────────────────────────────────────

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
        <div className="relative bg-cream overflow-hidden" style={{ aspectRatio: '16/9' }}>
          {room.status === 'done' && room.imageUrl ? (
            <>
              <Image src={room.imageUrl} alt={room.label} fill className="object-cover" sizes="(max-width: 768px) 100vw, 50vw" unoptimized />
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
              <div className="absolute inset-0 bg-gradient-to-br from-cream via-[#E8D8C8] to-[#D8C8B8] animate-pulse" />
              <div className="relative flex flex-col items-center gap-3">
                <div className="w-12 h-12 rounded-2xl bg-white/60 backdrop-blur-sm flex items-center justify-center">
                  <Sparkles size={22} className="text-terracotta animate-pulse" />
                </div>
                <p className="font-body text-[13px] font-medium text-ink/70">AI рисует интерьер…</p>
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
                <p className="font-body text-[13px] font-medium text-ink">Ошибка</p>
                <p className="font-body text-[11px] text-muted mt-0.5 line-clamp-2">{room.error}</p>
              </div>
              <button onClick={() => onGenerate(room.id)} className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-white border border-border font-body text-[13px] text-ink hover:border-terracotta hover:text-terracotta transition-colors">
                <RotateCcw size={13} /> Попробовать снова
              </button>
            </div>
          ) : (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-4">
              <div className="w-14 h-14 rounded-2xl bg-white/80 border border-border flex items-center justify-center shadow-sm">
                <Sparkles size={24} className="text-terracotta/60" />
              </div>
              <button onClick={() => onGenerate(room.id)} className="btn-primary py-2.5 px-5 text-[13px] flex items-center gap-2 shadow-md">
                <Sparkles size={14} /> Сгенерировать
              </button>
            </div>
          )}
        </div>

        <div className="px-4 py-3 flex items-center justify-between">
          <div>
            <p className="font-body text-[13px] font-semibold text-ink">{room.label}</p>
            <p className="font-body text-[11px] text-muted">
              {DEFAULT_FURNITURE[room.id].slice(0, 2).map(f => f.name.split(' ').slice(0, 2).join(' ')).join(', ')}
            </p>
          </div>
          <span className={`font-body text-[11px] px-2.5 py-1 rounded-full flex-shrink-0 ${
            room.status === 'done'    ? 'bg-sage-50 text-sage-dark' :
            room.status === 'loading' ? 'bg-terracotta-100 text-terracotta' :
            room.status === 'error'   ? 'bg-red-50 text-red-500' :
            'bg-border text-muted'
          }`}>
            {room.status === 'done' ? '✓ Готово' : room.status === 'loading' ? 'Генерируется…' : room.status === 'error' ? 'Ошибка' : 'Ожидание'}
          </span>
        </div>
      </div>

      {zoomed && room.imageUrl && (
        <div className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center p-4" onClick={() => setZoomed(false)}>
          <button onClick={() => setZoomed(false)} className="absolute top-4 right-4 w-10 h-10 rounded-full bg-white/10 flex items-center justify-center hover:bg-white/20">
            <X size={18} className="text-white" />
          </button>
          <div className="max-w-5xl max-h-[90vh] w-full" onClick={e => e.stopPropagation()}>
            <p className="font-heading text-[22px] text-white mb-3">{room.label}</p>
            <div className="relative rounded-2xl overflow-hidden" style={{ aspectRatio: '16/9' }}>
              <Image src={room.imageUrl} alt={room.label} fill className="object-cover" unoptimized />
            </div>
          </div>
        </div>
      )}
    </>
  )
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function VisualizationPage() {
  const router = useRouter()
  const { planUrl, planFile } = usePlanStore()
  const [mainTab, setMainTab] = useState<MainTab>('3d')
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
        body: JSON.stringify({ room: roomId, style: currentStyle, furniture: DEFAULT_FURNITURE[roomId] }),
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

  // Авто-генерируем первые 2 комнаты при переходе на вкладку фото
  const photoTabInitialized = useState(false)
  const handlePhotoTab = () => {
    setMainTab('photo')
    if (!photoTabInitialized[0]) {
      photoTabInitialized[1](true)
      generateRoom('living')
      setTimeout(() => generateRoom('bedroom'), 800)
    }
  }

  const anyLoading = rooms.some(r => r.status === 'loading')

  const generateAll = () => {
    ROOMS.forEach((r, i) => setTimeout(() => generateRoom(r.id), i * 600))
  }

  return (
    <div className="min-h-screen bg-paper flex flex-col">
      <StepHeader current={2} backHref="/preferences" backLabel="Назад к предпочтениям" />

      <main className="flex-1 flex flex-col px-6 md:px-10 py-8 gap-6 max-w-[1100px] w-full mx-auto">

        {/* Title */}
        <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
          <div>
            <h1 className="font-heading text-[38px] font-semibold text-ink leading-tight">Ваша квартира</h1>
            <p className="font-body text-[15px] text-muted mt-1">Скандинавский стиль · товары из каталога Hoff</p>
          </div>
          {mainTab === 'photo' && (
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
          )}
        </div>

        {/* Tabs */}
        <div className="flex gap-1 p-1 bg-white rounded-xl border border-border w-fit">
          <button
            onClick={() => setMainTab('3d')}
            className={`px-5 py-2 rounded-lg font-body text-[14px] font-medium transition-all flex items-center gap-2
              ${mainTab === '3d' ? 'bg-terracotta text-white shadow-sm' : 'text-muted hover:text-ink'}`}
          >
            <Building2 size={15} /> 3D план
          </button>
          <button
            onClick={handlePhotoTab}
            className={`px-5 py-2 rounded-lg font-body text-[14px] font-medium transition-all flex items-center gap-2
              ${mainTab === 'photo' ? 'bg-terracotta text-white shadow-sm' : 'text-muted hover:text-ink'}`}
          >
            <Camera size={15} /> Фото комнат
          </button>
        </div>

        {/* ── 3D план ── */}
        {mainTab === '3d' && (
          <FloorplanView planUrl={planUrl} planFile={planFile} style={currentStyle} />
        )}

        {/* ── Фото комнат ── */}
        {mainTab === 'photo' && (
          <div className="flex flex-col gap-4">
            <p className="font-body text-[14px] text-muted">
              AI генерирует реалистичные фото каждой комнаты с реальными товарами из каталога Hoff
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {rooms.map(room => (
                <RoomPhotoCard key={room.id} room={room} style={currentStyle} onGenerate={generateRoom} />
              ))}
            </div>
            <div className="flex items-start gap-2 px-4 py-3 bg-terracotta-50 rounded-xl">
              <Sparkles size={14} className="text-terracotta flex-shrink-0 mt-0.5" />
              <p className="font-body text-[12px] text-[#7A4033]">
                Визуализации генерируются через fal.ai (FLUX). Мебель — из реального каталога Hoff.
              </p>
            </div>
          </div>
        )}

        {/* CTA */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pt-4 border-t border-border">
          <div>
            <p className="font-body text-[14px] font-medium text-ink">Нравится планировка?</p>
            <p className="font-body text-[13px] text-muted">Перейдите к выбору реальных товаров из каталога</p>
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
