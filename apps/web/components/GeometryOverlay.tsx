'use client'

/**
 * Canvas-компонент для отображения геометрии квартиры поверх исходного плана.
 *
 * Рендерит:
 * - Стены (синий = внутренние, красный = внешние)
 * - Комнаты (полупрозрачная заливка + подпись)
 * - Двери (оранжевый прямоугольник + дуга)
 * - Окна (голубые двойные линии)
 * - Расставленную мебель (зелёные прямоугольники)
 *
 * Используется на странице /analysis для пользовательской валидации.
 */

import { useEffect, useRef } from 'react'
import type {
  ApartmentGeometry,
  FurniturePlacement,
  Opening,
  PlacedFurniture,
  Room,
  Wall,
} from '@/store/geometryStore'
import { ROOM_LABEL_RU } from '@/store/geometryStore'

interface Props {
  planImageSrc: string          // blob URL или base64 исходного плана
  geometry: ApartmentGeometry
  placement?: FurniturePlacement | null
  showWalls?: boolean
  showRooms?: boolean
  showDoors?: boolean
  showWindows?: boolean
  showFurniture?: boolean
  highlightRoomId?: string | null
  onRoomClick?: (roomId: string) => void
  className?: string
}

// Цвета слоёв
const COLORS = {
  wallOuter:    '#E83030',
  wallInner:    '#2060D0',
  roomFills:    ['#88CC88', '#88BBDD', '#DDCC88', '#CC88DD', '#88CCCC', '#DDAA88', '#AADDAA'],
  roomHighlight:'#FF8C00',
  door:         '#FF7700',
  window:       '#00AAFF',
  furniture:    '#22AA55',
  furnitureFill:'rgba(34,170,85,0.2)',
  text:         '#1C1917',
}

function drawWall(ctx: CanvasRenderingContext2D, wall: Wall) {
  ctx.beginPath()
  ctx.moveTo(wall.start.x, wall.start.y)
  ctx.lineTo(wall.end.x, wall.end.y)
  ctx.strokeStyle = wall.type === 'outer' ? COLORS.wallOuter : COLORS.wallInner
  ctx.lineWidth = Math.max(2, wall.thickness_px * 0.5)
  ctx.stroke()
}

function drawRoom(
  ctx: CanvasRenderingContext2D,
  room: Room,
  colorIdx: number,
  highlighted: boolean,
) {
  if (room.polygon.length < 3) return
  const color = highlighted ? COLORS.roomHighlight : COLORS.roomFills[colorIdx % COLORS.roomFills.length]

  ctx.beginPath()
  ctx.moveTo(room.polygon[0].x, room.polygon[0].y)
  for (const pt of room.polygon.slice(1)) {
    ctx.lineTo(pt.x, pt.y)
  }
  ctx.closePath()

  // Полупрозрачная заливка
  ctx.fillStyle = color + '40'  // 25% opacity
  ctx.fill()
  ctx.strokeStyle = color
  ctx.lineWidth = 2
  ctx.stroke()

  // Подпись
  if (room.centroid) {
    const label = ROOM_LABEL_RU[room.label] ?? room.label
    const area = room.area_m2 ? ` ${room.area_m2}м²` : ''
    ctx.fillStyle = COLORS.text
    ctx.font = 'bold 11px sans-serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(label + area, room.centroid.x, room.centroid.y)
  }
}

function drawOpening(ctx: CanvasRenderingContext2D, opening: Opening) {
  const hw = opening.width_px / 2
  const { x, y } = opening.position
  const color = opening.type === 'door' ? COLORS.door : COLORS.window

  ctx.strokeStyle = color
  ctx.lineWidth = 3

  if (opening.type === 'door') {
    // Прямоугольник проёма + дуга
    ctx.strokeRect(x - hw, y - 4, hw * 2, 8)
    ctx.beginPath()
    ctx.arc(x - hw, y, hw, 0, Math.PI / 2)
    ctx.stroke()
  } else {
    // Двойная линия окна
    ctx.beginPath()
    ctx.moveTo(x - hw, y - 3)
    ctx.lineTo(x + hw, y - 3)
    ctx.stroke()
    ctx.beginPath()
    ctx.moveTo(x - hw, y + 3)
    ctx.lineTo(x + hw, y + 3)
    ctx.stroke()
  }
}

