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

// ─── Планировка квартиры с реальными товарами Hoff ───────────────────────────

interface FurniturePart { x: number; y: number; w: number; h: number; rx?: number }
interface PlanItem {
  id: string
  hoffName: string    // полное название товара Hoff
  label: string       // короткое для SVG
  color: string
  opacity: number
  parts: FurniturePart[]
}
interface PlanRoom {
  id: string; label: string; accentColor: string
  labelX: number; labelY: number
  zone: { x: number; y: number; w: number; h: number }
  items: PlanItem[]
}

// Масштаб: 1 SVG-юнит ≈ 10 см. Квартира ~10м × 10м = 100×100 юнитов.
const PLAN_ROOMS: PlanRoom[] = [
  // ── ГОСТИНАЯ (top-left, 6.2 × 4.8 м) ─────────────────────────────────────
  {
    id: 'living', label: 'Гостиная', accentColor: '#D4795C',
    labelX: 35, labelY: 28,
    zone: { x: 1, y: 1, w: 62, h: 48 },
    items: [
      // Угловой диван Мэдисон (250×90 + 90×95 см) — Г-образно в левом верхнем углу
      {
        id: 'sofa', hoffName: 'Угловой диван-кровать SOLANA Мэдисон', label: 'Диван Мэдисон',
        color: '#D4795C', opacity: 0.65,
        parts: [
          { x: 3, y: 2, w: 26, h: 9, rx: 1.5 },   // горизонтальная часть (250 см)
          { x: 3, y: 2, w: 9, h: 19, rx: 1.5 },    // вертикальная (90 см) — Г-образно
        ],
      },
      // Кресло Скотт (80×80 см)
      {
        id: 'armchair', hoffName: 'Кресло SCANDICA Скотт', label: 'Кресло Скотт',
        color: '#D4795C', opacity: 0.52,
        parts: [{ x: 34, y: 2, w: 9, h: 9, rx: 2 }],
      },
      // Столик кофейный (120×60 см) перед диваном
      {
        id: 'coffee', hoffName: 'Столик кофейный', label: 'Столик',
        color: '#A08060', opacity: 0.58,
        parts: [{ x: 14, y: 23, w: 14, h: 7, rx: 1 }],
      },
      // ТВ-зона / Шкаф-витрина Эванс (180×40 см) у дальней стены
      {
        id: 'tv', hoffName: 'Шкаф-витрина с 3 ящиками Эванс', label: 'ТВ-зона · Шкаф Эванс',
        color: '#7A8F7A', opacity: 0.58,
        parts: [{ x: 16, y: 44, w: 20, h: 4, rx: 0.5 }],
      },
      // Ковёр Гиссар 200×300 см — зона под диваном и столиком
      {
        id: 'rug', hoffName: 'Ковёр Гиссар 200×300 см', label: 'Ковёр Гиссар',
        color: '#D4A080', opacity: 0.18,
        parts: [{ x: 5, y: 18, w: 30, h: 27, rx: 1 }],
      },
    ],
  },

  // ── СПАЛЬНЯ (top-right, 3.5 × 4.8 м) ─────────────────────────────────────
  {
    id: 'bedroom', label: 'Спальня', accentColor: '#7A8F7A',
    labelX: 83, labelY: 31,
    zone: { x: 65, y: 1, w: 34, h: 48 },
    items: [
      // Кровать двуспальная 160×200 см
      {
        id: 'bed', hoffName: 'Кровать двуспальная 160×200 см', label: 'Кровать 160×200',
        color: '#7A8F7A', opacity: 0.62,
        parts: [{ x: 68, y: 3, w: 16, h: 20, rx: 1.5 }],
      },
      // Тумбы прикроватные (45×40 см) × 2
      {
        id: 'ns_l', hoffName: 'Тумба прикроватная с ящиком', label: 'Тумба',
        color: '#A0B0A0', opacity: 0.68,
        parts: [{ x: 65, y: 6, w: 4, h: 8, rx: 0.5 }],
      },
      {
        id: 'ns_r', hoffName: 'Тумба прикроватная с ящиком', label: 'Тумба',
        color: '#A0B0A0', opacity: 0.68,
        parts: [{ x: 85, y: 6, w: 4, h: 8, rx: 0.5 }],
      },
      // Шкаф-купе 220×60 см у нижней стены
      {
        id: 'wardrobe', hoffName: 'Шкаф-купе 2-дверный 220 см', label: 'Шкаф-купе',
        color: '#7A8F7A', opacity: 0.55,
        parts: [{ x: 66, y: 43, w: 22, h: 5, rx: 0.5 }],
      },
      // Комод с ящиками 100×45 см
      {
        id: 'dresser', hoffName: 'Комод с ящиками', label: 'Комод',
        color: '#A0B0A0', opacity: 0.62,
        parts: [{ x: 89, y: 43, w: 9, h: 5, rx: 0.5 }],
      },
      // Кресло Норд (75×75 см) в углу
      {
        id: 'armchair_b', hoffName: 'Кресло для отдыха SCANDICA Норд', label: 'Кресло Норд',
        color: '#7A8F7A', opacity: 0.50,
        parts: [{ x: 90, y: 2, w: 8, h: 8, rx: 2 }],
      },
      // Ковёр Шегги 160×230 под кроватью
      {
        id: 'rug_b', hoffName: 'Ковёр Шегги 160×230 см', label: 'Ковёр',
        color: '#8FA89F', opacity: 0.16,
        parts: [{ x: 66, y: 2, w: 17, h: 25, rx: 1 }],
      },
    ],
  },

  // ── КУХНЯ-СТОЛОВАЯ (bottom-left, 3.1 × 4.8 м) ────────────────────────────
  {
    id: 'kitchen', label: 'Кухня-столовая', accentColor: '#C8B4A0',
    labelX: 16, labelY: 77,
    zone: { x: 1, y: 51, w: 31, h: 48 },
    items: [
      // Кухонный гарнитур Г-образный
      {
        id: 'kitchen_h', hoffName: 'Кухонный гарнитур', label: 'Кухня',
        color: '#B09880', opacity: 0.60,
        parts: [
          { x: 2, y: 52, w: 29, h: 5, rx: 0.5 },  // вдоль верхней стены
          { x: 27, y: 52, w: 4, h: 18, rx: 0.5 }, // вдоль правой стены
        ],
      },
      // Обеденный стол (90×80 см)
      {
        id: 'dining', hoffName: 'Стол обеденный 90×80 см', label: 'Стол',
        color: '#C8B4A0', opacity: 0.65,
        parts: [{ x: 6, y: 77, w: 10, h: 8, rx: 1 }],
      },
      // 4 стула вокруг стола
      { id: 'ch1', hoffName: 'Стул', label: '', color: '#C8B4A0', opacity: 0.55, parts: [{ x: 3, y: 79, w: 3.5, h: 5, rx: 1 }] },
      { id: 'ch2', hoffName: 'Стул', label: '', color: '#C8B4A0', opacity: 0.55, parts: [{ x: 17, y: 79, w: 3.5, h: 5, rx: 1 }] },
      { id: 'ch3', hoffName: 'Стул', label: '', color: '#C8B4A0', opacity: 0.55, parts: [{ x: 9,  y: 74, w: 5, h: 4, rx: 1 }] },
      { id: 'ch4', hoffName: 'Стул', label: '', color: '#C8B4A0', opacity: 0.55, parts: [{ x: 9,  y: 86, w: 5, h: 4, rx: 1 }] },
      // Пуф-банкетка (60×40 см)
      {
        id: 'puf', hoffName: 'Пуф-банкетка', label: 'Пуф',
        color: '#D4795C', opacity: 0.45,
        parts: [{ x: 19, y: 88, w: 8, h: 5, rx: 1.5 }],
      },
    ],
  },

  // ── ДЕТСКАЯ (bottom-right, 6.6 × 4.8 м) ──────────────────────────────────
  {
    id: 'kids', label: 'Детская', accentColor: '#8FA0C0',
    labelX: 66, labelY: 78,
    zone: { x: 34, y: 51, w: 65, h: 48 },
    items: [
      // Кровать детская 90×190 см
      {
        id: 'kids_bed', hoffName: 'Кровать детская 90×190 см', label: 'Кровать',
        color: '#8FA0C0', opacity: 0.62,
        parts: [{ x: 36, y: 53, w: 9, h: 19, rx: 1.5 }],
      },
      // Диван Норман (для игровой зоны, 170×90 см)
      {
        id: 'kids_sofa', hoffName: 'Диван-кровать Атланта', label: 'Диван',
        color: '#8FA0C0', opacity: 0.50,
        parts: [{ x: 67, y: 53, w: 17, h: 9, rx: 1.5 }],
      },
      // Письменный стол 120×60 см
      {
        id: 'desk', hoffName: 'Стол письменный 120×60 см', label: 'Стол',
        color: '#A0B0C0', opacity: 0.62,
        parts: [{ x: 47, y: 55, w: 12, h: 6, rx: 0.5 }],
      },
      // Кресло Gap (груша) у стола
      {
        id: 'gap', hoffName: 'Кресло Gap', label: 'Кресло Gap',
        color: '#8FA0C0', opacity: 0.55,
        parts: [{ x: 49, y: 62, w: 7, h: 7, rx: 3.5 }],
      },
      // Комод с ящиками 100×45 см
      {
        id: 'kids_dresser', hoffName: 'Комод с ящиками детский', label: 'Комод',
        color: '#A0B0C0', opacity: 0.62,
        parts: [{ x: 36, y: 82, w: 10, h: 5, rx: 0.5 }],
      },
      // Пуф мягкий
      {
        id: 'kids_puf', hoffName: 'Пуф мягкий круглый', label: 'Пуф',
        color: '#D4795C', opacity: 0.42,
        parts: [{ x: 87, y: 52, w: 7, h: 6, rx: 2 }],
      },
      // Ковёр Шегги 160×230 см — игровая зона
      {
        id: 'kids_rug', hoffName: 'Ковёр Шегги 160×230 см', label: 'Ковёр',
        color: '#8FA0C0', opacity: 0.16,
        parts: [{ x: 60, y: 65, w: 22, h: 27, rx: 1 }],
      },
    ],
  },
]

