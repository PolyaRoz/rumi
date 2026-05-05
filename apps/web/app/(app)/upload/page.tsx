'use client'

import { useCallback, useState } from 'react'
import { useDropzone } from 'react-dropzone'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Upload, FileImage, ArrowRight, X, CheckCircle2 } from 'lucide-react'
import StepHeader from '@/components/StepHeader'
import { usePlanStore } from '@/store/planStore'

export default function UploadPage() {
  const router = useRouter()
  const { setPlan } = usePlanStore()
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)

  const onDrop = useCallback((accepted: File[]) => {
    const f = accepted[0]
    if (!f) return
    const url = URL.createObjectURL(f)
    setFile(f)
    setPreview(url)
    setPlan(url, f, f.name) // сохраняем blob URL + File объект для fal.ai
  }, [setPlan])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'image/*': ['.jpg', '.jpeg', '.png', '.webp', '.heic'] },
    maxSize: 10 * 1024 * 1024,
    multiple: false,
  })

  const handleRemove = () => {
    if (preview) URL.revokeObjectURL(preview)
    setFile(null)
    setPreview(null)
  }

  return (
    <div className="min-h-screen bg-paper flex flex-col">
      <StepHeader current={0} backHref="/" backLabel="На главную" />

      <main className="flex-1 flex flex-col items-center justify-center px-6 py-12">
        <div className="w-full max-w-[560px] flex flex-col gap-8">
          <div className="flex flex-col gap-2">
            <h1 className="font-heading text-[42px] font-semibold text-ink leading-tight">
              Загрузите план квартиры
            </h1>
            <p className="font-body text-[15px] text-muted leading-relaxed">
              Подойдёт фото плана из приложения застройщика, скан из документов
              или фото с рекламного щита
            </p>
          </div>

          {!file ? (
            <div
              {...getRootProps()}
              className={`
                rounded-2xl border-2 border-dashed transition-all duration-200 cursor-pointer
                flex flex-col items-center justify-center gap-4 py-16 px-8
                ${isDragActive
                  ? 'border-terracotta bg-terracotta-50'
                  : 'border-border bg-white hover:border-terracotta hover:bg-terracotta-50/30'
                }
              `}
            >
              <input {...getInputProps()} />
              <div className={`w-14 h-14 rounded-2xl flex items-center justify-center transition-colors
                ${isDragActive ? 'bg-terracotta text-white' : 'bg-terracotta-100 text-terracotta'}`}>
                <Upload size={24} />
              </div>
              <div className="text-center flex flex-col gap-1.5">
                <p className="font-body text-[16px] font-medium text-ink">
                  {isDragActive ? 'Отпустите файл' : 'Перетащите план сюда'}
                </p>
                <p className="font-body text-[14px] text-muted">
                  или <span className="text-terracotta underline">выберите файл</span>
                </p>
              </div>
              <p className="font-body text-[12px] text-muted">JPEG, PNG, HEIC · до 10 МБ</p>
            </div>
          ) : (
            <div className="bg-white rounded-2xl border border-border overflow-hidden">
              <div className="relative">
                <img src={preview!} alt="Загруженный план" className="w-full h-[260px] object-cover" />
                <button
                  onClick={handleRemove}
                  className="absolute top-3 right-3 w-8 h-8 bg-white rounded-full border border-border flex items-center justify-center shadow-sm hover:bg-paper transition-colors"
                >
                  <X size={14} className="text-ink" />
                </button>
              </div>
              <div className="px-5 py-4 flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl bg-sage-50 flex items-center justify-center flex-shrink-0">
                  <FileImage size={18} className="text-sage" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-body text-[14px] font-medium text-ink truncate">{file.name}</p>
                  <p className="font-body text-[12px] text-muted">{(file.size / 1024 / 1024).toFixed(1)} МБ</p>
                </div>
                <CheckCircle2 size={20} className="text-sage flex-shrink-0" />
              </div>
            </div>
          )}

          <div className="bg-terracotta-50 rounded-xl p-4 flex flex-col gap-2">
            <p className="font-body text-[13px] font-medium text-terracotta">Советы для лучшего результата</p>
            <ul className="flex flex-col gap-1">
              {[
                'Убедитесь, что план хорошо освещён и не размыт',
                'Все комнаты должны быть видны целиком',
                'Размеры на плане помогут точнее подобрать мебель',
              ].map((tip, i) => (
                <li key={i} className="font-body text-[12px] text-[#7A4033] flex items-start gap-2">
                  <span className="mt-0.5 w-3 h-3 rounded-full border border-terracotta flex-shrink-0" />
                  {tip}
                </li>
              ))}
            </ul>
          </div>

          <div className="flex gap-3">
            <Link href="/" className="btn-ghost py-3.5 px-6 text-[15px]">Назад</Link>
            <button
              onClick={() => router.push('/preferences')}
              disabled={!file}
              className="flex-1 btn-primary text-[15px] py-3.5 flex items-center justify-center gap-2"
            >
              Продолжить <ArrowRight size={16} />
            </button>
          </div>
        </div>
      </main>
    </div>
  )
}
