'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useMutation } from '@tanstack/react-query'
import { login, register } from '@/lib/auth'
import { useAuthStore } from '@/store/authStore'

// ── Схемы валидации ───────────────────────────────────────────────────────────

const loginSchema = z.object({
  email: z.string().email('Введите корректный email'),
  password: z.string().min(1, 'Введите пароль'),
})

const registerSchema = z.object({
  name: z.string().min(2, 'Имя — минимум 2 символа').max(100),
  email: z.string().email('Введите корректный email'),
  password: z.string().min(8, 'Пароль — минимум 8 символов'),
  passwordConfirm: z.string(),
}).refine((d) => d.password === d.passwordConfirm, {
  message: 'Пароли не совпадают',
  path: ['passwordConfirm'],
})

type LoginForm = z.infer<typeof loginSchema>
type RegisterForm = z.infer<typeof registerSchema>

// ── Компонент ─────────────────────────────────────────────────────────────────

export default function AuthPage() {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const router = useRouter()
  const setUser = useAuthStore((s) => s.setUser)

  // Форма входа
  const loginForm = useForm<LoginForm>({
    resolver: zodResolver(loginSchema),
  })

  // Форма регистрации
  const registerForm = useForm<RegisterForm>({
    resolver: zodResolver(registerSchema),
  })

  // Мутации
  const loginMutation = useMutation({
    mutationFn: login,
    onSuccess: (data) => {
      setUser(data.user)
      router.push('/upload')
    },
  })

  const registerMutation = useMutation({
    mutationFn: register,
    onSuccess: (data) => {
      setUser(data.user)
      router.push('/upload')
    },
  })

  const error = loginMutation.error || registerMutation.error

  return (
    <div className="min-h-screen bg-paper flex">
      {/* Левая часть — форма */}
      <div className="flex-1 flex flex-col justify-center px-8 py-12 max-w-md mx-auto w-full">
        {/* Логотип */}
        <div className="flex items-center gap-2 mb-10">
          <div className="w-2.5 h-2.5 rounded-full bg-terracotta" />
          <span className="font-heading text-2xl font-bold text-ink">Руми</span>
        </div>

        {/* Заголовок */}
        <h1 className="font-heading text-4xl font-semibold text-ink mb-2">
          {mode === 'login' ? 'С возвращением' : 'Создайте аккаунт'}
        </h1>
        <p className="text-muted font-body text-sm mb-8">
          {mode === 'login'
            ? 'Войдите, чтобы продолжить работу'
            : 'Первый проект — бесплатно'}
        </p>

        {/* Ошибка */}
        {error && (
          <div className="mb-4 px-4 py-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm font-body">
            {(error as any)?.response?.data?.detail ?? 'Что-то пошло не так'}
          </div>
        )}

        {mode === 'login' ? (
          /* ── Форма входа ── */
          <form
            onSubmit={loginForm.handleSubmit((d) => loginMutation.mutate(d))}
            className="space-y-4"
          >
            <div>
              <label className="block text-sm font-medium text-ink mb-1.5 font-body">
                Email
              </label>
              <input
                {...loginForm.register('email')}
                type="email"
                placeholder="you@example.com"
                className="input"
                autoComplete="email"
              />
              {loginForm.formState.errors.email && (
                <p className="mt-1 text-xs text-red-600">
                  {loginForm.formState.errors.email.message}
                </p>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-ink mb-1.5 font-body">
                Пароль
              </label>
              <input
                {...loginForm.register('password')}
                type="password"
                placeholder="••••••••"
                className="input"
                autoComplete="current-password"
              />
              {loginForm.formState.errors.password && (
                <p className="mt-1 text-xs text-red-600">
                  {loginForm.formState.errors.password.message}
                </p>
              )}
            </div>

            <button
              type="submit"
              className="btn-primary w-full"
              disabled={loginMutation.isPending}
            >
              {loginMutation.isPending ? 'Входим...' : 'Войти'}
            </button>
          </form>
        ) : (
          /* ── Форма регистрации ── */
          <form
            onSubmit={registerForm.handleSubmit((d) => registerMutation.mutate(d))}
            className="space-y-4"
          >
            <div>
              <label className="block text-sm font-medium text-ink mb-1.5 font-body">
                Имя
              </label>
              <input
                {...registerForm.register('name')}
                type="text"
                placeholder="Как вас зовут?"
                className="input"
                autoComplete="name"
              />
              {registerForm.formState.errors.name && (
                <p className="mt-1 text-xs text-red-600">
                  {registerForm.formState.errors.name.message}
                </p>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-ink mb-1.5 font-body">
                Email
              </label>
              <input
                {...registerForm.register('email')}
                type="email"
                placeholder="you@example.com"
                className="input"
                autoComplete="email"
              />
              {registerForm.formState.errors.email && (
                <p className="mt-1 text-xs text-red-600">
                  {registerForm.formState.errors.email.message}
                </p>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-ink mb-1.5 font-body">
                Пароль
              </label>
              <input
                {...registerForm.register('password')}
                type="password"
                placeholder="Минимум 8 символов"
                className="input"
                autoComplete="new-password"
              />
              {registerForm.formState.errors.password && (
                <p className="mt-1 text-xs text-red-600">
                  {registerForm.formState.errors.password.message}
                </p>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-ink mb-1.5 font-body">
                Повторите пароль
              </label>
              <input
                {...registerForm.register('passwordConfirm')}
                type="password"
                placeholder="••••••••"
                className="input"
                autoComplete="new-password"
              />
              {registerForm.formState.errors.passwordConfirm && (
                <p className="mt-1 text-xs text-red-600">
                  {registerForm.formState.errors.passwordConfirm.message}
                </p>
              )}
            </div>

            <button
              type="submit"
              className="btn-primary w-full"
              disabled={registerMutation.isPending}
            >
              {registerMutation.isPending ? 'Создаём аккаунт...' : 'Начать бесплатно'}
            </button>

            <p className="text-xs text-muted text-center font-body">
              Регистрируясь, вы соглашаетесь с условиями использования
            </p>
          </form>
        )}

        {/* Переключение режима */}
        <div className="mt-6 text-center">
          <span className="text-sm text-muted font-body">
            {mode === 'login' ? 'Нет аккаунта? ' : 'Уже есть аккаунт? '}
          </span>
          <button
            onClick={() => setMode(mode === 'login' ? 'register' : 'login')}
            className="text-sm text-terracotta font-medium font-body hover:underline"
          >
            {mode === 'login' ? 'Зарегистрироваться' : 'Войти'}
          </button>
        </div>
      </div>

      {/* Правая часть — декоративная */}
      <div className="hidden lg:block flex-1 bg-cream relative overflow-hidden">
        <div className="absolute inset-0 flex flex-col items-center justify-center p-16 text-center">
          <blockquote className="font-heading text-3xl font-medium text-ink leading-snug mb-6">
            «Дом — это не то,<br />где ты живёшь.<br />
            Это то, как ты себя чувствуешь»
          </blockquote>
          <p className="text-muted font-body text-sm">Руми, XIII век</p>
        </div>
        {/* Декоративные круги */}
        <div className="absolute -bottom-20 -right-20 w-96 h-96 rounded-full bg-terracotta/10" />
        <div className="absolute -top-10 -left-10 w-64 h-64 rounded-full bg-sage/10" />
      </div>
    </div>
  )
}
