/**
 * Per-room photo generation via fal.ai с FIXED render-style template.
 *
 * АРХИТЕКТУРА:
 *  - Промпт строится через renderInstructionBuilder с ФИКСИРОВАННЫМ шаблоном
 *    рендера (правило F: render style stable across regenerations)
 *  - User-style влияет ТОЛЬКО на палитру материалов (правило G)
 *  - Furniture передаётся ТОЛЬКО из validated catalog placement
 *    (правила B, D, E)
 *  - Seed детерминирован: один и тот же layout → одинаковая картинка
 *  - Negative prompt запрещает AI добавлять окна, передвигать двери, etc.
 */

import { NextRequest, NextResponse } from 'next/server'
import { fal } from '@fal-ai/client'
import {
  buildPerRoomPhotoInstruction,
  type StyleKey,
  type PerRoomLockedContext,
  type FurnitureNameDim,
} from '@/lib/renderInstructionBuilder'

fal.config({ credentials: process.env.FAL_KEY })

interface VisualizeRequest {
  // Тип комнаты для маппинга в English
  room: string
  // Стиль (только палитра материалов)
  style: StyleKey
  // Validated catalog items (имена + размеры)
  furniture: { name: string; category: string; width_m?: number; depth_m?: number }[]
  // Locked-контекст из geometry JSON
  locked?: {
    room_label?: string
    area_m2?: number | null
    placed_count?: number
  }
}

// Маппинг старых RoomType → RoomLabel для совместимости с фронтом
const LEGACY_ROOM_MAP: Record<string, string> = {
  living:  'living_room',
  bedroom: 'bedroom',
  kitchen: 'kitchen',
  kids:    'kids_room',
  hallway: 'corridor',
}

export async function POST(req: NextRequest) {
  if (!process.env.FAL_KEY) {
    return NextResponse.json(
      { error: 'FAL_KEY не настроен в .env.local', code: 'NO_KEY' },
      { status: 500 }
    )
  }

  let body: VisualizeRequest
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: 'Неверный формат запроса' }, { status: 400 })
  }

  // Locked-контекст: из body.locked или маппинга из легаси-room
  const roomLabel = body.locked?.room_label ?? LEGACY_ROOM_MAP[body.room] ?? 'unknown'
  const lockedContext: PerRoomLockedContext = {
    room_label:    roomLabel,
    area_m2:       body.locked?.area_m2 ?? null,
    placed_count:  body.locked?.placed_count ?? body.furniture.length,
  }

  // Validated catalog items
  const furniture: FurnitureNameDim[] = body.furniture.map(f => ({
    name: f.name,
    category: f.category,
    width_m: f.width_m,
    depth_m: f.depth_m,
  }))

  // ── Построить ФИКСИРОВАННУЮ инструкцию ────────────────────────────────────
  const instruction = buildPerRoomPhotoInstruction(
    lockedContext,
    furniture,
    body.style,
  )

  console.log(`[visualize] room=${roomLabel} style=${body.style} seed=${instruction.seed}`)
  console.log(`[visualize] locked: ${instruction.locked_constraints.join(', ')}`)
  console.log(`[visualize] prompt[:150]: ${instruction.prompt.slice(0, 150)}...`)

  try {
    const result = await fal.subscribe('fal-ai/flux/schnell', {
      input: {
        prompt: instruction.prompt,
        // ФИКСИРОВАННЫЕ параметры — стабильность render-style
        image_size: 'landscape_16_9',
        num_inference_steps: 4,
        num_images: 1,
        seed: instruction.seed,                     // детерминированный
        enable_safety_checker: true,
      } as any,
      logs: false,
    })

    const imageUrl: string = (result.data as any).images?.[0]?.url
    if (!imageUrl) {
      return NextResponse.json({ error: 'Изображение не получено от fal.ai' }, { status: 500 })
    }

    return NextResponse.json({
      imageUrl,
      prompt: instruction.prompt,
      seed: instruction.seed,
      render_style_id: instruction.render_style_id,
      locked_constraints: instruction.locked_constraints,
      room: roomLabel,
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
