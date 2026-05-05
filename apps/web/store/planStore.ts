import { create } from 'zustand'

interface PlanStore {
  planUrl: string | null
  planFileName: string | null
  setPlan: (url: string, fileName: string) => void
  clearPlan: () => void
}

export const usePlanStore = create<PlanStore>((set) => ({
  planUrl: null,
  planFileName: null,
  setPlan: (url, fileName) => set({ planUrl: url, planFileName: fileName }),
  clearPlan: () => set({ planUrl: null, planFileName: null }),
}))
