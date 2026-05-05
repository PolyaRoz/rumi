'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { ArrowRight, Check } from 'lucide-react'
import StepHeader from '@/components/StepHeader'
import { useVisualizationStore } from '@/store/visualizationStore'

type Who = 'one' | 'pair' | 'family'
type Style = 'minimal' | 'scandi' | 'loft' | 'classic'
type Budget = 'economy' | 'middle' | 'premium'
type Priority = 'storage' | 'workspace' | 'kids' | 'guest'

const WHO_OPTIONS: { id: Who; label: string; emoji: string }[] = [
  { id: 'one', label: 'Один', emoji: '🧍' },
  { id: 'pair', label: 'Пара', emoji: '👫' },
  { id: 'family', label: 'Семья с детьми', emoji: '👨‍👩‍👧' },
]

const STYLE_OPTIONS: { id: Style; label: string; desc: string }[] = [
  { id: 'minimal', label: 'Минимализм', desc: 'Чистые линии, нейтральные тона' },
  { id: 'scandi', label: 'Скандинавский', desc: 'Светло, тепло, природные материалы' },
  { id: 'loft', label: 'Лофт', desc: 'Металл, дерево, открытое пространство' },
  { id: 'classic', label: 'Классика', desc: 'Элегантность, симметрия, детали' },
]

const BUDGET_OPTIONS: { id: Budget; label: string; range: string }[] = [
  { id: 'economy', label: 'Эконом', range: 'до 100 000 ₽' },
  { id: 'middle', label: 'Средний', range: '100 000–300 000 ₽' },
  { id: 'premium', label: 'Премиум', range: 'от 300 000 ₽' },
]

const PRIORITY_OPTIONS: { id: Priority; label: string; emoji: string }[] = [
  { id: 'storage', label: 'Хранение', emoji: '📦' },
  { id: 'workspace', label: 'Рабочее место', emoji: '💻' },
  { id: 'kids', label: 'Детская зона', emoji: '🧸' },
  { id: 'guest', label: 'Гостевое место', emoji: '🛏' },
]