function drawFurnitureItem(ctx: CanvasRenderingContext2D, item: PlacedFurniture) {
  ctx.save()
  ctx.translate(item.position.x + item.width_px / 2, item.position.y + item.depth_px / 2)
  ctx.rotate((item.rotation_deg * Math.PI) / 180)

  const hw = item.width_px / 2
  const hd = item.depth_px / 2

  ctx.fillStyle = COLORS.furnitureFill
  ctx.fillRect(-hw, -hd, item.width_px, item.depth_px)
  ctx.strokeStyle = COLORS.furniture
  ctx.lineWidth = 1.5
  ctx.strokeRect(-hw, -hd, item.width_px, item.depth_px)

  ctx.restore()
}

export function GeometryOverlay({
  planImageSrc,
  geometry,
  placement,
  showWalls = true,
  showRooms = true,
  showDoors = true,
  showWindows = true,
  showFurniture = false,
  highlightRoomId,
  onRoomClick,
  className,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const imageRef = useRef<HTMLImageElement | null>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const img = new Image()
    img.src = planImageSrc
    imageRef.current = img

    img.onload = () => {
      canvas.width = geometry.source_image_width_px || img.naturalWidth
      canvas.height = geometry.source_image_height_px || img.naturalHeight

      // 1. Фон — исходный план
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height)

      // 2. Полупрозрачный оверлей
      ctx.fillStyle = 'rgba(255,255,255,0.15)'
      ctx.fillRect(0, 0, canvas.width, canvas.height)

      // 3. Комнаты
      if (showRooms) {
        geometry.rooms.forEach((room, idx) => {
          drawRoom(ctx, room, idx, room.id === highlightRoomId)
        })
      }

      // 4. Стены
      if (showWalls) {
        geometry.walls.forEach((wall) => drawWall(ctx, wall))
      }

      // 5. Проёмы
      if (showDoors || showWindows) {
        geometry.openings.forEach((opening) => {
          if (opening.type === 'door' && showDoors) drawOpening(ctx, opening)
          if (opening.type === 'window' && showWindows) drawOpening(ctx, opening)
        })
      }

      // 6. Мебель
      if (showFurniture && placement) {
        placement.rooms.forEach((rl) => {
          rl.placed_items.forEach((pi) => drawFurnitureItem(ctx, pi))
        })
      }
    }
  }, [planImageSrc, geometry, placement, showWalls, showRooms, showDoors, showWindows, showFurniture, highlightRoomId])

  // Обработка кликов по комнатам
  const handleClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!onRoomClick) return
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const scaleX = canvas.width / rect.width
    const scaleY = canvas.height / rect.height
    const px = (e.clientX - rect.left) * scaleX
    const py = (e.clientY - rect.top) * scaleY

    // Найти комнату, в которую попала точка
    for (const room of geometry.rooms) {
      if (room.polygon.length < 3) continue
      if (pointInPolygon(px, py, room.polygon)) {
        onRoomClick(room.id)
        return
      }
    }
  }

  return (
    <canvas
      ref={canvasRef}
      onClick={handleClick}
      className={className}
      style={{ cursor: onRoomClick ? 'pointer' : 'default', maxWidth: '100%' }}
    />
  )
}

// Ray-casting — повтор из Python для клиента
function pointInPolygon(px: number, py: number, polygon: { x: number; y: number }[]): boolean {
  let inside = false
  let j = polygon.length - 1
  for (let i = 0; i < polygon.length; i++) {
    const xi = polygon[i].x, yi = polygon[i].y
    const xj = polygon[j].x, yj = polygon[j].y
    if ((yi > py) !== (yj > py) && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi) {
      inside = !inside
    }
    j = i
  }
  return inside
}
