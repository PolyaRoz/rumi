/**
 * Zustand-стор для хранения структурированной геометрии квартиры.
 *
 * ApartmentGeometry — результат CV-пайплайна.
 * После подтверждения пользователем флаг userValidated = true,
 * и геометрия считается locked — AI не может её изменять.
 */

import { create } from 'zustand'

// ─── Типы (зеркало Python схем) ───────────────────────────────────────────────

export interface Point {
  x: number
  y: number
}

export type WallType = 'outer' | 'inner' | 'unknown'

export interface Wall {
  id: string
  type: WallType
  start: Point
  end: Point
  thickness_px: number
  locked: boolean
  confidence: number
}

export type OpeningType = 'door' | 'window'

export interface Opening {
  id: string
  type: OpeningType
  wall_id: string
  position: Point
  width_px: number
  width_m: number | null
  swing_direction: string
  clearance_m: number
  locked: boolean
  confidence: number
}

export type RoomLabel =
  | 'living_room' | 'bedroom' | 'kitchen' | 'bathroom'
  | 'toilet' | 'corridor' | 'kids_room' | 'balcony'
  | 'storage' | 'unknown'

export const ROOM_LABEL_RU: Record<RoomLabel, string> = {
  living_room: 'Гостиная',
  bedroom:     'Спальня',
  kitchen:     'Кухня',
  bathroom:    'Ванная',
  toilet:      'Туалет',
  corridor:    'Коридор',
  kids_room:   'Детская',
  balcony:     'Балкон',
  storage:     'Кладовая',
  unknown:     'Неизвестно',
}

export interface Room {
  id: string
  label: RoomLabel
  area_m2: number | null
  area_px2: number | null
  polygon: Point[]
  centroid: Point | null
  locked: boolean
  confidence: number
  wall_ids: string[]
  opening_ids: string[]
}

export interface Scale {
  px_per_meter: number | null
  source: string
  confidence: number
}

export interface ConfidenceScores {
  wall_confidence: number
  room_confidence: number
  door_confidence: number
  window_confidence: number
  scale_confidence: number
}

export interface DebugLayers {
  original: string | null
  preprocessed: string | null
  walls_detected: string | null
  rooms_detected: string | null
  doors_detected: string | null
  windows_detected: string | null
  final_geometry: string | null
}

export interface ApartmentGeometry {
  source_image_width_px:  number
  source_image_height_px: number
  scale: Scale
  walls: Wall[]
  openings: Opening[]
  rooms: Room[]
  constraints: {
    do_not_move_walls: boolean
    do_not_block_doors: boolean
    keep_clearance_near_doors_m: number
    keep_walkway_width_m: number
    mode: string
  }
  confidence: ConfidenceScores
  debug: DebugLayers | null
  user_validated: boolean
  validation_notes: string
}

// ─── Типы расстановки ─────────────────────────────────────────────────────────

export interface PlacedFurniture {
  item_id: string
  room_id: string
  position: Point
  rotation_deg: number
  width_px: number
  depth_px: number
}

export interface RoomLayout {
  room_id: string
  room_label: string
  placed_items: PlacedFurniture[]
  unplaced_items: string[]
  warnings: string[]
}

export interface FurniturePlacement {
  style: string
  budget: string
  rooms: RoomLayout[]
  validated: boolean
  validation_errors: string[]
  total_price_rub: number
}

// ─── Store ────────────────────────────────────────────────────────────────────

type AnalysisStatus = 'idle' | 'analyzing' | 'done' | 'error'
type PlacementStatus = 'idle' | 'placing' | 'done' | 'error'

interface GeometryStore {
  // Геометрия
  geometry: ApartmentGeometry | null
  analysisStatus: AnalysisStatus
  analysisError: string | null
  needsValidation: boolean

  // Расстановка
  placement: FurniturePlacement | null
  placementStatus: PlacementStatus
  placementError: string | null

  // Валидация
  validationErrors: string[]
  validationWarnings: string[]

  // Actions
  setGeometry: (g: ApartmentGeometry) => void
  setAnalysisStatus: (s: AnalysisStatus, error?: string) => void
  setNeedsValidation: (v: boolean) => void
  confirmGeometry: (notes?: string) => void
  updateRoomLabel: (roomId: string, label: RoomLabel) => void
  updateRoomArea: (roomId: string, area_m2: number) => void
  updateScale: (px_per_meter: number) => void

  setPlacement: (p: FurniturePlacement) => void
  setPlacementStatus: (s: PlacementStatus, error?: string) => void
  setValidationResult: (errors: string[], warnings: string[]) => void

  reset: () => void
}

export const useGeometryStore = create<GeometryStore>((set, get) => ({
  geometry: null,
  analysisStatus: 'idle',
  analysisError: null,
  needsValidation: false,

  placement: null,
  placementStatus: 'idle',
  placementError: null,

  validationErrors: [],
  validationWarnings: [],

  setGeometry: (g) => set({ geometry: g }),

  setAnalysisStatus: (s, error) => set({
    analysisStatus: s,
    analysisError: error ?? null,
  }),

  setNeedsValidation: (v) => set({ needsValidation: v }),

  confirmGeometry: (notes = '') => set((s) => ({
    geometry: s.geometry
      ? { ...s.geometry, user_validated: true, validation_notes: notes }
      : null,
    needsValidation: false,
  })),

  updateRoomLabel: (roomId, label) => set((s) => ({
    geometry: s.geometry ? {
      ...s.geometry,
      rooms: s.geometry.rooms.map((r) =>
        r.id === roomId ? { ...r, label } : r
      ),
    } : null,
  })),

  updateRoomArea: (roomId, area_m2) => set((s) => ({
    geometry: s.geometry ? {
      ...s.geometry,
      rooms: s.geometry.rooms.map((r) =>
        r.id === roomId ? { ...r, area_m2 } : r
      ),
    } : null,
  })),

  updateScale: (px_per_meter) => set((s) => {
    if (!s.geometry) return {}
    const rooms = s.geometry.rooms.map((r) => ({
      ...r,
      area_m2: r.area_px2
        ? Math.round(r.area_px2 / (px_per_meter ** 2) * 10) / 10
        : r.area_m2,
    }))
    return {
      geometry: {
        ...s.geometry,
        scale: { ...s.geometry.scale, px_per_meter, source: 'user_input' },
        rooms,
      },
    }
  }),

  setPlacement: (p) => set({ placement: p }),
  setPlacementStatus: (s, error) => set({
    placementStatus: s,
    placementError: error ?? null,
  }),

  setValidationResult: (errors, warnings) => set({
    validationErrors: errors,
    validationWarnings: warnings,
  }),

  reset: () => set({
    geometry: null,
    analysisStatus: 'idle',
    analysisError: null,
    needsValidation: false,
    placement: null,
    placementStatus: 'idle',
    placementError: null,
    validationErrors: [],
    validationWarnings: [],
  }),
}))
