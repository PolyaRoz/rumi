'use client'

/**
 * Страница обработки — реальный pipeline (НЕ фейк-анимация).
 *
 * Логика:
 * 1. Если geometry.user_validated === false → вызвать /api/v1/plan/analyze
 *    → положить в geometryStore → перенаправить на /analysis
 *
 * 2. Если geometry.user_validated === true (вернулись с /analysis):
 *    → вызвать /api/v1/plan/place-furniture
 *    → положить placement в geometryStore
 *    → вызвать /api/v1/plan/validate-layout (проверка)
 *    → перенаправить на /visualization
 *
 * Это центральный оркестратор pipeline. Pipeline нельзя обойти —
 * /visualization не работает без validated geometry + placement.
 */

import { useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { AlertTriangle, RotateCcw } from 'lucide-react'
import StepHeader from '@/components/StepHeader'
import { usePlanStore } from '@/store/planStore'
import { useGeometryStore } from '@/store/geometryStore'
import { usePreferencesStore } from '@/store/preferencesStore'

const PIPELINE_STEPS = [
  { id: 'analyze',  label: 'Claude Vision анализирует план',       weight: 4 },
  { id: 'scale',    label: 'Определяем масштаб по подписям',       weight: 1 },
  { id: 'validate', label: 'Проверяем геометрию',                  weight: 1 },
  { id: 'select',   label: 'Подбираем мебель из каталога',         weight: 2 },
  { id: 'place',    label: 'Расставляем по правилам',              weight: 3 },
  { id: 'check',    label: 'Проверяем расстановку',                weight: 1 },
]

export default function ProcessingPage() {
  const router = useRouter()

  const { planFile, planFalUrl } = usePlanStore()
  const {
    geometry, analysisStatus, analysisError,
    placement, placementStatus, placementError,
    setGeometry, setAnalysisStatus, setNeedsValidation,
    setPlacement, setPlacementStatus,
    setValidationResult,
  } = useGeometryStore()
  const { style, budget, priorities } = usePreferencesStore()

  const [currentStep, setCurrentStep] = useState(0)
  const [error, setError] = useState<string | null>(null)
  // Ref-guard против двойного запуска в React StrictMode (dev-режим двойной mount)
  const runningRef = useRef(false)

  useEffect(() => {
    // Защита от повторного запуска (ref работает синхронно, в отличие от state)
    if (runningRef.current) return
    if (analysisStatus === 'analyzing' || placementStatus === 'placing') return

    const run = async () => {
      // ── Сценарий 1: геометрия ещё не получена → запустить анализ ─────────
      if (!geometry || analysisStatus !== 'done') {
        await runAnalyze()
        return
      }

      // ── Сценарий 2: геометрия не подтверждена → отправить на валидацию ───
      if (!geometry.user_validated) {
        router.push('/analysis')
        return
      }

      // ── Сценарий 3: геометрия подтверждена → запустить размещение ────────
      if (!placement || placementStatus !== 'done') {
        await runPlaceFurniture()
        return
      }

      // ── Сценарий 4: всё готово → визуализация ────────────────────────────
      router.push('/visualization')
    }

    runningRef.current = true
    run()
      .catch(err => setError(err?.message ?? 'Ошибка обработки'))
      .finally(() => { runningRef.current = false })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [geometry, analysisStatus, placement, placementStatus])

  // ── Анализ плана ──────────────────────────────────────────────────────────

  const runAnalyze = async () => {
    if (!planFalUrl && !planFile) {
      setError('План не загружен — вернитесь на шаг загрузки')
      return
    }

    setAnalysisStatus('analyzing')
    setCurrentStep(0)

    try {
      const fd = new FormData()
      if (planFalUrl) {
        fd.append('image_url', planFalUrl)
      } else if (planFile) {
        fd.append('file', planFile)
      }
      fd.append('include_debug', 'false')

      const res = await fetch('/api/v1/plan/analyze-vision', {
        method: 'POST',
        body: fd,
      })

      if (!res.ok) {
        const txt = await res.text().catch(() => '')
        throw new Error(`HTTP ${res.status}: ${txt.slice(0, 200)}`)
      }

      const data = await res.json()
      if (data.geometry) {
        setGeometry(data.geometry)
        setNeedsValidation(Boolean(data.needs_validation))
        setAnalysisStatus('done')
        setCurrentStep(2)

        // Перенаправляем на /analysis для подтверждения
        router.push('/analysis')
      } else {
        throw new Error(data.message ?? 'Не удалось распознать план')
      }
    } catch (err: any) {
      const msg = err?.message ?? 'Ошибка анализа плана'
      setAnalysisStatus('error', msg)
      setError(msg)
    }
  }

  // ── Расстановка мебели ────────────────────────────────────────────────────

  const runPlaceFurniture = async () => {
    if (!geometry?.user_validated) {
      setError('Геометрия не подтверждена')
      return
    }

    setPlacementStatus('placing')
    setCurrentStep(3)

    try {
      const res = await fetch('/api/v1/plan/place-furniture', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          geometry,
          style:    style    ?? 'scandi',
          budget:   budget   ?? 'middle',
          priorities,
        }),
      })

      if (!res.ok) {
        const txt = await res.text().catch(() => '')
        throw new Error(`HTTP ${res.status}: ${txt.slice(0, 200)}`)
      }

      const data = await res.json()
      if (!data.placement) {
        throw new Error('Сервер не вернул расстановку')
      }
      setPlacement(data.placement)
      setCurrentStep(5)

      // ── Валидация ──────────────────────────────────────────────────────────
      try {
        const valRes = await fetch('/api/v1/plan/validate-layout', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ geometry, placement: data.placement }),
        })
        if (valRes.ok) {
          const valData = await valRes.json()
          setValidationResult(valData.errors ?? [], valData.warnings ?? [])
        }
      } catch (e) {
        // Валидация — не критична, просто логируем
        console.warn('[validate-layout] failed:', e)
      }

      setPlacementStatus('done')
      router.push('/visualization')
    } catch (err: any) {
      const msg = err?.message ?? 'Ошибка расстановки мебели'
      setPlacementStatus('error', msg)
      setError(msg)
    }
  }

  // ── Прогресс ──────────────────────────────────────────────────────────────

  const totalWeight = PIPELINE_STEPS.reduce((s, x) => s + x.weight, 0)
  const doneWeight  = PIPELINE_STEPS.slice(0, currentStep).reduce((s, x) => s + x.weight, 0)
  const progress    = Math.round((doneWeight / totalWeight) * 100)

  // ── Render ────────────────────────────────────────────────────────────────

  if (error) {
    return (
      <div className="min-h-screen bg-paper flex flex-col">
        <StepHeader current={2} backHref="/preferences" backLabel="Назад" />
        <div className="flex-1 flex flex-col items-center justify-center gap-6 px-6">
          <AlertTriangle size={48} className="text-terracotta" />
          <div className="text-center max-w-md">
            <p className="font-heading text-[24px] font-semibold text-ink">Не удалось обработать план</p>
            <p className="font-body text-[14px] text-muted mt-2">{error}</p>
          </div>
          <button
            onClick={() => router.push('/upload')}
            className="btn-primary px-8 py-3 flex items-center gap-2"
          >
            <RotateCcw size={16} /> Загрузить другой план
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-paper flex flex-col">
      <StepHeader current={2} />

      <main className="flex-1 flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-[480px] flex flex-col items-center gap-10">

          {/* Animated logo */}
          <div className="relative">
            <div className="w-20 h-20 rounded-3xl bg-terracotta-100 flex items-center justify-center">
              <span className="text-3xl">📐</span>
            </div>
            <div className="absolute inset-0 rounded-3xl bg-terracotta/15 animate-ping" />
          </div>

          {/* Title */}
          <div className="text-center flex flex-col gap-2">
            <h1 className="font-heading text-[36px] font-semibold text-ink">
              {analysisStatus === 'analyzing' ? 'Анализируем план…' :
               placementStatus === 'placing' ? 'Расставляем мебель…' :
               'Подготовка…'}
            </h1>
            <p className="font-body text-[15px] text-muted">
              Claude Vision распознаёт геометрию и расставляет мебель из каталога
            </p>
          </div>

          {/* Progress bar */}
          <div className="w-full flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <span className="font-body text-[13px] text-muted">Прогресс</span>
              <span className="font-body text-[13px] font-medium text-ink">{progress}%</span>
            </div>
            <div className="w-full h-2 bg-border rounded-full overflow-hidden">
              <div
                className="h-full bg-terracotta rounded-full transition-all duration-500 ease-out"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>

          {/* Steps */}
          <div className="w-full flex flex-col gap-2">
            {PIPELINE_STEPS.map((step, i) => {
              const isDone = i < currentStep
              const isCurrent = i === currentStep
              return (
                <div
                  key={step.id}
                  className={`flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-300
                    ${isCurrent ? 'bg-white border border-terracotta/30 shadow-sm' : ''}
                    ${isDone ? 'opacity-50' : isCurrent ? 'opacity-100' : 'opacity-25'}`}
                >
                  <div className={`w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0
                    ${isDone ? 'bg-sage' : isCurrent ? 'bg-terracotta' : 'bg-border'}`}>
                    {isDone ? (
                      <svg width="10" height="8" viewBox="0 0 10 8" fill="none">
                        <path d="M1 4L3.5 6.5L9 1" stroke="white" strokeWidth="1.5"
                              strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    ) : isCurrent ? (
                      <div className="w-2 h-2 rounded-full bg-white animate-pulse" />
                    ) : null}
                  </div>
                  <span className={`font-body text-[14px] ${isCurrent ? 'text-ink font-medium' : 'text-muted'}`}>
                    {step.label}
                  </span>
                </div>
              )
            })}
          </div>

          <p className="font-body text-[12px] text-muted text-center">
            Геометрия фиксируется — AI не сможет её изменить
          </p>
        </div>
      </main>
    </div>
  )
}
