import { create } from 'zustand'
import type { RoomType } from '@/lib/promptBuilder'

// ─── Types ────────────────────────────────────────────────────────────────────

export type GenStatus = 'idle' | 'loading' | 'done' | 'error'

export interface FloorplanResult {
  imageUrl: string | null
  status: 'idle' | 'uploading' | 'generating' | 'done' | 'error'
  error?: string
}

export interface RoomPhoto {
  id: RoomType
  label: string
  imageUrl: string | null
  status: GenStatus
  error?: string
}

interface VisualizationStore {
  floorplan: FloorplanResult
  rooms: RoomPhoto[]

  setFloorplan: (update: Partial<FloorplanResult>) => void
  setRoom: (id: RoomType, update: Partial<RoomPhoto>) => void

  // Сбросить всё — вызывать при загрузке нового плана или смене предпочтений
  reset: () => void
}

// ─── Initial state ────────────────────────────────────────────────────────────

const INITIAL_ROOMS: RoomPhoto[] = [
  { id: 'living',  label: 'Гостиная',      imageUrl: null, status: 'idle' },
  { id: 'bedroom', label: 'Спальня',        imageUrl: null, status: 'idle' },
  { id: 'kitchen', label: 'Кухня-столовая', imageUrl: null, status: 'idle' },
  { id: 'kids',    label: 'Детская',        imageUrl: null, status: 'idle' },
]

const INITIAL_FLOORPLAN: FloorplanResult = {
  imageUrl: null,
  status: 'idle',
}

// ─── Store ────────────────────────────────────────────────────────────────────

export const useVisualizationStore = create<VisualizationStore>((set) => ({
  floorplan: INITIAL_FLOORPLAN,
  rooms: INITIAL_ROOMS,

  setFloorplan: (update) =>
    set((s) => ({ floorplan: { ...s.floorplan, ...update } })),

  setRoom: (id, update) =>
    set((s) => ({
      rooms: s.rooms.map((r) => (r.id === id ? { ...r, ...update } : r)),
    })),

  reset: () =>
    set({
      floorplan: { ...INITIAL_FLOORPLAN },
      rooms: INITIAL_ROOMS.map((r) => ({ ...r })),
    }),
}))
