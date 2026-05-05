'use client'

/**
 * Страница валидации геометрии.
 *
 * Пользователь видит:
 * - Исходный план квартиры
 * - Поверх него — распознанные стены, комнаты, двери, окна
 * - Confidence scores по каждой категории
 * - Список комнат с возможностью исправить тип и площадь
 * - Поле для ввода масштаба (если не распознан)
 * - Кнопка «Подтвердить геометрию» → переход к расстановке мебели
 *
 * Геометрия загружается из geometryStore (заполняется на /processing).
 */

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { CheckCircle2, AlertTriangle, Ruler, ChevronDown, ChevronUp, ArrowRight, RotateCcw } from 'lucide-react'
import StepHeader from '@/components/StepHeader'
import { GeometryOverlay } from '@/components/GeometryOverlay'
import { usePlanStore } from '@/store/planStore'
import {
  useGeometryStore,
  ROOM_LABEL_RU,
  type RoomLabel,
} from '@/store/geometryStore'

const ROOM_LABELS: RoomLabel[] = [
  'living_room', 'bedroom', 'kitchen', 'bathroom',
  'toilet', 'corridor', 'kids_room', 'balcony', 'storage', 'unknown',
]

function ConfidenceBadge({ value, label }: { value: number; label: string }) {
  const pct = Math.round(value * 100)
  const color = pct >= 70 ? 'bg-sage-50 text-sage-dark border-sage/30'
    : pct >= 45 ? 'bg-yellow-50 text-yellow-700 border-yellow-300'
    : 'bg-red-50 text-red-600 border-red-300'
  return (
    <div className={`flex items-center gap-2 px-3 py-2 rounded-xl border ${color}`}>
      <div className="w-2 h-2 rounded-full bg-current opacity-70" />
      <div>
        <p className="font-body text-[11px] font-semibold">{label}</p>
        <p className="font-body text-[13px]">{pct}%</p>
      </div>
    </div>
  )
}

