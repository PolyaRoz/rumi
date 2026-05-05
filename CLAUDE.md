# CLAUDE.md — инструкция для AI-агента

Этот файл описывает, как устроен проект Rumi и как его запускать.
Читай его целиком перед тем как что-то делать.

---

## Что такое Rumi

Веб-сервис: пользователь загружает план квартиры → выбирает стиль/бюджет → AI расставляет мебель на плане и генерирует фото интерьера → выдаёт подборку реальной мебели из каталога Hoff с ценами.

**Стек:**
- Frontend: Next.js 14 (App Router) + TypeScript + Tailwind CSS + Zustand
- Backend: FastAPI (Python 3.12) + SQLAlchemy + Alembic
- БД: PostgreSQL 16 + Redis 7
- AI: fal.ai FLUX Schnell (генерация фото интерьеров)
- Каталог: JSON-файлы с реальными товарами Hoff

---

## Структура репозитория

```
rumi/
├── CLAUDE.md                   ← этот файл
├── README.md                   ← документация для людей
├── apps/
│   ├── api/                    ← FastAPI бэкенд
│   │   ├── .env                ← переменные окружения (dev)
│   │   ├── requirements.txt
│   │   ├── alembic/            ← миграции БД
│   │   └── app/
│   │       ├── main.py         ← точка входа FastAPI
│   │       ├── config.py       ← настройки (pydantic-settings)
│   │       ├── database.py     ← async SQLAlchemy engine
│   │       ├── models/         ← SQLAlchemy модели (user, project)
│   │       ├── routers/        ← API endpoints (auth, projects)
│   │       ├── schemas/        ← Pydantic схемы
│   │       ├── services/       ← бизнес-логика (auth_service)
│   │       ├── middleware/     ← JWT auth middleware
│   │       └── workers/        ← Celery tasks (заготовка)
│   │
│   └── web/                    ← Next.js фронтенд
│       ├── .env.local.example  ← шаблон env для фронтенда
│       ├── next.config.mjs
│       ├── package.json
│       ├── app/
│       │   ├── page.tsx                    ← лендинг (/)
│       │   ├── layout.tsx                  ← root layout + шрифты
│       │   ├── globals.css                 ← CSS переменные бренда
│       │   ├── auth/page.tsx               ← регистрация/вход
│       │   ├── api/visualize/route.ts      ← proxy → fal.ai
│       │   └── (app)/                      ← защищённые страницы
│       │       ├── layout.tsx              ← проверка JWT
│       │       ├── upload/page.tsx         ← шаг 1: загрузка плана
│       │       ├── preferences/page.tsx    ← шаг 2: стиль/бюджет
│       │       ├── processing/page.tsx     ← шаг 3: анимация AI
│       │       ├── visualization/page.tsx  ← шаг 4: план + фото
│       │       └── results/page.tsx        ← шаг 5: каталог Hoff
│       ├── components/
│       │   └── StepHeader.tsx  ← прогресс-бар (4 шага)
│       ├── data/               ← каталог мебели Hoff (JSON)
│       │   ├── divany.json     ← диваны (27 шт.)
│       │   ├── kresla.json     ← кресла (24 шт.)
│       │   ├── shkafy.json     ← шкафы
│       │   ├── komody.json     ← комоды
│       │   ├── tumby.json      ← тумбы прикроватные
│       │   ├── pufy.json       ← пуфы и банкетки
│       │   └── kovry.json      ← ковры
│       ├── lib/
│       │   ├── api.ts          ← axios клиент → FastAPI
│       │   ├── auth.ts         ← JWT helpers (decode, check)
│       │   ├── catalog.ts      ← загрузка и типы каталога Hoff
│       │   └── promptBuilder.ts ← генерация промптов для fal.ai
│       ├── store/
│       │   ├── authStore.ts    ← JWT token + user (Zustand)
│       │   ├── onboardingStore.ts ← стиль/бюджет/кто живёт
│       │   └── planStore.ts    ← URL загруженного плана квартиры
│       └── types/api.ts        ← TypeScript типы для API
│
└── infra/
    ├── .env                    ← переменные для Docker Compose
    ├── .env.example            ← шаблон с описанием всех переменных
    ├── docker-compose.yml      ← postgres, redis, qdrant, nginx
    └── nginx/nginx.conf        ← реверс-прокси
```

---

## Как запустить проект (локально)

### Шаг 1 — Запустить базы данных

```bash
cd infra
docker compose up -d postgres redis
```

Проверить что работает:
```bash
docker ps
# должны быть: infra-postgres-1, infra-redis-1
```

Проверить здоровье:
```bash
docker exec infra-postgres-1 pg_isready -U rumi -d rumi_db
docker exec infra-redis-1 redis-cli ping
# ответ: PONG
```