export default function PreferencesPage() {
  const router = useRouter()
  const resetVisualization = useVisualizationStore(s => s.reset)
  const [who, setWho] = useState<Who | null>(null)
  const [style, setStyle] = useState<Style | null>(null)
  const [budget, setBudget] = useState<Budget | null>(null)
  const [priorities, setPriorities] = useState<Priority[]>([])

  const togglePriority = (id: Priority) =>
    setPriorities(prev => prev.includes(id) ? prev.filter(p => p !== id) : [...prev, id])

  const canContinue = who && style && budget

  const handleContinue = () => {
    resetVisualization() // новые предпочтения — сбрасываем старые визуализации
    router.push('/processing')
  }

  return (
    <div className="min-h-screen bg-paper flex flex-col">
      <StepHeader current={1} backHref="/upload" backLabel="Назад к плану" />

      <main className="flex-1 px-6 py-10">
        <div className="w-full max-w-[600px] mx-auto flex flex-col gap-10">
          <div>
            <h1 className="font-heading text-[42px] font-semibold text-ink leading-tight">
              Расскажите о себе
            </h1>
            <p className="font-body text-[15px] text-muted mt-2">
              Это поможет подобрать мебель именно под ваши потребности
            </p>
          </div>

          {/* Кто живёт */}
          <div className="flex flex-col gap-4">
            <h2 className="font-heading text-[22px] font-semibold text-ink">Кто живёт в квартире?</h2>
            <div className="flex gap-3">
              {WHO_OPTIONS.map(opt => (
                <button key={opt.id} onClick={() => setWho(opt.id)}
                  className={`flex-1 flex flex-col items-center gap-2 py-4 px-3 rounded-xl border-2 transition-all font-body
                    ${who === opt.id ? 'border-terracotta bg-terracotta-50' : 'border-border bg-white hover:border-terracotta/40'}`}>
                  <span className="text-2xl">{opt.emoji}</span>
                  <span className={`text-[13px] font-medium ${who === opt.id ? 'text-terracotta' : 'text-ink'}`}>
                    {opt.label}
                  </span>
                </button>
              ))}
            </div>
          </div>

          {/* Стиль */}
          <div className="flex flex-col gap-4">
            <h2 className="font-heading text-[22px] font-semibold text-ink">Желаемый стиль</h2>
            <div className="grid grid-cols-2 gap-3">
              {STYLE_OPTIONS.map(opt => (
                <button key={opt.id} onClick={() => setStyle(opt.id)}
                  className={`flex flex-col items-start gap-1 p-4 rounded-xl border-2 transition-all text-left
                    ${style === opt.id ? 'border-terracotta bg-terracotta-50' : 'border-border bg-white hover:border-terracotta/40'}`}>
                  <div className="flex items-center justify-between w-full">
                    <span className={`font-body text-[14px] font-semibold ${style === opt.id ? 'text-terracotta' : 'text-ink'}`}>
                      {opt.label}
                    </span>
                    {style === opt.id && (
                      <div className="w-4 h-4 rounded-full bg-terracotta flex items-center justify-center">
                        <Check size={10} className="text-white" />
                      </div>
                    )}
                  </div>
                  <span className="font-body text-[12px] text-muted">{opt.desc}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Бюджет */}
          <div className="flex flex-col gap-4">
            <h2 className="font-heading text-[22px] font-semibold text-ink">Бюджет на мебель</h2>
            <div className="flex flex-col gap-2">
              {BUDGET_OPTIONS.map(opt => (
                <button key={opt.id} onClick={() => setBudget(opt.id)}
                  className={`flex items-center justify-between px-5 py-4 rounded-xl border-2 transition-all
                    ${budget === opt.id ? 'border-terracotta bg-terracotta-50' : 'border-border bg-white hover:border-terracotta/40'}`}>
                  <span className={`font-body text-[14px] font-semibold ${budget === opt.id ? 'text-terracotta' : 'text-ink'}`}>
                    {opt.label}
                  </span>
                  <div className="flex items-center gap-3">
                    <span className="font-body text-[13px] text-muted">{opt.range}</span>
                    <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center
                      ${budget === opt.id ? 'border-terracotta bg-terracotta' : 'border-border'}`}>
                      {budget === opt.id && <Check size={11} className="text-white" />}
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Приоритеты */}
          <div className="flex flex-col gap-4">
            <div>
              <h2 className="font-heading text-[22px] font-semibold text-ink">Приоритеты</h2>
              <p className="font-body text-[13px] text-muted mt-1">Выберите всё, что важно (необязательно)</p>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {PRIORITY_OPTIONS.map(opt => {
                const selected = priorities.includes(opt.id)
                return (
                  <button key={opt.id} onClick={() => togglePriority(opt.id)}
                    className={`flex items-center gap-3 px-4 py-3 rounded-xl border-2 transition-all
                      ${selected ? 'border-sage bg-sage-50' : 'border-border bg-white hover:border-sage/40'}`}>
                    <span className="text-lg">{opt.emoji}</span>
                    <span className={`font-body text-[13px] font-medium ${selected ? 'text-sage-dark' : 'text-ink'}`}>
                      {opt.label}
                    </span>
                    {selected && (
                      <div className="ml-auto w-4 h-4 rounded bg-sage flex items-center justify-center flex-shrink-0">
                        <Check size={10} className="text-white" />
                      </div>
                    )}
                  </button>
                )
              })}
            </div>
          </div>

          <button
            onClick={handleContinue}
            disabled={!canContinue}
            className="btn-primary py-4 text-[16px] flex items-center justify-center gap-2"
          >
            Расставить мебель <ArrowRight size={18} />
          </button>
        </div>
      </main>
    </div>
  )
}
