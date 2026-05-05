/**
 * DEPRECATED: AI img2img рендер плана квартиры.
 *
 * Этот endpoint удалён из pipeline — он был корнем проблемы "walls drift":
 *  - strength=0.92 давал AI право перерисовать 92% изображения
 *  - стены, окна и двери смещались между генерациями
 *  - render-style менялся между запусками
 *
 * Новая архитектура (см. spec, правило C):
 *  1. /api/v1/plan/analyze → locked geometry JSON (CV-пайплайн, OpenCV)
 *  2. /api/v1/plan/place-furniture → validated layout JSON (rule-based)
 *  3. <TopDownPlanRenderer> на фронтенде → детерминированный Canvas-рендер
 *
 * Если кто-то всё ещё вызывает этот endpoint — возвращаем 410 Gone.
 */

import { NextResponse } from 'next/server'

export async function POST() {
  return NextResponse.json(
    {
      error: 'Этот endpoint удалён. Используйте /api/v1/plan/analyze + клиентский TopDownPlanRenderer.',
      code: 'DEPRECATED',
      migration: {
        old: 'POST /api/floorplan { planUrl, style }',
        new_pipeline: [
          'POST /api/v1/plan/analyze (multipart: image_url или file)',
          'User confirms geometry on /analysis page',
          'POST /api/v1/plan/place-furniture (geometry + style + budget)',
          'Render via <TopDownPlanRenderer> Canvas component',
        ],
      },
    },
    { status: 410 }
  )
}