// ─── SVG Overlay компонент ────────────────────────────────────────────────────

function PlanOverlay() {
  return (
    <svg
      className="absolute inset-0 w-full h-full pointer-events-none"
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
    >
      <defs>
        <filter id="fs">
          <feDropShadow dx="0.2" dy="0.3" stdDeviation="0.6" floodOpacity="0.28" />
        </filter>
      </defs>

      {/* Фоновая подсветка зон комнат */}
      {PLAN_ROOMS.map(room => (
        <rect
          key={`zone-${room.id}`}
          x={room.zone.x} y={room.zone.y}
          width={room.zone.w} height={room.zone.h}
          fill={room.accentColor} opacity={0.07} rx={0.5}
        />
      ))}

      {/* Внутренние стены (разделители комнат) */}
      <line x1="64" y1="1" x2="64" y2="99" stroke="#1C1917" strokeWidth="1" opacity={0.30} />
      <line x1="1"  y1="50" x2="63" y2="50" stroke="#1C1917" strokeWidth="1" opacity={0.30} />
      <line x1="33" y1="50" x2="33" y2="99" stroke="#1C1917" strokeWidth="0.7" opacity={0.22} />

      {/* Мебель по комнатам */}
      {PLAN_ROOMS.flatMap(room =>
        room.items.flatMap(item =>
          item.parts.map((part, pi) => {
            const showLabel = pi === 0 && item.label && part.w > 7 && part.h > 5
            return (
              <g key={`${item.id}-${pi}`}>
                <rect
                  x={part.x} y={part.y} width={part.w} height={part.h}
                  rx={part.rx ?? 0.5}
                  fill={item.color} opacity={item.opacity}
                  filter="url(#fs)"
                />
                {/* Блик сверху */}
                <rect
                  x={part.x + 0.3} y={part.y + 0.3}
                  width={part.w - 0.6} height={Math.min(part.h * 0.22, 1.4)}
                  rx={part.rx ?? 0.5}
                  fill="white" opacity={0.20}
                />
                {/* Подпись */}
                {showLabel && (
                  <text
                    x={part.x + part.w / 2}
                    y={part.y + part.h / 2 + 0.7}
                    textAnchor="middle"
                    fontSize="1.8"
                    fontFamily="Onest, sans-serif"
                    fill="white"
                    fontWeight="700"
                    opacity={0.92}
                  >
                    {item.label.length > 15 ? item.label.slice(0, 14) + '…' : item.label}
                  </text>
                )}
              </g>
            )
          })
        )
      )}

      {/* Названия комнат */}
      {PLAN_ROOMS.map(room => (
        <text
          key={`room-label-${room.id}`}
          x={room.labelX} y={room.labelY}
          textAnchor="middle"
          fontSize="2.8"
          fontFamily="Onest, sans-serif"
          fill={room.accentColor}
          fontWeight="800"
          opacity={0.65}
        >
          {room.label}
        </text>
      ))}
    </svg>
  )
}

