import { api, setAccessToken, clearAccessToken } from './api'
import type { AuthResponse, LoginRequest, RegisterRequest, User } from '@/types/api'

export async function register(data: RegisterRequest): Promise<AuthResponse> {
  const result = await api.post<AuthResponse>('/auth/register', data)
  setAccessToken(result.access_token)
  return result
}

export async function login(data: LoginRequest): Promise<AuthResponse> {
  const result = await api.post<AuthResponse>('/auth/login', data)
  setAccessToken(result.access_token)
  return result
}

export async function logout(): Promise<void> {
  await api.post('/auth/logout')
  clearAccessToken()
}

export async function getMe(): Promise<User> {
  return api.get<User>('/auth/me')
}

export async function refreshToken(): Promise<string | null> {
  try {
    const result = await api.post<{ access_token: string }>('/auth/refresh')
    setAccessToken(result.access_token)
    return result.access_token
  } catch {
    return null
  }
}
