import { create } from 'zustand'
import type { StyleType } from '@/lib/promptBuilder'

export type Who      = 'one' | 'pair' | 'family'
export type Budget   = 'economy' | 'middle' | 'premium'
export type Priority = 'storage' | 'workspace' | 'kids' | 'guest'

export const STYLE_LABELS: Record<StyleType, string> = {
  scandi:  'Скандинавский',
  minimal: 'Минимализм',
  loft:    'Лофт',
  classic: 'Классика',
}

export const BUDGET_LABELS: Record<Budget, string> = {
  economy: 'Эконом · до 100 000 ₽',
  middle:  'Средний · 100–300 000 ₽',
  premium: 'Премиум · от 300 000 ₽',
}

export const WHO_LABELS: Record<Who, string> = {
  one:    'Один',
  pair:   'Пара',
  family: 'Семья с детьми',
}

interface PreferencesStore {
  style:      StyleType | null
  who:        Who       | null
  budget:     Budget    | null
  priorities: Priority[]

  setPreferences: (prefs: {
    style:      StyleType
    who:        Who
    budget:     Budget
    priorities: Priority[]
  }) => void

  // Готов ли пользователь продолжить (все обязательные поля заполнены)
  isReady: () => boolean
}

export const usePreferencesStore = create<PreferencesStore>((set, get) => ({
  style:      null,
  who:        null,
  budget:     null,
  priorities: [],

  setPreferences: (prefs) => set(prefs),

  isReady: () => {
    const s = get()
    return s.style !== null && s.who !== null && s.budget !== null
  },
}))
