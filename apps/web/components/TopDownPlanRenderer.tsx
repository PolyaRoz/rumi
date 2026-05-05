'use client'

/**
 * ДЕТЕРМИНИРОВАННЫЙ Top-Down рендерер плана квартиры.
 *
 * Это КЛЮЧЕВОЙ компонент архитектуры:
 * Он рендерит финальную визуализацию ПРЯМО из locked geometry JSON + placement JSON,
 * БЕЗ участия генеративной модели.
 *
 * Почему это важно:
 *  - AI больше не имеет шанса передвинуть стены (правило C)
 *  - AI больше не может изобрести мебель (правило D)
 *  - AI больше не меняет размеры (правило E)
 *  - Render-style 100% стабилен между генерациями (правило F)
 *  - Один и тот же JSON → один и тот же пиксель (правило успеха #1)
 *
 * Поддерживает 2 режима:
 *  - 'plan'      — чисто 2D top-down план (для технической точности)
 *  - 'isometric' — 3D-look через изометрическую проекцию (для презентации)
 *
 * User-style (scandi/loft/etc) влияет ТОЛЬКО на цветовую палитру материалов,
 * НЕ на формат рендера.
 */

import { useEffect, useRef } from 'react'
import type {
  ApartmentGeometry,
  FurniturePlacement,
  PlacedFurniture,
  Point,
  Room,
  Wall,
} from '@/store/geometryStore'
import { ROOM_LABEL_RU } from '@/store/geometryStore'

type StyleKey = 'scandi' | 'minimal' | 'loft' | 'classic'
type RenderMode = 'plan' | 'isometric'

interface Props {
  geometry: ApartmentGeometry
  placement: FurniturePlacement | null
  catalog?: Map<string, { name: string; category: string; image_url?: string }>
  style: StyleKey
  mode?: RenderMode
  showLabels?: boolean      // показывать ли названия комнат
  showFurnitureLabels?: boolean
  onCanvasReady?: (canvas: HTMLCanvasElement) => void
  className?: string
}

// ─── ФИКСИРОВАННЫЕ render-параметры (правило F: render style is fixed) ───────

const FIXED_RENDER = {
  // Размеры canvas — фиксированы для стабильности
  outputWidth: 1200,
  outputHeight: 1200,

  // Изометрическая проекция (правило: top-down 3D isometric)
  isometricAngle: 30,        // градусов от горизонтали
  wallHeightPx: 60,          // высота стен в пикселях

  // Стены — всегда одинаковые
  wallStrokeWidth: 1,        // обводка
  wallShadowBlur: 4,
  wallShadowColor: 'rgba(0,0,0,0.10)',

  // Мебель — обводка
  furnitureStrokeWidth: 1.2,
  furnitureCornerRadius: 4,

  // Шрифты
  labelFont: '13px "Onest", sans-serif',
  labelColor: '#1C1917',
}

// ─── User-style → ТОЛЬКО палитра материалов ──────────────────────────────────
// Render-format не меняется. Меняются только цвета пола, стен, мебели.

const STYLE_PALETTES: Record<StyleKey, {
  background: string
  floor: string
  wallFace: string
  wallTop: string
  wallShadow: string
  furniture: string
  furnitureStroke: string
  accent: string
  rugFill: string
  doorFill: string
  windowFill: string
}> = {
  scandi: {
    background:      '#FAF7F2',
    floor:           '#E8D8C0',
    wallFace:        '#F5EFE6',
    wallTop:         '#3C342B',
    wallShadow:      '#9C8B7A',
    furniture:       '#D4B896',
    furnitureStroke: '#7A6043',
    accent:          '#C97052',
    rugFill:         '#E8C896',
    doorFill:        '#B8946C',
    windowFill:      '#A8C8E0',
  },
  minimal: {
    background:      '#FFFFFF',
    floor:           '#E5E5E5',
    wallFace:        '#FAFAFA',
    wallTop:         '#1A1A1A',
    wallShadow:      '#888888',
    furniture:       '#CCCCCC',
    furnitureStroke: '#444444',
    accent:          '#000000',
    rugFill:         '#DDDDDD',
    doorFill:        '#999999',
    windowFill:      '#9CB8D0',
  },
  loft: {
    background:      '#F0EBE3',
    floor:           '#5C4530',
    wallFace:        '#A89280',
    wallTop:         '#2A1F18',
    wallShadow:      '#1F1610',
    furniture:       '#7A5C42',
    furnitureStroke: '#2A1F14',
    accent:          '#B85A2D',
    rugFill:         '#9C7050',
    doorFill:        '#3C2A1C',
    windowFill:      '#7C9CBC',
  },
  classic: {
    background:      '#F8F2E8',
    floor:           '#C49968',
    wallFace:        '#F0E5D2',
    wallTop:         '#2A2018',
    wallShadow:      '#A89070',
    furniture:       '#9C6B3D',
    furnitureStroke: '#3C2410',
    accent:          '#A0825C',
    rugFill:         '#D8B888',
    doorFill:        '#7A5028',
    windowFill:      '#B0C8E0',
  },
}

