'use client'

import Link from 'next/link'
import { Check } from 'lucide-react'

const STEPS = ['Загрузка', 'Предпочтения', 'Визуализация', 'Подборка']

interface StepHeaderProps {
  current: number // 0-based index
  backHref?: string
  backLabel?: string
}

export default function StepHeader({ current, backHref, backLabel }: StepHeaderProps) {
  return (
    <>
      {/* Top nav */}
      <header className="h-[64px] bg-white border-b border-border flex items-center justify-between px-6 md:px-10 flex-shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="w-2 h-2 rounded-full bg-terracotta" />
          <span className="font-heading text-[22px] font-semibold text-ink">Руми</span>
        </div>
        {backHref && (
          <Link
            href={backHref}
            className="font-body text-[14px] text-muted hover:text-ink transition-colors"
          >
            ← {backLabel ?? 'Назад'}
          </Link>
        )}
      </header>

      {/* Progress bar */}
      <div className="bg-white border-b border-border px-6 md:px-10 py-3 flex items-center gap-2">
        {STEPS.map((label, i) => {
          const done = i < current
          const active = i === current
          return (
            <div key={i} className="flex items-center gap-2">
              <div className="flex items-center gap-2">
                <div
                  className={`w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-medium font-body flex-shrink-0
                    ${done ? 'bg-sage text-white' : active ? 'bg-terracotta text-white' : 'bg-border text-muted'}`}
                >
                  {done ? <Check size={11} /> : i + 1}
                </div>
                <span
                  className={`font-body text-[13px] hidden sm:block flex-shrink-0
                    ${active ? 'text-ink font-medium' : done ? 'text-sage' : 'text-muted'}`}
                >
                  {label}
                </span>
              </div>
              {i < STEPS.length - 1 && (
                <div className={`w-6 md:w-10 h-px flex-shrink-0 ${done ? 'bg-sage/40' : 'bg-border'}`} />
              )}
            </div>
          )
        })}
      </div>
    </>
  )
}
