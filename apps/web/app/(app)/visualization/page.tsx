'use client'

import { useEffect, useCallback, useState } from 'react'
import { useRouter } from 'next/navigation'
import Image from 'next/image'
import {
  ArrowRight, Loader2, ZoomIn, X,
  Sparkles, AlertCircle, RotateCcw, Upload,
  Building2, Camera,
} from 'lucide-react'
import StepHeader from '@/components/StepHeader'
import { usePlanStore } from '@/store/planStore'
import { useVisualizationStore } from '@/store/visualizationStore'
import { DEFAULT_FURNITURE, type RoomType, type StyleType } from '@/lib/promptBuilder'

// ─── Types ────────────────────────────────────────────────────────────────────

type MainTab = '3d' | 'photo'

const ROOMS: { id: RoomType; label: string }[] = [
  { id: 'living',  label: 'Гостиная'      },
  { id: 'bedroom', label: 'Спальня'        },
  { id: 'kitchen', label: 'Кухня-столовая' },
  { id: 'kids',    label: 'Детская'        },
]

// ─── 3D Floor Plan View ───────────────────────────────────────────────────────

function FloorplanView({ onRegenerate }: { onRegenerate: () => void }) {
  const { planUrl } = usePlanStore()
  const floorplan = useVisualizationStore(s => s.floorplan)
  const [zoomed, setZoomed] = useState(false)

  if (!planUrl) {
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
      {/* Статус-бар сверху */}
      <div className="flex items-center justify-between gap-4 p-4 bg-white rounded-2xl border border-border">
        <div className="flex items-center gap-3">
          <div className="relative w-16 h-12 rounded-xl overflow-hidden flex-shrink-0 border border-border">
            <img src={planUrl} alt="Ваш план" className="w-full h-full object-cover" />
          </div>
          <div>
            <p className="font-body text-[13px] font-semibold text-ink">3D-визуализация вашего плана</p>
            <p className="font-body text-[12px] text-muted">
              {floorplan.status === 'done'
                ? 'Готово · мебель из каталога Hoff'
                : floorplan.status === 'uploading'
                ? 'Загружаем план…'
                : floorplan.status === 'generating'
                ? 'Строим 3D-вид…'
                : floorplan.status === 'error'
                ? 'Ошибка генерации'
                : 'Генерируется…'}
            </p>
          </div>
        </div>

        {(floorplan.status === 'uploading' || floorplan.status === 'generating') && (
          <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-terracotta-50 border border-terracotta/20">
            <Loader2 size={14} className="text-terracotta animate-spin" />
            <span className="font-body text-[12px] text-terracotta">
              {floorplan.status === 'uploading' ? 'Загружаем…' : 'Строим…'}
            </span>
          </div>
        )}

        {(floorplan.status === 'done' || floorplan.status === 'error') && (
          <button
            onClick={onRegenerate}
            className="flex items-center gap-2 px-4 py-2 rounded-xl border border-border bg-white font-body text-[13px] text-muted hover:border-terracotta hover:text-terracotta transition-colors flex-shrink-0"
          >
            <RotateCcw size={13} /> Перегенерировать
          </button>
        )}
      </div>

      {/* Генерируется */}
      {(floorplan.status === 'uploading' || floorplan.status === 'generating' || floorplan.status === 'idle') && (
        <div className="relative w-full rounded-2xl overflow-hidden border border-border bg-cream" style={{ aspectRatio: '1/1' }}>
          <div className="absolute inset-0 bg-gradient-to-br from-cream via-[#E8D4C4] to-[#DCC8B4] animate-pulse" />
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-4">
            <div className="w-16 h-16 rounded-2xl bg-white/70 backdrop-blur-sm flex items-center justify-center shadow-sm">
              <Building2 size={28} className="text-terracotta animate-pulse" />
            </div>
            <div className="text-center">
              <p className="font-heading text-[20px] text-ink/80">
                {floorplan.status === 'uploading' ? 'Загружаем план…' : 'Строим 3D-визуализацию…'}
              </p>
              <p className="font-body text-[13px] text-muted mt-1">обычно 15–30 секунд</p>
            </div>
            <div className="flex gap-2">
              {[0,1,2,3,4].map(i => (
                <div key={i} className="w-2 h-2 rounded-full bg-terracotta animate-bounce" style={{ animationDelay: `${i * 150}ms` }} />
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Готово */}
      {floorplan.status === 'done' && floorplan.imageUrl && (
        <>
          <div
            className="relative w-full rounded-2xl overflow-hidden border border-border shadow-md cursor-zoom-in"
            style={{ aspectRatio: '1/1' }}
            onClick={() => setZoomed(true)}
          >
            <Image src={floorplan.imageUrl} alt="3D визуализация" fill className="object-cover" unoptimized />
            <div className="absolute bottom-3 right-3 flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-black/30 backdrop-blur-sm">
              <ZoomIn size={12} className="text-white" />
              <span className="font-body text-[11px] text-white">Увеличить</span>
            </div>
            <div className="absolute top-3 left-3 flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-black/25 backdrop-blur-sm">
              <Sparkles size={11} className="text-white" />
              <span className="font-body text-[11px] text-white">AI 3D · Hoff</span>
            </div>
          </div>
          <div className="flex items-start gap-2 px-4 py-3 bg-terracotta-50 rounded-xl">
            <Sparkles size={14} className="text-terracotta flex-shrink-0 mt-0.5" />
            <p className="font-body text-[12px] text-[#7A4033]">
              ИИ построил 3D-визуализацию по вашему плану с мебелью из каталога Hoff.
              Нажмите «Перегенерировать» для нового варианта.
            </p>
          </div>
          {zoomed && (
            <div className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center p-4" onClick={() => setZoomed(false)}>
              <button onClick={() => setZoomed(false)} className="absolute top-4 right-4 w-10 h-10 rounded-full bg-white/10 flex items-center justify-center hover:bg-white/20">
                <X size={18} className="text-white" />
              </button>
              <div className="relative max-w-3xl max-h-[90vh] w-full aspect-square" onClick={e => e.stopPropagation()}>
                <Image src={floorplan.imageUrl} alt="3D план" fill className="object-contain rounded-2xl" unoptimized />
              </div>
            </div>
          )}
        </>
      )}

      {/* Ошибка */}
      {floorplan.status === 'error' && (
        <div className="flex flex-col items-center justify-center gap-4 py-16 bg-white rounded-2xl border border-border">
          <AlertCircle size={32} className="text-terracotta/60" />
          <div className="text-center">
            <p className="font-body text-[14px] font-medium text-ink">Ошибка генерации</p>
            <p className="font-body text-[12px] text-muted mt-1 max-w-xs">{floorplan.error}</p>
          </div>
          <button onClick={onRegenerate} className="btn-primary py-2.5 px-6 text-[14px] flex items-center gap-2">
            <RotateCcw size={14} /> Попробовать снова
          </button>
        </div>
      )}
    </div>
  )
}

// ─── Room Photo Card ──────────────────────────────────────────────────────────

function RoomPhotoCard({
  roomId,
  onRegenerate,
}: {
  roomId: RoomType
  onRegenerate: (id: RoomType) => void
}) {
  const room = useVisualizationStore(s => s.rooms.find(r => r.id === roomId)!)
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
                  <button onClick={() => onRegenerate(room.id)} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/20 backdrop-blur-sm font-body text-[12px] text-white hover:bg-white/30 transition-colors">
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
                  {[0,1,2,3].map(i => (
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
              <button onClick={() => onRegenerate(room.id)} className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-white border border-border font-body text-[13px] text-ink hover:border-terracotta hover:text-terracotta transition-colors">
                <RotateCcw size={13} /> Попробовать снова
              </button>
            </div>
          ) : (
            /* idle — не показываем кнопку, генерируется автоматически */
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-3">
              <div className="absolute inset-0 bg-gradient-to-br from-cream via-[#E8D8C8] to-[#D8C8B8] animate-pulse opacity-50" />
              <div className="relative">
                <Sparkles size={24} className="text-terracotta/40" />
              </div>
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
  const { planUrl, planFile, planFalUrl, setPlanFalUrl } = usePlanStore()
  const { floorplan, rooms, setFloorplan, setRoom } = useVisualizationStore()
  const [mainTab, setMainTab] = useState<MainTab>('3d')
  const [currentStyle] = useState<StyleType>('scandi')

  // ── Генерация 3D флорплана ────────────────────────────────────────────────

  const generateFloorplan = useCallback(async () => {
    setFloorplan({ imageUrl: null, status: 'uploading', error: undefined })
    try {
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

      setFloorplan({ status: 'generating' })
      const res = await fetch('/api/floorplan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ planUrl: falUrl, style: currentStyle }),
      })
      const data = await res.json()
      if (!res.ok || data.error) throw new Error(data.error ?? 'Ошибка генерации')
      setFloorplan({ imageUrl: data.imageUrl, status: 'done' })
    } catch (err: any) {
      setFloorplan({ imageUrl: null, status: 'error', error: err?.message ?? 'Ошибка' })
    }
  }, [planFile, planFalUrl, currentStyle, setFloorplan, setPlanFalUrl])

  // ── Генерация фото комнаты ────────────────────────────────────────────────

  const generateRoom = useCallback(async (roomId: RoomType) => {
    setRoom(roomId, { status: 'loading', error: undefined })
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
        setRoom(roomId, { status: 'error', error: msg })
        return
      }
      setRoom(roomId, { status: 'done', imageUrl: data.imageUrl })
    } catch (err: any) {
      setRoom(roomId, { status: 'error', error: err?.message ?? 'Ошибка сети' })
    }
  }, [currentStyle, setRoom])

  // ── Авто-генерация при входе ──────────────────────────────────────────────
  // Запускаем только если ещё не сгенерировано (store пустой)

  useEffect(() => {
    if (!planFile && !planFalUrl) return // нет плана — ничего не делаем

    // 3D флорплан
    if (floorplan.status === 'idle') {
      generateFloorplan()
    }

    // Фото комнат — стартуем с задержкой, чтобы не перегружать fal.ai
    rooms.forEach((room, i) => {
      if (room.status === 'idle') {
        setTimeout(() => generateRoom(room.id), i * 700)
      }
    })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []) // только при маунте — store уже содержит актуальное состояние

  const anyPhotoLoading = rooms.some(r => r.status === 'loading')

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
          {mainTab === 'photo' && anyPhotoLoading && (
            <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-terracotta-50 border border-terracotta/20">
              <Loader2 size={14} className="text-terracotta animate-spin" />
              <span className="font-body text-[13px] text-terracotta">Генерируется…</span>
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
            onClick={() => setMainTab('photo')}
            className={`px-5 py-2 rounded-lg font-body text-[14px] font-medium transition-all flex items-center gap-2
              ${mainTab === 'photo' ? 'bg-terracotta text-white shadow-sm' : 'text-muted hover:text-ink'}`}
          >
            <Camera size={15} /> Фото комнат
          </button>
        </div>

        {/* Вкладки — всегда в DOM, CSS скрытие → стейт не теряется при переключении */}

        <div style={{ display: mainTab === '3d' ? 'flex' : 'none' }} className="flex-col gap-5">
          <FloorplanView onRegenerate={generateFloorplan} />
        </div>

        <div style={{ display: mainTab === 'photo' ? 'flex' : 'none' }} className="flex-col gap-4">
          <p className="font-body text-[14px] text-muted">
            AI генерирует реалистичные фото каждой комнаты с реальными товарами из каталога Hoff
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {ROOMS.map(r => (
              <RoomPhotoCard key={r.id} roomId={r.id} onRegenerate={generateRoom} />
            ))}
          </div>
          <div className="flex items-start gap-2 px-4 py-3 bg-terracotta-50 rounded-xl">
            <Sparkles size={14} className="text-terracotta flex-shrink-0 mt-0.5" />
            <p className="font-body text-[12px] text-[#7A4033]">
              Визуализации генерируются через fal.ai (FLUX). Мебель — из реального каталога Hoff.
            </p>
          </div>
        </div>

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
