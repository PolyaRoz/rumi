# 🛋 Руми — AI-подбор мебели

Веб-сервис, который берёт план квартиры и подбирает реальную мебель из российских магазинов с визуализацией.

**Стек:** Next.js 14 · FastAPI · PostgreSQL · Redis · fal.ai (FLUX) · Hoff каталог

---

## Быстрый старт

### Что нужно установить
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [Node.js 20+](https://nodejs.org/)
- [Python 3.12+](https://www.python.org/)
- [Git](https://git-scm.com/)

### 1. Клонировать репозиторий

```bash
git clone https://github.com/PolyaRoz/rumi.git
cd rumi
```

### 2. Запустить базы данных (PostgreSQL + Redis)

```bash
cd infra
cp .env.example .env        # заполни JWT_SECRET и опционально S3_*
docker compose up -d postgres redis
```

Проверить что запустилось:
```bash
docker ps   # должны быть infra-postgres-1 и infra-redis-1
```

### 3. Запустить бэкенд (FastAPI)

```bash
cd apps/api

# Создать виртуальное окружение
python -m venv .venv

# Активировать (выбери свою ОС):
source .venv/bin/activate        # macOS / Linux
.venv\Scripts\activate           # Windows (cmd)
.venv\Scripts\Activate.ps1       # Windows (PowerShell)

# Установить зависимости
pip install -r requirements.txt

# Создать .env для локального запуска
cp ../../infra/.env .env
# Убедись что DATABASE_URL и REDIS_URL указывают на localhost, не на docker-сервисы

# Применить миграции
alembic upgrade head

# Запустить сервер
uvicorn app.main:app --reload --port 8000
```

API: http://localhost:8000  
Swagger: http://localhost:8000/api/docs

### 4. Запустить фронтенд (Next.js)

```bash
cd apps/web

# Установить зависимости
npm install

# Настроить переменные окружения
cp .env.local.example .env.local
# Опционально: добавить FAL_KEY для AI-генерации визуализаций
# Получить ключ: https://fal.ai/dashboard/keys

# Запустить
npm run dev
```

Фронтенд: http://localhost:3000

---

## Структура проекта

```
rumi/
├── apps/
│   ├── api/                    # FastAPI бэкенд
│   │   ├── app/
│   │   │   ├── main.py         # точка входа
│   │   │   ├── models/         # SQLAlchemy модели
│   │   │   ├── routers/        # API роуты
│   │   │   ├── schemas/        # Pydantic схемы
│   │   │   ├── services/       # бизнес-логика
│   │   │   └── middleware/     # JWT auth
│   │   ├── alembic/            # миграции БД
│   │   └── requirements.txt
│   │
│   └── web/                    # Next.js фронтенд
│       ├── app/
│       │   ├── page.tsx        # лендинг
│       │   ├── auth/           # авторизация
│       │   ├── (app)/
│       │   │   ├── upload/     # шаг 1: загрузка плана
│       │   │   ├── preferences/# шаг 2: предпочтения
│       │   │   ├── processing/ # шаг 3: AI обработка
│       │   │   ├── visualization/ # шаг 4: план + фото
│       │   │   └── results/    # шаг 5: каталог Hoff
│       │   └── api/
│       │       └── visualize/  # генерация через fal.ai
│       ├── components/         # переиспользуемые компоненты
│       ├── data/               # каталог мебели Hoff (JSON)
│       ├── lib/                # утилиты: catalog.ts, promptBuilder.ts
│       └── store/              # Zustand стейт
│
└── infra/
    ├── docker-compose.yml      # postgres, redis, nginx
    ├── nginx/nginx.conf        # реверс-прокси
    └── .env.example            # шаблон переменных
```

---

## Flow приложения

```
Лендинг (/) 
  → Авторизация (/auth)
    → Загрузка плана (/upload)          — drag & drop план квартиры
      → Предпочтения (/preferences)     — стиль, бюджет, кто живёт
        → Обработка (/processing)       — анимация AI (10 сек)
          → Визуализация (/visualization)
            ├── 📐 На плане             — SVG-оверлей мебели на загруженный план
            └── 📸 Фото интерьера       — AI-генерация через fal.ai (FLUX)
              → Подборка (/results)     — реальные товары из каталога Hoff
```

---

## Переменные окружения

### `apps/web/.env.local` (создать из `.env.local.example`)

| Переменная | Описание |
|-----------|----------|
| `NEXT_PUBLIC_API_URL` | URL бэкенда, по умолчанию `http://localhost:8000` |
| `FAL_KEY` | API ключ fal.ai для генерации визуализаций |

### `infra/.env` (создать из `.env.example`)

| Переменная | Описание |
|-----------|----------|
| `JWT_SECRET` | Секрет для JWT, генерировать: `python -c "import secrets; print(secrets.token_hex(64))"` |
| `DATABASE_URL` | PostgreSQL URL |
| `REDIS_URL` | Redis URL |
| `S3_*` | Yandex Object Storage (опционально) |

---

## Каталог мебели

В `apps/web/data/` лежат JSON-файлы с реальными товарами Hoff:
- `divany.json` — диваны (27 шт.)
- `kresla.json` — кресла (24 шт.)
- `shkafy.json` — шкафы
- `komody.json` — комоды
- `tumby.json` — тумбы прикроватные
- `pufy.json` — пуфы и банкетки
- `kovry.json` — ковры

---

## Статус разработки

- ✅ Инфраструктура: PostgreSQL, Redis, Docker Compose, nginx
- ✅ FastAPI: auth (register/login/refresh/me), projects CRUD, JWT
- ✅ Alembic миграции
- ✅ Лендинг с превью интерфейса
- ✅ Страница авторизации (регистрация/вход)
- ✅ Шаг 1: загрузка плана (drag & drop)
- ✅ Шаг 2: предпочтения (стиль / бюджет / приоритеты)
- ✅ Шаг 3: анимация AI-обработки
- ✅ Шаг 4: визуализация — SVG-оверлей + AI-фото (fal.ai FLUX)
- ✅ Шаг 5: каталог Hoff с реальными товарами, фото, ценами, ссылками
- ✅ Смета с подсчётом итогов и скидок
- ⬜ Загрузка фото в S3 (presigned URL)
- ⬜ Генерация через Celery + WebSocket прогресс
- ⬜ PDF экспорт сметы
- ⬜ Монетизация (ЮКасса)