### Шаг 2 — Запустить FastAPI бэкенд

```bash
cd apps/api

# Создать и активировать venv (если первый раз)
python -m venv .venv
source .venv/bin/activate          # macOS / Linux
.venv\Scripts\activate             # Windows (cmd)
.venv\Scripts\Activate.ps1         # Windows (PowerShell)

# Установить зависимости
pip install -r requirements.txt

# Применить миграции БД
alembic upgrade head

# Запустить сервер
uvicorn app.main:app --reload --port 8000
```

Проверить:
```bash
curl http://localhost:8000/health
# {"status":"ok","service":"rumi-api","version":"0.1.0"}
```

Swagger UI: http://localhost:8000/api/docs

### Шаг 3 — Запустить Next.js фронтенд

```bash
cd apps/web

# Установить зависимости (один раз)
npm install

# Создать .env.local (если нет)
cp .env.local.example .env.local
# Добавить FAL_KEY= для AI-генерации фотографий интерьеров

# Запустить dev-сервер
npm run dev
```

Фронтенд: http://localhost:3000

---

## Как проверить что всё работает

```bash
# API живой
curl http://localhost:8000/health

# Фронтенд отвечает
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000
# ответ: 200

# БД доступна (через API)
curl http://localhost:8000/api/v1/auth/me -H "Authorization: Bearer invalid"
# ответ: 401 — значит API работает и достучался до БД
```

---

## Переменные окружения

### `apps/web/.env.local` (НЕ в git — создать локально)

| Переменная | Значение | Описание |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | URL бэкенда |
| `NEXT_PUBLIC_WS_URL` | `ws://localhost:8000` | WebSocket URL |
| `API_URL` | `http://localhost:8000` | SSR proxy URL |
| `FAL_KEY` | `ключ с fal.ai` | API ключ для генерации фото |

Получить FAL_KEY: https://fal.ai/dashboard/keys

### `infra/.env` (уже есть в репо, dev-значения)

Ключевые переменные:
- `DATABASE_URL` — PostgreSQL connection string
- `REDIS_URL` — Redis connection string  
- `JWT_SECRET` — секрет для подписи JWT токенов

### `apps/api/.env` (уже есть в репо, dev-значения)

Копия нужных переменных для запуска API напрямую (не в Docker).
DATABASE_URL указывает на `localhost` (не `postgres`).

---

## Команды разработки

### Frontend

```bash
cd apps/web

npm run dev          # запустить dev-сервер (порт 3000)
npm run build        # production build
npm run lint         # ESLint проверка
npm run type-check   # TypeScript проверка типов
```

### Backend

```bash
cd apps/api && source .venv/bin/activate   # или .venv\Scripts\activate

uvicorn app.main:app --reload --port 8000  # запустить с hot-reload

# Миграции Alembic
alembic upgrade head              # применить все миграции
alembic revision --autogenerate -m "описание" # создать новую миграцию
alembic downgrade -1              # откатить последнюю миграцию
alembic history                   # история миграций
```

### Docker

```bash
cd infra

docker compose up -d postgres redis          # только БД (для dev)
docker compose up -d postgres redis qdrant   # + векторная БД
docker compose up -d                         # всё (включая API, web, nginx)
docker compose down                          # остановить всё
docker compose logs -f postgres              # смотреть логи
docker compose ps                            # статус контейнеров
```

---

## Бренд и дизайн

Все цвета и стили описаны в `apps/web/app/globals.css` и `tailwind.config.ts`.

**Цветовая палитра Rumi:**
```
terracotta:  #D4795C  ← основной акцент, кнопки CTA
sage:        #7A8F7A  ← вторичный, зелёный акцент
cream:       #F5EDE0  ← фоны секций
paper:       #FBF7F0  ← основной фон страниц
ink:         #1C1917  ← основной текст
border:      #EDE8E3  ← разделители, обводки
```

**Шрифты:**
- `Cormorant Garamond` (serif) — заголовки (font-heading)
- `Onest` (sans-serif) — текст (font-body)

Tailwind классы: `bg-cream`, `text-terracotta`, `border-border`, `font-heading`, `font-body`

---

## Пользовательский флоу

```
/ (лендинг)
  → /auth (регистрация или вход)
    → /upload (шаг 1: drag & drop план квартиры PNG/JPG)
      → /preferences (шаг 2: стиль, бюджет, кто живёт, приоритеты)
        → /processing (шаг 3: анимация AI-обработки, 10 сек)
          → /visualization (шаг 4)
            ├── Вкладка "На плане" — реальный план + SVG-оверлей мебели
            └── Вкладка "Фото интерьера" — AI-генерация через fal.ai FLUX
              → /results (шаг 5: реальные товары из каталога Hoff)
                └── Смета с итогами, скидками, ссылками на hoff.ru
```

