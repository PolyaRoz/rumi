import { create } from 'zustand'
import type { RoomType, StyleType } from '@/types/api'

interface OnboardingState {
  step: 1 | 2 | 3
  projectId: string | null
  roomId: string | null
  photos: File[]
  roomType: RoomType
  style: StyleType
  budgetRub: number
  notes: string

  setStep: (step: 1 | 2 | 3) => void
  setProjectId: (id: string) => void
  setRoomId: (id: string) => void
  setPhotos: (files: File[]) => void
  setRoomType: (type: RoomType) => void
  setStyle: (style: StyleType) => void
  setBudget: (rub: number) => void
  setNotes: (notes: string) => void
  reset: () => void
}

const DEFAULTS = {
  step: 1 as const,
  projectId: null,
  roomId: null,
  photos: [],
  roomType: 'living' as RoomType,
  style: 'scandinavian' as StyleType,
  budgetRub: 300_000,
  notes: '',
}

export const useOnboardingStore = create<OnboardingState>((set) => ({
  ...DEFAULTS,

  setStep: (step) => set({ step }),
  setProjectId: (projectId) => set({ projectId }),
  setRoomId: (roomId) => set({ roomId }),
  setPhotos: (photos) => set({ photos }),
  setRoomType: (roomType) => set({ roomType }),
  setStyle: (style) => set({ style }),
  setBudget: (budgetRub) => set({ budgetRub }),
  setNotes: (notes) => set({ notes }),
  reset: () => set(DEFAULTS),
}))