export default function AnalysisPage() {
  const router = useRouter()
  const { planUrl } = usePlanStore()
  const {
    geometry, analysisStatus, analysisError, needsValidation,
    confirmGeometry, updateRoomLabel, updateRoomArea, updateScale,
    setAnalysisStatus,
  } = useGeometryStore()

  const [selectedRoomId, setSelectedRoomId] = useState<string | null>(null)
  const [scaleInput, setScaleInput] = useState('')
  const [showDebug, setShowDebug] = useState(false)
  const [confirmNotes, setConfirmNotes] = useState('')
  const [showLayers, setShowLayers] = useState({
    walls: true, rooms: true, doors: true, windows: true,
  })

  // Если нет плана — перенаправить
  if (!planUrl) {
    return (
      <div className="min-h-screen bg-paper flex items-center justify-center">
        <div className="text-center">
          <p className="font-body text-muted">План не загружен</p>
          <button onClick={() => router.push('/upload')} className="btn-primary mt-4 px-6 py-3">
            Загрузить план
          </button>
        </div>
      </div>
    )
  }

  if (analysisStatus === 'analyzing') {
    return (
      <div className="min-h-screen bg-paper flex flex-col">
        <StepHeader current={1} backHref="/upload" backLabel="Назад к плану" />
        <div className="flex-1 flex flex-col items-center justify-center gap-6">
          <div className="w-16 h-16 border-4 border-terracotta border-t-transparent rounded-full animate-spin" />
          <div className="text-center">
            <p className="font-heading text-[24px] font-semibold text-ink">Анализируем план…</p>
            <p className="font-body text-[14px] text-muted mt-2">Распознаём стены, комнаты, двери и окна</p>
          </div>
        </div>
      </div>
    )
  }

  if (analysisStatus === 'error' || !geometry) {
    return (
      <div className="min-h-screen bg-paper flex flex-col">
        <StepHeader current={1} backHref="/upload" backLabel="Назад к плану" />
        <div className="flex-1 flex flex-col items-center justify-center gap-6 px-6">
          <AlertTriangle size={48} className="text-terracotta" />
          <div className="text-center">
            <p className="font-heading text-[24px] font-semibold text-ink">Ошибка анализа</p>
            <p className="font-body text-[14px] text-muted mt-2 max-w-md">
              {analysisError || 'Не удалось распознать план. Попробуйте другое изображение.'}
            </p>
          </div>
          <button onClick={() => router.push('/upload')} className="btn-primary px-8 py-3 flex items-center gap-2">
            <RotateCcw size={16} /> Загрузить другой план
          </button>
        </div>
      </div>
    )
  }

  const { confidence, walls, rooms, openings, scale } = geometry
  const doors = openings.filter(o => o.type === 'door')
  const windows = openings.filter(o => o.type === 'window')
  const overallPct = Math.round(
    (confidence.wall_confidence + confidence.room_confidence +
     confidence.door_confidence + confidence.window_confidence +
     confidence.scale_confidence) / 5 * 100
  )

  const selectedRoom = selectedRoomId ? rooms.find(r => r.id === selectedRoomId) : null

  const handleConfirm = () => {
    confirmGeometry(confirmNotes)
    router.push('/processing')
  }

  const handleScaleInput = () => {
    const v = parseFloat(scaleInput)
    if (!isNaN(v) && v > 0) {
      updateScale(v)
    }
  }

  return (
    <div className="min-h-screen bg-paper flex flex-col">
      <StepHeader current={1} backHref="/preferences" backLabel="Назад к предпочтениям" />

      <main className="flex-1 flex flex-col lg:flex-row gap-6 px-6 py-8 max-w-[1200px] w-full mx-auto">

        {/* ── Левая колонка: оверлей ── */}
        <div className="flex-1 flex flex-col gap-4">
          <div>
            <h1 className="font-heading text-[32px] font-semibold text-ink leading-tight">
              Проверьте план квартиры
            </h1>
            <p className="font-body text-[14px] text-muted mt-1">
              ИИ распознал геометрию. Убедитесь, что всё правильно.
            </p>
          </div>

          {/* Предупреждение если нужна валидация */}
          {needsValidation && (
            <div className="flex items-start gap-3 px-4 py-3 bg-yellow-50 border border-yellow-200 rounded-xl">
              <AlertTriangle size={18} className="text-yellow-600 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-body text-[13px] font-semibold text-yellow-700">
                  Уверенность распознавания: {overallPct}%
                </p>
                <p className="font-body text-[12px] text-yellow-600 mt-0.5">
                  Пожалуйста, проверьте стены и комнаты перед продолжением
                </p>
              </div>
            </div>
          )}

          {/* Переключатели слоёв */}
          <div className="flex flex-wrap gap-2">
            {[
              { key: 'walls',   label: `Стены (${walls.length})`,    color: 'text-blue-600' },
              { key: 'rooms',   label: `Комнаты (${rooms.length})`,  color: 'text-green-600' },
              { key: 'doors',   label: `Двери (${doors.length})`,    color: 'text-orange-500' },
              { key: 'windows', label: `Окна (${windows.length})`,   color: 'text-sky-500' },
            ].map(({ key, label, color }) => (
              <button
                key={key}
                onClick={() => setShowLayers(l => ({ ...l, [key]: !l[key as keyof typeof l] }))}
                className={`font-body text-[12px] px-3 py-1.5 rounded-lg border transition-all ${
                  showLayers[key as keyof typeof showLayers]
                    ? `border-current ${color} bg-white`
                    : 'border-border text-muted bg-white'
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {/* Canvas оверлей */}
          <div className="relative rounded-2xl overflow-hidden border border-border bg-white">
            <GeometryOverlay
              planImageSrc={planUrl}
              geometry={geometry}
              showWalls={showLayers.walls}
              showRooms={showLayers.rooms}
              showDoors={showLayers.doors}
              showWindows={showLayers.windows}
              highlightRoomId={selectedRoomId}
              onRoomClick={setSelectedRoomId}
              className="w-full"
            />
          </div>

          {/* Масштаб */}
          <div className="flex items-center gap-3 p-4 bg-white rounded-2xl border border-border">
            <Ruler size={18} className="text-terracotta flex-shrink-0" />
            <div className="flex-1">
              <p className="font-body text-[13px] font-semibold text-ink">Масштаб</p>
              <p className="font-body text-[11px] text-muted">
                {scale.px_per_meter
                  ? `${scale.px_per_meter.toFixed(1)} px/м · источник: ${scale.source}`
                  : 'Не распознан автоматически'}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <input
                type="number"
                placeholder="px/м"
                value={scaleInput}
                onChange={e => setScaleInput(e.target.value)}
                className="w-20 px-2 py-1.5 text-[13px] font-body border border-border rounded-lg text-center"
              />
              <button
                onClick={handleScaleInput}
                className="px-3 py-1.5 rounded-lg bg-terracotta text-white font-body text-[12px] hover:bg-terracotta/90"
              >
                Применить
              </button>
            </div>
          </div>
        </div>

        {/* ── Правая колонка: комнаты + подтверждение ── */}
        <div className="w-full lg:w-[320px] flex flex-col gap-4">

          {/* Confidence scores */}
          <div className="bg-white rounded-2xl border border-border p-4 flex flex-col gap-3">
            <h2 className="font-heading text-[18px] font-semibold text-ink">Уверенность</h2>
            <div className="grid grid-cols-2 gap-2">
              <ConfidenceBadge value={confidence.wall_confidence}   label="Стены" />
              <ConfidenceBadge value={confidence.room_confidence}   label="Комнаты" />
              <ConfidenceBadge value={confidence.door_confidence}   label="Двери" />
              <ConfidenceBadge value={confidence.window_confidence} label="Окна" />
              <ConfidenceBadge value={confidence.scale_confidence}  label="Масштаб" />
            </div>
          </div>

          {/* Список комнат */}
          <div className="bg-white rounded-2xl border border-border overflow-hidden">
            <div className="px-4 py-3 border-b border-border">
              <h2 className="font-heading text-[18px] font-semibold text-ink">
                Комнаты ({rooms.length})
              </h2>
              <p className="font-body text-[12px] text-muted mt-0.5">
                Кликните на комнату на плане или выберите здесь
              </p>
            </div>
            <div className="divide-y divide-border max-h-[300px] overflow-y-auto">
              {rooms.map((room) => (
                <div
                  key={room.id}
                  className={`px-4 py-3 cursor-pointer transition-colors ${
                    selectedRoomId === room.id ? 'bg-terracotta-50' : 'hover:bg-paper'
                  }`}
                  onClick={() => setSelectedRoomId(room.id === selectedRoomId ? null : room.id)}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-body text-[13px] font-semibold text-ink">
                      {ROOM_LABEL_RU[room.label]}
                    </span>
                    <span className="font-body text-[12px] text-muted">
                      {room.area_m2 ? `${room.area_m2} м²` : '? м²'}
                    </span>
                  </div>
                  <p className="font-body text-[11px] text-muted mt-0.5">
                    conf: {Math.round(room.confidence * 100)}%
                  </p>
                </div>
              ))}
            </div>
          </div>

          {/* Редактирование выбранной комнаты */}
          {selectedRoom && (
            <div className="bg-terracotta-50 rounded-2xl border border-terracotta/20 p-4 flex flex-col gap-3">
              <h3 className="font-body text-[14px] font-semibold text-terracotta">
                Редактировать: {ROOM_LABEL_RU[selectedRoom.label]}
              </h3>
              <div className="flex flex-col gap-2">
                <label className="font-body text-[12px] text-ink">Тип комнаты</label>
                <select
                  value={selectedRoom.label}
                  onChange={e => updateRoomLabel(selectedRoom.id, e.target.value as RoomLabel)}
                  className="px-3 py-2 rounded-xl border border-border bg-white font-body text-[13px] text-ink"
                >
                  {ROOM_LABELS.map(l => (
                    <option key={l} value={l}>{ROOM_LABEL_RU[l]}</option>
                  ))}
                </select>
              </div>
              <div className="flex flex-col gap-2">
                <label className="font-body text-[12px] text-ink">Площадь (м²)</label>
                <input
                  type="number"
                  step="0.1"
                  defaultValue={selectedRoom.area_m2 ?? ''}
                  placeholder="Например: 18.5"
                  onChange={e => {
                    const v = parseFloat(e.target.value)
                    if (!isNaN(v) && v > 0) updateRoomArea(selectedRoom.id, v)
                  }}
                  className="px-3 py-2 rounded-xl border border-border bg-white font-body text-[13px] text-ink"
                />
              </div>
            </div>
          )}

          {/* Заметки */}
          <div className="bg-white rounded-2xl border border-border p-4">
            <label className="font-body text-[13px] font-semibold text-ink block mb-2">
              Заметки (опционально)
            </label>
            <textarea
              value={confirmNotes}
              onChange={e => setConfirmNotes(e.target.value)}
              placeholder="Укажите особенности планировки..."
              rows={2}
              className="w-full px-3 py-2 rounded-xl border border-border font-body text-[13px] text-ink resize-none"
            />
          </div>

          {/* Кнопка подтверждения */}
          <button
            onClick={handleConfirm}
            className="btn-primary py-4 text-[16px] flex items-center justify-center gap-2"
          >
            <CheckCircle2 size={18} />
            Геометрия верная — расставить мебель
            <ArrowRight size={16} />
          </button>

          <p className="font-body text-[11px] text-muted text-center px-4">
            После подтверждения стены и комнаты фиксируются.
            ИИ не сможет их изменить — только расставит мебель.
          </p>
        </div>
      </main>
    </div>
  )
}