**Стейт между страницами (Zustand):**
- `authStore` — JWT accessToken, refreshToken, user объект
- `onboardingStore` — style, budget, residents, priorities
- `planStore` — planUrl (blob URL загруженного плана), planFileName

---

## Каталог мебели Hoff

Файлы в `apps/web/data/` — реальные товары с сайта Hoff.

Структура каждого JSON:
```json
{
  "category": "divany",
  "products": [
    {
      "id": "unique-id",
      "name": "Название товара",
      "image": "https://hoff.ru/upload/...",
      "url": "https://hoff.ru/catalog/...",
      "price_rub": 45990,
      "old_price_rub": 57490,
      "discount_percent": 20,
      "dimensions": {
        "width_cm": 220,
        "depth_cm": 95,
        "height_cm": 85,
        "source": "сайт",
        "note": null
      }
    }
  ]
}
```

Утилиты для работы с каталогом: `apps/web/lib/catalog.ts`
- `ALL_PRODUCTS` — все товары всех категорий
- `CATEGORIES` — список категорий с продуктами
- `formatPrice(rub)` → `"45 990 ₽"`
- `formatDimensions(d)` → `"Ш 220 см · Г 95 см · В 85 см"`

---

## AI-генерация визуализаций

**Как работает:**
1. Фронтенд (`/visualization`) вызывает `/api/visualize` (Next.js route)
2. Route `/api/visualize/route.ts` собирает промпт через `promptBuilder.ts`
3. Отправляет запрос в fal.ai (модель `fal-ai/flux/schnell`)
4. Возвращает URL сгенерированного изображения

**Параметры запроса:**
```typescript
{
  room: 'living' | 'bedroom' | 'kitchen' | 'kids' | 'hallway'
  style: 'minimal' | 'scandi' | 'loft' | 'classic'
  furniture: Array<{ name: string; category: string }>
  budget?: 'economy' | 'comfort' | 'premium'
}
```

**Если FAL_KEY не задан** — API вернёт `{ error: '...', code: 'NO_KEY' }` со статусом 500.
Ключ получить на: https://fal.ai/dashboard/keys

---

## API эндпоинты

Base URL: `http://localhost:8000/api/v1`

```
POST /auth/register   — регистрация { email, password, full_name }
POST /auth/login      — вход { email, password } → { access_token, refresh_token }
POST /auth/refresh    — обновить токен { refresh_token }
GET  /auth/me         — текущий пользователь (требует Bearer token)

GET    /projects          — список проектов пользователя
POST   /projects          — создать проект
GET    /projects/{id}     — получить проект
PUT    /projects/{id}     — обновить проект
DELETE /projects/{id}     — удалить проект

GET /health               — проверка работоспособности API
```

Полная документация: http://localhost:8000/api/docs (Swagger UI)

---

## Типичные ошибки и решения

### `DATABASE_URL` connection refused
Postgres не запущен. Запусти: `cd infra && docker compose up -d postgres`

### `alembic upgrade head` падает
Проверь что `apps/api/.env` содержит правильный `DATABASE_URL` с `localhost`.
В infra/.env DATABASE_URL использует хост `postgres` (имя Docker-сервиса).

### Next.js `Image` не загружает картинки hoff.ru
Проверь `apps/web/next.config.mjs` — должен быть `hostname: 'hoff.ru'` в `remotePatterns`.

### fal.ai возвращает ошибку
- Проверь наличие `FAL_KEY` в `apps/web/.env.local`
- Убедись что ключ валидный (формат: `uuid:hash`)
- Перезапусти Next.js после изменения `.env.local`

### JWT 401 Unauthorized на всех запросах
Токен истёк. Фронтенд должен автоматически вызвать `/auth/refresh`.
Если не помогает — разлогинься и войди заново.

### `node_modules` или `.venv` нет
```bash
# Frontend
cd apps/web && npm install

# Backend
cd apps/api && python -m venv .venv && pip install -r requirements.txt
```

---

## Что ещё не реализовано (roadmap)

- [ ] Загрузка файлов в Yandex S3 (presigned URL)
- [ ] Celery-задачи для генерации + WebSocket прогресс
- [ ] PDF-экспорт сметы
- [ ] Монетизация через ЮКасса
- [ ] Мобильная адаптация (частично готова)

---

## Git workflow

Основная ветка: `master`  
Репозиторий: https://github.com/PolyaRoz/rumi

```bash
git pull origin master          # получить последние изменения
git checkout -b feature/название # создать ветку для фичи
git add .
git commit -m "feat: описание"
git push origin feature/название
# → создать Pull Request на GitHub
```
