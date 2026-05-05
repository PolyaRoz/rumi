import axios, { type AxiosInstance } from 'axios'

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

// Синглтон клиент
let _client: AxiosInstance | null = null

function getClient(): AxiosInstance {
  if (_client) return _client

  _client = axios.create({
    baseURL: `${BASE_URL}/api/v1`,
    withCredentials: true, // для httpOnly refresh cookie
    headers: { 'Content-Type': 'application/json' },
  })

  // Вставляем access token из памяти в каждый запрос
  _client.interceptors.request.use((config) => {
    const token = getAccessToken()
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  })

  // Автообновление токена при 401
  _client.interceptors.response.use(
    (res) => res,
    async (error) => {
      const original = error.config
      if (error.response?.status === 401 && !original._retry) {
        original._retry = true
        try {
          const { data } = await axios.post(
            `${BASE_URL}/api/v1/auth/refresh`,
            {},
            { withCredentials: true }
          )
          setAccessToken(data.data.access_token)
          original.headers.Authorization = `Bearer ${data.data.access_token}`
          return _client!(original)
        } catch {
          clearAccessToken()
          if (typeof window !== 'undefined') {
            window.location.href = '/auth'
          }
        }
      }
      return Promise.reject(error)
    }
  )

  return _client
}

// ── Хранение access token в памяти (не localStorage, не cookie) ───────────────
let _accessToken: string | null = null

export function setAccessToken(token: string) {
  _accessToken = token
}

export function getAccessToken(): string | null {
  return _accessToken
}

export function clearAccessToken() {
  _accessToken = null
}

// ── Экспортируемый API-объект ─────────────────────────────────────────────────
export const api = {
  get: <T>(url: string, params?: object) =>
    getClient().get<{ data: T }>(url, { params }).then((r) => r.data.data),

  post: <T>(url: string, body?: unknown) =>
    getClient().post<{ data: T }>(url, body).then((r) => r.data.data),

  patch: <T>(url: string, body?: unknown) =>
    getClient().patch<{ data: T }>(url, body).then((r) => r.data.data),

  delete: (url: string) =>
    getClient().delete(url),

  // Прямой запрос — для случаев где нужен полный ответ
  raw: () => getClient(),
}
