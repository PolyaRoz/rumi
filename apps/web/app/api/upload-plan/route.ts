import { NextRequest, NextResponse } from 'next/server'
import { fal } from '@fal-ai/client'

fal.config({ credentials: process.env.FAL_KEY })

export async function POST(req: NextRequest) {
  if (!process.env.FAL_KEY) {
    return NextResponse.json({ error: 'FAL_KEY не настроен', code: 'NO_KEY' }, { status: 500 })
  }

  try {
    const formData = await req.formData()
    const file = formData.get('file') as File | null

    if (!file) {
      return NextResponse.json({ error: 'Файл не передан' }, { status: 400 })
    }

    // Загружаем в fal.ai storage — возвращает публичный URL
    const url = await fal.storage.upload(file)

    return NextResponse.json({ url })
  } catch (err: any) {
    console.error('[upload-plan] error:', err)
    return NextResponse.json({ error: err?.message ?? 'Ошибка загрузки' }, { status: 500 })
  }
}
