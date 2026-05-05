import type { Metadata } from 'next'
import './globals.css'
import { Providers } from './providers'

export const metadata: Metadata = {
  title: 'Руми — AI-дизайн интерьера',
  description:
    'Загрузите фото комнаты, укажите бюджет — Руми подберёт мебель и покажет готовый результат',
  keywords: ['дизайн интерьера', 'AI', 'мебель', 'смета', 'обустройство квартиры'],
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="ru">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  )
}