// ─── Цвета мебели по категориям (валидируются из каталога) ───────────────────

const CATEGORY_COLORS: Record<string, { fill: string; alpha: number }> = {
  sofa:        { fill: 'accent',     alpha: 0.85 },
  armchair:    { fill: 'accent',     alpha: 0.70 },
  bed:         { fill: 'furniture',  alpha: 0.95 },
  wardrobe:    { fill: 'furniture',  alpha: 0.95 },
  dresser:     { fill: 'furniture',  alpha: 0.85 },
  nightstand:  { fill: 'furniture',  alpha: 0.80 },
  table:       { fill: 'furniture',  alpha: 0.75 },
  chair:       { fill: 'furniture',  alpha: 0.65 },
  rug:         { fill: 'rugFill',    alpha: 0.55 },
  ottoman:     { fill: 'accent',     alpha: 0.55 },
  tv_unit:     { fill: 'furniture',  alpha: 0.85 },
  bookshelf:   { fill: 'furniture',  alpha: 0.90 },
  desk:        { fill: 'furniture',  alpha: 0.80 },
  kitchen_set: { fill: 'furniture',  alpha: 0.95 },
}

// ─── Утилиты ─────────────────────────────────────────────────────────────────

function getCategoryFromItemId(itemId: string, catalog?: Props['catalog']): string {
  return catalog?.get(itemId)?.category ?? 'furniture'
}

function getCategoryName(itemId: string, catalog?: Props['catalog']): string {
  return catalog?.get(itemId)?.name ?? itemId
}

interface RenderTransform {
  scale:      number
  offsetX:    number
  offsetY:    number
  imgWidth:   number
  imgHeight:  number
}

function computeFitTransform(
  geometry: ApartmentGeometry,
  outputWidth: number,
  outputHeight: number,
  margin: number = 60,
): RenderTransform {
  const imgW = geometry.source_image_width_px
  const imgH = geometry.source_image_height_px
  const scale = Math.min(
    (outputWidth - margin * 2) / imgW,
    (outputHeight - margin * 2) / imgH,
  )
  const renderedW = imgW * scale
  const renderedH = imgH * scale
  return {
    scale,
    offsetX: (outputWidth - renderedW) / 2,
    offsetY: (outputHeight - renderedH) / 2,
    imgWidth: imgW,
    imgHeight: imgH,
  }
}

/** Пересчитать координаты из image-space в canvas-space. */
function px(p: Point, t: RenderTransform): { x: number; y: number } {
  return {
    x: p.x * t.scale + t.offsetX,
    y: p.y * t.scale + t.offsetY,
  }
}

// ─── Изометрическая проекция ─────────────────────────────────────────────────
// Стандартная axonometric: x' = (x - y) * cos(30), y' = (x + y) * sin(30)
// Это даёт стабильный 30-градусный elevation angle (правило render style).

function isoProject(
  x: number, y: number, z: number = 0,
  centerX: number = 0, centerY: number = 0,
): { x: number; y: number } {
  const angle = (FIXED_RENDER.isometricAngle * Math.PI) / 180
  const cos = Math.cos(angle)
  const sin = Math.sin(angle)
  const dx = x - centerX
  const dy = y - centerY
  return {
    x: centerX + (dx - dy) * cos,
    y: centerY + (dx + dy) * sin - z,
  }
}

// ─── Rendering helpers ───────────────────────────────────────────────────────

function fillBackground(ctx: CanvasRenderingContext2D, w: number, h: number, color: string) {
  ctx.fillStyle = color
  ctx.fillRect(0, 0, w, h)
}

