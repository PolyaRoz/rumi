import Link from 'next/link'
import { ArrowRight } from 'lucide-react'

const steps = [
  {
    n: '01',
    title: 'Загрузите план',
    desc: 'Фото плана квартиры из приложения застройщика или скан документа',
    color: 'bg-terracotta-100',
    dot: 'bg-terracotta',
  },
  {
    n: '02',
    title: 'Укажите предпочтения',
    desc: 'Стиль, бюджет и приоритеты — кто живёт, что важно, сколько хранить',
    color: 'bg-sage-50',
    dot: 'bg-sage',
  },
  {
    n: '03',
    title: 'Получите подборку',
    desc: 'Реальные товары из российских магазинов, подобранные под ваш план',
    color: 'bg-terracotta-100',
    dot: 'bg-terracotta',
  },
]

export default function HomePage() {
  return (
    <main className="min-h-screen bg-paper">
      {/* Navbar */}
      <nav className="h-[72px] bg-white/80 backdrop-blur-sm border-b border-border flex items-center justify-between px-8 md:px-20 sticky top-0 z-50">
        <div className="flex items-center gap-2.5">
          <div className="w-2.5 h-2.5 rounded-full bg-terracotta" />
          <span className="font-heading text-[26px] font-semibold text-ink">Руми</span>
        </div>
        <div className="hidden md:flex items-center gap-10">
          <a href="#how" className="font-body text-[15px] text-ink hover:text-terracotta transition-colors">
            Как это работает
          </a>
          <a href="#examples" className="font-body text-[15px] text-ink hover:text-terracotta transition-colors">
            Примеры
          </a>
        </div>
        <div className="flex items-center gap-3">
          <Link href="/auth" className="btn-ghost text-[15px]">
            Войти
          </Link>
          <Link href="/auth" className="btn-primary text-[14px] py-2.5 px-5">
            Начать
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <section className="flex flex-col md:flex-row min-h-[580px]">
        {/* Левая — текст */}
        <div className="flex-1 flex flex-col justify-center px-8 md:pl-20 md:pr-10 py-16 gap-6">
          <span className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-terracotta-100 text-terracotta text-[13px] font-medium font-body w-fit">
            <span className="w-1.5 h-1.5 rounded-full bg-terracotta animate-pulse" />
            AI подбор мебели
          </span>
          <h1 className="font-heading text-[58px] md:text-[72px] leading-[1.04] font-semibold text-ink">
            Мебель,<br />
            которая<br />
            впишется
          </h1>
          <p className="font-body text-[17px] text-[#5A5350] leading-relaxed max-w-[440px]">
            Загрузите план квартиры — Руми распознает комнаты, расставит мебель
            и подберёт реальные товары из российских магазинов
          </p>
          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4 pt-2">
            <Link href="/auth" className="btn-primary text-base py-3.5 px-8 flex items-center gap-2">
              Попробовать <ArrowRight size={16} />
            </Link>
            <p className="font-body text-[13px] text-muted">
              Бесплатно · AI на основе Claude
            </p>
          </div>
        </div>

        {/* Правая — визуализация */}
        <div className="flex-1 bg-cream flex items-center justify-center p-8 min-h-[360px]">
          <div className="w-full max-w-[480px] bg-white rounded-2xl border border-border shadow-sm overflow-hidden">
            {/* Мок интерфейса результатов */}
            <div className="bg-[#F5EDE0] px-5 py-3 border-b border-border flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-terracotta" />
                <span className="font-heading text-[15px] font-semibold text-ink">Руми</span>
              </div>
              <span className="font-body text-[12px] text-muted">Гостиная · Скандинавский</span>
            </div>
            <div className="p-4 flex flex-col gap-3">
              {[
                { name: 'Диван угловой Stockholm', store: 'Hoff', price: '89 990 ₽', color: 'bg-[#D4C5B5]' },
                { name: 'Стол обеденный Arken', store: 'IKEA', price: '24 990 ₽', color: 'bg-[#C8B4A0]' },
                { name: 'Кресло Frigg', store: 'Lazurit', price: '34 990 ₽', color: 'bg-[#DDD0C0]' },
              ].map((item, i) => (
                <div key={i} className="flex items-center gap-3 p-3 rounded-xl bg-paper border border-border">
                  <div className={`w-12 h-12 rounded-lg flex-shrink-0 ${item.color}`} />
                  <div className="flex-1 min-w-0">
                    <p className="font-body text-[13px] font-medium text-ink truncate">{item.name}</p>
                    <p className="font-body text-[12px] text-muted">{item.store}</p>
                  </div>
                  <span className="font-body text-[13px] font-semibold text-terracotta flex-shrink-0">{item.price}</span>
                </div>
              ))}
              <div className="mt-1 pt-3 border-t border-border flex items-center justify-between">
                <span className="font-body text-[13px] text-muted">Итого (3 товара)</span>
                <span className="font-heading text-[17px] font-semibold text-ink">149 970 ₽</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Как это работает */}
      <section id="how" className="bg-white border-t border-border py-16 px-8 md:px-20">
        <h2 className="font-heading text-[40px] font-semibold text-ink mb-10">Как это работает</h2>
        <div className="grid md:grid-cols-3 gap-8">
          {steps.map((s, i) => (
            <div key={i} className="flex flex-col gap-4">
              <div className={`w-12 h-12 rounded-2xl ${s.color} flex items-center justify-center`}>
                <span className="font-heading text-[13px] font-semibold text-ink">{s.n}</span>
              </div>
              <h3 className="font-heading text-[22px] font-semibold text-ink">{s.title}</h3>
              <p className="font-body text-[15px] text-[#6B6562] leading-relaxed">{s.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Примеры */}
      <section id="examples" className="py-16 px-8 md:px-20">
        <h2 className="font-heading text-[40px] font-semibold text-ink mb-10">Примеры подборок</h2>
        <div className="grid md:grid-cols-3 gap-6">
          {[
            { room: 'Гостиная', style: 'Скандинавский', budget: '100–200 тыс.', items: 8 },
            { room: 'Спальня', style: 'Минимализм', budget: '80–120 тыс.', items: 6 },
            { room: 'Кухня-студия', style: 'Лофт', budget: '150–250 тыс.', items: 11 },
          ].map((ex, i) => (
            <div key={i} className="card overflow-hidden">
              <div className="h-40 bg-cream flex items-center justify-center">
                <div className="w-16 h-16 rounded-2xl bg-white border border-border flex items-center justify-center shadow-sm">
                  <div className="w-6 h-6 rounded-full bg-terracotta opacity-60" />
                </div>
              </div>
              <div className="p-5 flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <span className="font-heading text-[18px] font-semibold text-ink">{ex.room}</span>
                  <span className="font-body text-[12px] text-muted px-2 py-0.5 rounded-full bg-sage-50 text-sage-dark">{ex.style}</span>
                </div>
                <p className="font-body text-[14px] text-muted">{ex.items} товаров · {ex.budget} ₽</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="bg-terracotta mx-8 md:mx-20 mb-16 rounded-3xl py-14 px-8 md:px-16 flex flex-col md:flex-row items-center justify-between gap-8">
        <div className="flex flex-col gap-3">
          <h2 className="font-heading text-[36px] font-semibold text-white leading-tight">
            Готовы обставить квартиру?
          </h2>
          <p className="font-body text-[16px] text-white/80">
            Загрузите план — мы подберём мебель за 10 секунд
          </p>
        </div>
        <Link
          href="/auth"
          className="flex-shrink-0 bg-white text-terracotta font-body font-semibold text-[15px] px-8 py-3.5 rounded-xl hover:bg-paper transition-colors flex items-center gap-2"
        >
          Начать бесплатно <ArrowRight size={16} />
        </Link>
      </section>

      {/* Footer */}
      <footer className="border-t border-border px-8 md:px-20 py-8 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-terracotta" />
          <span className="font-heading text-[18px] font-semibold text-ink">Руми</span>
        </div>
        <p className="font-body text-[13px] text-muted">© 2025 Руми. AI-подбор мебели</p>
      </footer>
    </main>
  )
}
