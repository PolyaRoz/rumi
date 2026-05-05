import { create } from 'zustand'

interface PlanStore {
  planUrl: string | null       // blob URL для превью (клиент)
  planFile: File | null        // оригинальный File объект для загрузки
  planFileName: string | null
  planFalUrl: string | null    // URL в fal.ai storage (после загрузки)
  setPlan: (url: string, file: File, fileName: string) => void
  setPlanFalUrl: (url: string) => void
  clearPlan: () => void
}

export const usePlanStore = create<PlanStore>((set) => ({
  planUrl: null,
  planFile: null,
  planFileName: null,
  planFalUrl: null,
  setPlan: (url, file, fileName) => set({ planUrl: url, planFile: file, planFileName: fileName, planFalUrl: null }),
  setPlanFalUrl: (url) => set({ planFalUrl: url }),
  clearPlan: () => set({ planUrl: null, planFile: null, planFileName: null, planFalUrl: null }),
}))