function drawFloorPolygon(
  ctx: CanvasRenderingContext2D,
  rooms: Room[],
  t: RenderTransform,
  floorColor: string,
  shadowColor: string,
  isometric: boolean,
) {
  for (const room of rooms) {
    if (room.polygon.length < 3) continue
    ctx.beginPath()
    for (let i = 0; i < room.polygon.length; i++) {
      const p = px(room.polygon[i], t)
      let drawX = p.x
      let drawY = p.y
      if (isometric) {
        const proj = isoProject(p.x, p.y, 0, FIXED_RENDER.outputWidth / 2, FIXED_RENDER.outputHeight / 2)
        drawX = proj.x
        drawY = proj.y
      }
      if (i === 0) ctx.moveTo(drawX, drawY)
      else ctx.lineTo(drawX, drawY)
    }
    ctx.closePath()
    ctx.fillStyle = floorColor
    ctx.fill()
    ctx.strokeStyle = shadowColor + '40'
    ctx.lineWidth = 0.5
    ctx.stroke()
  }
}

function drawWalls(
  ctx: CanvasRenderingContext2D,
  walls: Wall[],
  openings: ApartmentGeometry['openings'],
  t: RenderTransform,
  wallTop: string,
  wallFace: string,
  wallShadow: string,
  isometric: boolean,
) {
  // Группируем openings по wall_id для пропусков в стенах
  const openingsByWall = new Map<string, ApartmentGeometry['openings']>()
  for (const opening of openings) {
    const arr = openingsByWall.get(opening.wall_id) ?? []
    arr.push(opening)
    openingsByWall.set(opening.wall_id, arr)
  }

  for (const wall of walls) {
    const start = px(wall.start, t)
    const end   = px(wall.end, t)
    const thicknessPx = Math.max(2, wall.thickness_px * t.scale * 0.6)

    // Длина и направление
    const dx = end.x - start.x
    const dy = end.y - start.y
    const length = Math.hypot(dx, dy)
    if (length === 0) continue

    // Перпендикулярный вектор для толщины стены
    const nx = -dy / length
    const ny = dx / length
    const halfT = thicknessPx / 2

    // 4 угла стены-как-прямоугольника
    const cornerA = { x: start.x + nx * halfT, y: start.y + ny * halfT }
    const cornerB = { x: end.x   + nx * halfT, y: end.y   + ny * halfT }
    const cornerC = { x: end.x   - nx * halfT, y: end.y   - ny * halfT }
    const cornerD = { x: start.x - nx * halfT, y: start.y - ny * halfT }

    const projectIfIso = (p: { x: number; y: number }, z: number = 0) => {
      if (!isometric) return p
      return isoProject(p.x, p.y, z, FIXED_RENDER.outputWidth / 2, FIXED_RENDER.outputHeight / 2)
    }

    // Изометрический режим: стены имеют высоту wallHeightPx
    if (isometric) {
      // Тень от стены (нижняя часть)
      ctx.beginPath()
      const sa = projectIfIso(cornerA, 0)
      const sb = projectIfIso(cornerB, 0)
      const sc = projectIfIso(cornerC, 0)
      const sd = projectIfIso(cornerD, 0)
      ctx.moveTo(sa.x, sa.y)
      ctx.lineTo(sb.x, sb.y)
      ctx.lineTo(sc.x, sc.y)
      ctx.lineTo(sd.x, sd.y)
      ctx.closePath()
      ctx.fillStyle = wallTop
      ctx.fill()

      // Боковая грань (стена видимая сбоку)
      const ta = projectIfIso(cornerA, FIXED_RENDER.wallHeightPx)
      const tb = projectIfIso(cornerB, FIXED_RENDER.wallHeightPx)
      const tc = projectIfIso(cornerC, FIXED_RENDER.wallHeightPx)
      const td = projectIfIso(cornerD, FIXED_RENDER.wallHeightPx)

      // Передняя грань (вид со стороны комнаты)
      ctx.beginPath()
      ctx.moveTo(sa.x, sa.y)
      ctx.lineTo(sb.x, sb.y)
      ctx.lineTo(tb.x, tb.y)
      ctx.lineTo(ta.x, ta.y)
      ctx.closePath()
      ctx.fillStyle = wallFace
      ctx.fill()
      ctx.strokeStyle = wallShadow
      ctx.lineWidth = 0.5
      ctx.stroke()

      // Верхняя грань
      ctx.beginPath()
      ctx.moveTo(ta.x, ta.y)
      ctx.lineTo(tb.x, tb.y)
      ctx.lineTo(tc.x, tc.y)
      ctx.lineTo(td.x, td.y)
      ctx.closePath()
      ctx.fillStyle = wallTop
      ctx.fill()
    } else {
      // Plain top-down: просто прямоугольник стены
      ctx.beginPath()
      ctx.moveTo(cornerA.x, cornerA.y)
      ctx.lineTo(cornerB.x, cornerB.y)
      ctx.lineTo(cornerC.x, cornerC.y)
      ctx.lineTo(cornerD.x, cornerD.y)
      ctx.closePath()
      ctx.fillStyle = wallTop
      ctx.fill()
    }
  }
}

