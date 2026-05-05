'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import StepHeader from '@/components/StepHeader'

const AI_STEPS = [
  { label: 'Распознаём комнаты на плане', duration: 2000 },
  { label: 'Определяем размеры помещений', duration: 2000 },
  { label: 'Подбираем оптимальную расстановку', duration: 2500 },
  { label: 'Генерируем визуализации', duration: 2000 },
  { label: 'Подбираем товары из магазинов', duration: 1500 },
]

export default function ProcessingPage() {
  const router = useRouter()
  const [currentStep, setCurrentStep] = useState(0)
  const [doneSteps, setDoneSteps] = useState<number[]>([])

  useEffect(() => {
    let totalDelay = 0

    AI_STEPS.forEach((step, i) => {
      setTimeout(() => setCurrentStep(i), totalDelay)
      totalDelay += step.duration
      setTimeout(() => setDoneSteps(prev => [...prev, i]), totalDelay - 300)
    })

    const total = AI_STEPS.reduce((sum, s) => sum + s.duration, 0)
    setTimeout(() => router.push('/visualization'), total + 400)
  }, [router])

  const progress = Math.round((doneSteps.length / AI_STEPS.length) * 100)

  return (
    <div className="min-h-screen bg-paper flex flex-col">
      <StepHeader current={2} />

      <main className="flex-1 flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-[480px] flex flex-col items-center gap-10">
          {/* Animated logo */}
          <div className="relative">
            <div className="w-20 h-20 rounded-3xl bg-terracotta-100 flex items-center justify-center">
              <span className="text-3xl">🛋</span>
            </div>
            <div className="absolute inset-0 rounded-3xl bg-terracotta/15 animate-ping" />
          </div>

          {/* Title */}
          <div className="text-center flex flex-col gap-2">
            <h1 className="font-heading text-[36px] font-semibold text-ink">
              Расставляем мебель…
            </h1>
            <p className="font-body text-[15px] text-muted">
              Claude анализирует план и подбирает варианты
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
            {AI_STEPS.map((step, i) => {
              const isDone = doneSteps.includes(i)
              const isCurrent = currentStep === i && !isDone
              return (
                <div
                  key={i}
                  className={`flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-300
                    ${isCurrent ? 'bg-white border border-terracotta/30 shadow-sm' : ''}
                    ${isDone ? 'opacity-50' : isCurrent ? 'opacity-100' : 'opacity-25'}
                  `}
                >
                  <div className={`w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0
                    ${isDone ? 'bg-sage' : isCurrent ? 'bg-terracotta' : 'bg-border'}`}>
                    {isDone ? (
                      <svg width="10" height="8" viewBox="0 0 10 8" fill="none">
                        <path d="M1 4L3.5 6.5L9 1" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    ) : isCurrent ? (
                      <div className="w-2 h-2 rounded-full bg-white animate-pulse" />
                    ) : null}
                  </div>
                  <span className={`font-body text-[14px] ${isCurrent ? 'text-ink font-medium' : 'text-muted'}`}>
                    {step.label}
                  </span>
                  {isCurrent && (
                    <div className="ml-auto flex gap-0.5">
                      {[0, 1, 2].map(d => (
                        <div key={d} className="w-1 h-1 rounded-full bg-terracotta animate-bounce"
                          style={{ animationDelay: `${d * 150}ms` }} />
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </div>

          <p className="font-body text-[13px] text-muted">Обычно занимает 5–10 секунд</p>
        </div>
      </main>
    </div>
  )
}
