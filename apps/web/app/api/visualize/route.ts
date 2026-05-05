import { NextRequest, NextResponse } from 'next/server'
import * as fal from '@fal-ai/client'
import { buildPrompt, type VisualizationRequest } from '@/lib/promptBuilder'

// fal.ai конфигурация
fal.config({
  credentials: process.env.FAL_KEY,
})

export async function POST(req: NextRequest) {
  // Проверяем API ключ
  if (!process.env.FAL_KEY) {
    return NextResponse.json(
      { error: 'FAL_KEY не настроен в .env.local', code: 'NO_KEY' },
      { status: 500 }
    )
  }

  let body: VisualizationRequest
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: 'Неверный формат запроса' }, { status: 400 })
  }

  const prompt = buildPrompt(body)

  console.log(`[visualize] room=${body.room} style=${body.style}`)
  console.log(`[visualize] prompt: ${prompt.slice(0, 120)}...`)

  try {
    const result = await fal.subscribe('fal-ai/flux/schnell', {
      input: {
        prompt,
        image_size: 'landscape_16_9', // 16:9 — идеально для интерьеров
        num_inference_steps: 4,       // schnell = 4 шага, ~1-2 сек
        num_images: 1,
        enable_safety_checker: true,
      },
      logs: false,
    })

    const imageUrl: string = (result.data as any).images?.[0]?.url
    if (!imageUrl) {
      return NextResponse.json({ error: 'Изображение не получено от fal.ai' }, { status: 500 })
    }

    return NextResponse.json({
      imageUrl,
      prompt, // возвращаем для отладки
      room: body.room,
      style: body.style,
    })
  } catch (err: any) {
    console.error('[visualize] fal.ai error:', err)
    return NextResponse.json(
      { error: err?.message ?? 'Ошибка генерации', code: 'FAL_ERROR' },
      { status: 500 }
    )
  }
}
