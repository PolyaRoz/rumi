'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { useAuthStore } from '@/store/authStore'
import { getMe, refreshToken } from '@/lib/auth'

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, setUser, setLoading } = useAuthStore()
  const router = useRouter()

  useEffect(() => {
    // Пытаемся восстановить сессию при загрузке
    async function restoreSession() {
      setLoading(true)
      try {
        // Сначала пробуем получить текущего пользователя
        const me = await getMe()
        setUser(me)
      } catch {
        // access token протух — пробуем refresh
        const token = await refreshToken()
        if (token) {
          try {
            const me = await getMe()
            setUser(me)
          } catch {
            setUser(null)
            router.replace('/auth')
          }
        } else {
          setUser(null)
          router.replace('/auth')
        }
      }
    }

    if (!user) {
      restoreSession()
    } else {
      setLoading(false)
    }
  }, [])

  return (
    <div className="min-h-screen bg-paper">
      {children}
    </div>
  )
}