function drawOpenings(
  ctx: CanvasRenderingContext2D,
  openings: ApartmentGeometry['openings'],
  t: RenderTransform,
  doorColor: string,
  windowColor: string,
  isometric: boolean,
) {
  for (const op of openings) {
    const center = px(op.position, t)
    const widthPx = op.width_px * t.scale

    let drawX = center.x, drawY = center.y
    if (isometric) {
      const proj = isoProject(center.x, center.y, 0, FIXED_RENDER.outputWidth / 2, FIXED_RENDER.outputHeight / 2)
      drawX = proj.x
      drawY = proj.y
    }

    if (op.type === 'door') {
      // Дверь — прямоугольник с дугой
      ctx.fillStyle = doorColor
      ctx.fillRect(drawX - widthPx / 2, drawY - 3, widthPx, 6)
      ctx.beginPath()
      ctx.arc(drawX - widthPx / 2, drawY, widthPx, 0, Math.PI / 2)
      ctx.strokeStyle = doorColor
      ctx.lineWidth = 1
      ctx.stroke()
    } else {
      // Окно — двойная линия
      ctx.fillStyle = windowColor
      ctx.fillRect(drawX - widthPx / 2, drawY - 4, widthPx, 8)
      ctx.strokeStyle = windowColor
      ctx.lineWidth = 1.5
      ctx.beginPath()
      ctx.moveTo(drawX - widthPx / 2, drawY)
      ctx.lineTo(drawX + widthPx / 2, drawY)
      ctx.stroke()
    }
  }
}

function drawFurniture(
  ctx: CanvasRenderingContext2D,
  placement: FurniturePlacement,
  t: RenderTransform,
  catalog: Props['catalog'],
  palette: typeof STYLE_PALETTES[StyleKey],
  isometric: boolean,
) {
  for (const rl of placement.rooms) {
    for (const item of rl.placed_items) {
      const category = getCategoryFromItemId(item.item_id, catalog)
      const colorRule = CATEGORY_COLORS[category] ?? { fill: 'furniture', alpha: 0.8 }
      const fill = palette[colorRule.fill as keyof typeof palette] ?? palette.furniture

      drawFurnitureItem(ctx, item, t, fill, palette.furnitureStroke, colorRule.alpha, isometric)
    }
  }
}

function drawFurnitureItem(
  ctx: CanvasRenderingContext2D,
  item: PlacedFurniture,
  t: RenderTransform,
  fill: string,
  stroke: string,
  alpha: number,
  isometric: boolean,
) {
  const x = item.position.x * t.scale + t.offsetX
  const y = item.position.y * t.scale + t.offsetY
  const w = item.width_px * t.scale
  const h = item.depth_px * t.scale

  // Центр для поворота
  const cx = x + w / 2
  const cy = y + h / 2

  ctx.save()
  ctx.globalAlpha = alpha

  if (isometric) {
    const proj = isoProject(cx, cy, 0, FIXED_RENDER.outputWidth / 2, FIXED_RENDER.outputHeight / 2)
    ctx.translate(proj.x, proj.y)
    // Изометрический поворот: оси x и y скошены
    const angleRad = (item.rotation_deg * Math.PI) / 180
    ctx.rotate(angleRad)
    ctx.scale(1, 0.5)  // изометрическое сжатие по вертикали
  } else {
    ctx.translate(cx, cy)
    ctx.rotate((item.rotation_deg * Math.PI) / 180)
  }

  // Рисуем прямоугольник предмета
  const r = FIXED_RENDER.furnitureCornerRadius
  ctx.beginPath()
  ctx.moveTo(-w/2 + r, -h/2)
  ctx.lineTo(w/2 - r, -h/2)
  ctx.quadraticCurveTo(w/2, -h/2, w/2, -h/2 + r)
  ctx.lineTo(w/2, h/2 - r)
  ctx.quadraticCurveTo(w/2, h/2, w/2 - r, h/2)
  ctx.lineTo(-w/2 + r, h/2)
  ctx.quadraticCurveTo(-w/2, h/2, -w/2, h/2 - r)
  ctx.lineTo(-w/2, -h/2 + r)
  ctx.quadraticCurveTo(-w/2, -h/2, -w/2 + r, -h/2)
  ctx.closePath()

  ctx.fillStyle = fill
  ctx.fill()
  ctx.strokeStyle = stroke
  ctx.lineWidth = FIXED_RENDER.furnitureStrokeWidth
  ctx.stroke()

  ctx.restore()
}