// ─── Plan view ────────────────────────────────────────────────────────────────

function PlanView({ planUrl, mode }: { planUrl: string; mode: PlanMode }) {
  const [zoomed, setZoomed] = useState(false)

  return (
    <>
      {/* Изображение + оверлей */}
      <div
        className="relative w-full rounded-2xl overflow-hidden border border-border shadow-sm bg-white cursor-zoom-in"
        onClick={() => setZoomed(true)}
      >
        <img
          src={planUrl} alt="План"
          className="w-full h-auto block"
          style={{ filter: mode === 'furniture' ? 'brightness(0.88) contrast(1.10)' : 'none' }}
          draggable={false}
        />
        {mode === 'furniture' && <PlanOverlay />}
        <div className="absolute bottom-3 right-3 flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-black/30 backdrop-blur-sm">
          <ZoomIn size={12} className="text-white" />
          <span className="font-body text-[11px] text-white">Увеличить</span>
        </div>
      </div>

      {/* Легенда комнат + список мебели */}
      {mode === 'furniture' && (
        <>
          {/* Цветовая легенда по комнатам */}
          <div className="flex flex-wrap gap-3 mt-1">
            {PLAN_ROOMS.map(room => (
              <div key={room.id} className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-sm flex-shrink-0" style={{ background: room.accentColor, opacity: 0.75 }} />
                <span className="font-body text-[12px] text-muted">{room.label}</span>
              </div>
            ))}
          </div>

          {/* Список мебели по комнатам */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-2">
            {PLAN_ROOMS.map(room => (
              <div key={room.id} className="bg-white rounded-xl border border-border p-3">
                <div className="flex items-center gap-2 mb-2">
                  <div className="w-2.5 h-2.5 rounded-sm flex-shrink-0" style={{ background: room.accentColor }} />
                  <span className="font-body text-[13px] font-semibold text-ink">{room.label}</span>
                </div>
                <div className="flex flex-col gap-1">
                  {room.items
                    .filter((item, idx, arr) => arr.findIndex(i => i.id === item.id) === idx) // дедупликация
                    .filter(item => item.label) // только именованные предметы
                    .map(item => (
                      <div key={item.id} className="flex items-start gap-2">
                        <div className="w-1.5 h-1.5 rounded-full flex-shrink-0 mt-1.5" style={{ background: item.color }} />
                        <span className="font-body text-[11px] text-muted leading-relaxed">{item.hoffName}</span>
                      </div>
                    ))
                  }
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {/* Зум-модал */}
      {zoomed && (
        <div className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4" onClick={() => setZoomed(false)}>
          <div className="relative max-w-5xl max-h-[90vh] w-full">
            <button onClick={() => setZoomed(false)} className="absolute -top-9 right-0 flex items-center gap-2 text-white/70 hover:text-white font-body text-[14px]">
              <X size={16} /> Закрыть
            </button>
            <div className="relative rounded-xl overflow-hidden">
              <img
                src={planUrl} alt="План"
                className="w-full h-auto max-h-[85vh] object-contain"
                draggable={false}
                style={{ filter: mode === 'furniture' ? 'brightness(0.88) contrast(1.10)' : 'none' }}
              />
              {mode === 'furniture' && <PlanOverlay />}
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
