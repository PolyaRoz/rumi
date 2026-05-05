'use client'

import { useQuery } from '@tanstack/react-query'
import Link from 'next/link'
import { api } from '@/lib/api'
import type { Project } from '@/types/api'
import { useAuthStore } from '@/store/authStore'
import { logout } from '@/lib/auth'
import { useRouter } from 'next/navigation'

const ROOM_LABELS: Record<string, string> = {
  living: 'Гостиная',
  bedroom: 'Спальня',
  kitchen: 'Кухня',
  office: 'Кабинет',
  bathroom: 'Ванная',
  dining: 'Столовая',
  hallway: 'Прихожая',
}

export default function ProjectsPage() {
  const user = useAuthStore((s) => s.user)
  const setUser = useAuthStore((s) => s.setUser)
  const router = useRouter()

  const { data: projects, isLoading } = useQuery({
    queryKey: ['projects'],
    queryFn: () => api.get<Project[]>('/projects'),
  })

  async function handleLogout() {
    await logout()
    setUser(null)
    router.push('/')
  }

  return (
    <div className="min-h-screen bg-paper">
      {/* Navbar */}
      <nav className="h-16 bg-white border-b border-border flex items-center justify-between px-20">
        <div className="flex items-center gap-2.5">
          <div className="w-2.5 h-2.5 rounded-full bg-terracotta" />
          <span className="font-heading text-[26px] font-bold text-ink">Руми</span>
        </div>
        <div className="flex items-center gap-4">
          <span className="font-body text-sm text-muted">{user?.name ?? user?.email}</span>
          <button onClick={handleLogout} className="btn-ghost text-sm">
            Выйти
          </button>
        </div>
      </nav>

      <div className="max-w-5xl mx-auto px-8 py-10">
        <div className="flex items-center justify-between mb-8">
          <h1 className="font-heading text-4xl font-semibold text-ink">Мои проекты</h1>
          <Link href="/new" className="btn-primary">
            + Новый проект
          </Link>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-20">
            <div className="w-6 h-6 rounded-full border-2 border-terracotta border-t-transparent animate-spin" />
          </div>
        ) : projects && projects.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {projects.map((project) => (
              <Link
                key={project.id}
                href={`/projects/${project.id}`}
                className="card p-6 hover:border-terracotta/40 hover:shadow-sm transition-all"
              >
                <h3 className="font-heading text-xl font-semibold text-ink mb-1">
                  {project.name}
                </h3>
                <p className="font-body text-sm text-muted mb-3">
                  {project.rooms.length} комнат
                  {project.budget_rub
                    ? ` · бюджет ${project.budget_rub.toLocaleString('ru')} ₽`
                    : ''}
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {project.rooms.map((room) => (
                    <span
                      key={room.id}
                      className="px-2.5 py-1 rounded-full bg-cream text-ink text-xs font-body"
                    >
                      {ROOM_LABELS[room.room_type] ?? room.room_type}
                    </span>
                  ))}
                </div>
              </Link>
            ))}
          </div>
        ) : (
          <div className="text-center py-20">
            <p className="font-heading text-2xl text-ink mb-2">Пока нет проектов</p>
            <p className="font-body text-muted mb-6">
              Создайте первый — это займёт меньше минуты
            </p>
            <Link href="/new" className="btn-primary">
              Создать проект
            </Link>
          </div>
        )}
      </div>
    </div>
  )
}
