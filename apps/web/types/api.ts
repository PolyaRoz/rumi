// ── Общие ────────────────────────────────────────────────────────────────────

export interface ApiResponse<T> {
  data: T
  error: string | null
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export interface User {
  id: string
  email: string
  name: string | null
  plan: 'free' | 'basic' | 'pro' | 'investor' | 'agency'
  generations_used: number
  generations_limit: number
  avatar_url: string | null
  created_at: string
}

export interface AuthResponse {
  access_token: string
  token_type: string
  user: User
}

export interface RegisterRequest {
  email: string
  password: string
  name?: string
}

export interface LoginRequest {
  email: string
  password: string
}

// ── Projects ──────────────────────────────────────────────────────────────────

export type RoomType =
  | 'living'
  | 'bedroom'
  | 'kitchen'
  | 'office'
  | 'bathroom'
  | 'dining'
  | 'hallway'

export type StyleType =
  | 'scandinavian'
  | 'modern'
  | 'classic'
  | 'loft'
  | 'japandi'
  | 'eclectic'

export interface Room {
  id: string
  room_type: RoomType
  style: StyleType
  budget_rub: number | null
  area_sqm: number | null
  notes: string | null
  photos_count: number
  created_at: string
}

export interface Project {
  id: string
  name: string
  segment: 'self' | 'invest'
  budget_rub: number | null
  created_at: string
  updated_at: string
  rooms: Room[]
}

export interface CreateProjectRequest {
  name?: string
  segment?: 'self' | 'invest'
  budget_rub?: number
}

export interface CreateRoomRequest {
  room_type: RoomType
  style: StyleType
  budget_rub?: number
  area_sqm?: number
  notes?: string
}

// ── Tasks ─────────────────────────────────────────────────────────────────────

export type TaskStatus = 'queued' | 'processing' | 'done' | 'failed'
export type TaskStage = 'cv_analysis' | 'generation' | 'matching'

export interface TaskEvent {
  status: TaskStatus
  stage?: TaskStage
  progress: number
  result?: { variant_ids: string[] }
  error?: string
}
