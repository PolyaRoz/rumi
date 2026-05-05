import { NextRequest, NextResponse } from 'next/server'
import { fal } from '@fal-ai/client'
import { type StyleType } from '@/lib/promptBuilder'

fal.config({ credentials: process.env.FAL_KEY })

interface FloorplanRequest {
  planUrl: string   // fal.ai storage URL загруженного плана
  style: StyleType
}

const STYLE_3D: Record<StyleType, string> = {
  scandi:  'Scandinavian interior design, light oak hardwood floors, white walls, natural linen textiles, minimalist Nordic hygge aesthetic, warm ambient lighting',
  minimal: 'minimalist interior design, polished light concrete floors, white and grey monochrome palette, clean geometric lines, understated luxury',
  loft:    'industrial loft interior, dark walnut wood floors, exposed brick walls, metal pipe accents, Edison bulb warm lighting, urban style',
  classic: 'classic elegant interior design, herringbone parquet oak floors, cream and warm gold palette, crown moldings, refined traditional décor',
}

function buildPrompt(style: StyleType): string {
  const styleDesc = STYLE_3D[style]

  return [
    'Ultra-photorealistic 3D architectural visualization,',
    'perfect top-down bird\'s-eye aerial view of a fully furnished modern apartment,',
    'walls cut away horizontally revealing complete interior layout from above.',
    styleDesc + '.',
    'Living room: large L-shaped corner sectional sofa in warm terracotta-beige fabric,',
    'matching accent armchair, oval glass coffee table on geometric area rug,',
    'slim low TV console unit with decor, floor lamp, green indoor plants.',
    'Bedroom: premium double bed with upholstered headboard and plump pillows,',
    'two matching wooden bedside tables with table lamps, large built-in sliding wardrobe,',
    'soft rug beside bed, reading armchair in corner.',
    'Kitchen and dining area: modern modular kitchen cabinets along wall with stone countertop,',
    'rectangular dining table for four with matching chairs, stylish pendant lights above.',
    'Additional room: single bed, study desk with chair, bookshelf, colorful rug.',
    'All rooms richly furnished. Light hardwood floors visible throughout.',
    'White walls and ceiling. Large windows with natural daylight streaming in.',
    'Perfect top-down perspective. Professional 3D architectural rendering.',
    'Ultra-sharp detail, realistic materials and textures, warm ambient lighting, 8K resolution.',
    'Architectural Digest and Dezeen magazine quality. No text, no labels, no annotations.',
  ].join(' ')
}

export async function POST(req: NextRequest) {
  if (!process.env.FAL_KEY) {
    return NextResponse.json({ error: 'FAL_KEY не настроен', code: 'NO_KEY' }, { status: 500 })
  }

  let body: FloorplanRequest
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: 'Неверный формат запроса' }, { status: 400 })
  }

  const { planUrl, style } = body
  if (!planUrl) {
    return NextResponse.json({ error: 'planUrl обязателен' }, { status: 400 })
  }

  const prompt = buildPrompt(style)
  console.log('[floorplan] style:', style)
  console.log('[floorplan] prompt[:120]:', prompt.slice(0, 120))

  try {
    // img2img: берём загруженный план как основу структуры,
    // strength 0.92 — AI максимально перерисовывает в 3D сохраняя планировку
    const result = await fal.subscribe('fal-ai/flux/dev/image-to-image', {
      input: {
        prompt,
        image_url: planUrl,
        strength: 0.92,
        num_inference_steps: 28,
        guidance_scale: 7,
        num_images: 1,
      } as any,
      logs: false,
    })

    const imageUrl: string = (result.data as any).images?.[0]?.url
    if (!imageUrl) {
      throw new Error('fal.ai не вернул изображение')
    }

    return NextResponse.json({ imageUrl, prompt, style })
  } catch (err: any) {
    console.error('[floorplan] fal.ai error:', err)

    // Fallback: если img2img недоступен — генерируем text-to-image
    try {
      console.log('[floorplan] falling back to text-to-image...')
      const result2 = await fal.subscribe('fal-ai/flux/schnell', {
        input: {
          prompt,
          image_size: 'square_hd',
          num_inference_steps: 4,
          num_images: 1,
        },
        logs: false,
      })
      const imageUrl2: string = (result2.data as any).images?.[0]?.url
      if (!imageUrl2) throw new Error('No image from fallback')
      return NextResponse.json({ imageUrl: imageUrl2, prompt, style, fallback: true })
    } catch (err2: any) {
      return NextResponse.json(
        { error: err?.message ?? 'Ошибка генерации', code: 'FAL_ERROR' },
        { status: 500 }
      )
    }
  }
}