function drawRoomLabels(
  ctx: CanvasRenderingContext2D,
  rooms: Room[],
  t: RenderTransform,
  isometric: boolean,
) {
  ctx.font = FIXED_RENDER.labelFont
  ctx.fillStyle = FIXED_RENDER.labelColor
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'

  for (const room of rooms) {
    if (!room.centroid) continue
    const c = px(room.centroid, t)
    let drawX = c.x, drawY = c.y
    if (isometric) {
      const proj = isoProject(c.x, c.y, 0, FIXED_RENDER.outputWidth / 2, FIXED_RENDER.outputHeight / 2)
      drawX = proj.x
      drawY = proj.y
    }

    const label = ROOM_LABEL_RU[room.label] ?? room.label
    const area = room.area_m2 ? `${room.area_m2.toFixed(1)} м²` : ''

    // Полупрозрачный фон под текстом
    const text = label
    const metrics = ctx.measureText(text)
    const padding = 6
    const bgW = metrics.width + padding * 2
    const bgH = 20

    ctx.fillStyle = 'rgba(255,255,255,0.85)'
    ctx.fillRect(drawX - bgW / 2, drawY - bgH / 2, bgW, bgH)

    ctx.fillStyle = FIXED_RENDER.labelColor
    ctx.fillText(text, drawX, drawY - 1)

    if (area) {
      ctx.font = '10px "Onest", sans-serif'
      ctx.fillStyle = '#7A6043'
      ctx.fillText(area, drawX, drawY + 12)
      ctx.font = FIXED_RENDER.labelFont
    }
  }
}

// ─── Main render function ────────────────────────────────────────────────────

function renderToCanvas(
  ctx: CanvasRenderingContext2D,
  geometry: ApartmentGeometry,
  placement: FurniturePlacement | null,
  catalog: Props['catalog'],
  style: StyleKey,
  mode: RenderMode,
  showLabels: boolean,
) {
  const palette = STYLE_PALETTES[style] ?? STYLE_PALETTES.scandi
  const isometric = mode === 'isometric'

  // 1. Фон (зависит от стиля)
  fillBackground(ctx, FIXED_RENDER.outputWidth, FIXED_RENDER.outputHeight, palette.background)

  // 2. Transform (вписать план в canvas)
  const t = computeFitTransform(geometry, FIXED_RENDER.outputWidth, FIXED_RENDER.outputHeight)

  // 3. Полы (по полигонам комнат)
  drawFloorPolygon(ctx, geometry.rooms, t, palette.floor, palette.wallShadow, isometric)

  // 4. Мебель — рисуем ДО стен в plan-режиме, ПОСЛЕ полов в любом
  if (placement) {
    drawFurniture(ctx, placement, t, catalog, palette, isometric)
  }

  // 5. Стены (поверх мебели, чтобы перекрыть выступающие части)
  drawWalls(ctx, geometry.walls, geometry.openings, t,
            palette.wallTop, palette.wallFace, palette.wallShadow, isometric)

  // 6. Двери и окна (поверх стен)
  drawOpenings(ctx, geometry.openings, t, palette.doorFill, palette.windowFill, isometric)

  // 7. Подписи (опционально)
  if (showLabels) {
    drawRoomLabels(ctx, geometry.rooms, t, isometric)
  }
}

// ─── React component ─────────────────────────────────────────────────────────

export function TopDownPlanRenderer({
  geometry,
  placement,
  catalog,
  style,
  mode = 'isometric',
  showLabels = true,
  onCanvasReady,
  className,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    // Фиксированный размер для стабильности
    canvas.width = FIXED_RENDER.outputWidth
    canvas.height = FIXED_RENDER.outputHeight

    renderToCanvas(ctx, geometry, placement, catalog, style, mode, showLabels)

    onCanvasReady?.(canvas)
  }, [geometry, placement, catalog, style, mode, showLabels, onCanvasReady])

  return (
    <canvas
      ref={canvasRef}
      className={className}
      style={{ width: '100%', height: 'auto', display: 'block', maxWidth: '100%' }}
    />
  )
}

/** Утилита: экспорт canvas в PNG data URL (для скачивания / отправки). */
export function canvasToDataURL(canvas: HTMLCanvasElement): string {
  return canvas.toDataURL('image/png')
}
