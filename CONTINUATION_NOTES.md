# Точка продолжения работы (Tarot Telegram Mini App)

**Дата фиксации:** 2026-10-25. Все изменения закоммичены, рабочее дерево чистое.

## ✅已完成 / Выполнено и проверено

### Backend (`/workspace/backend`)
- FastAPI приложение: `app/main.py` — импортируется и запускается без ошибок.
- Авторизация Telegram initData (HMAC-SHA-256): `app/core/security.py` + тесты (8 passed).
- Роуты: auth, catalog, readings (создание/детали/история), preferences, payments/premium.
- Исправлена блокирующая ошибка импорта `PremiumProductsOut` в `payments.py`.
- Бизнес-логика: лимиты бесплатных раскладов (1/день), Premium-доступ, Кельтский крест только для Premium, идемпотентность создания раскладов (14 passed).
- Alembic: первая миграция `alembic/versions/d82e561ce0de_initial_schema.py` — применена/откатана на чистой SQLite (22 таблицы). Повторный запуск проверен.
- Seed: `app/seed/load_content.py` (колода 78 карт, темы, спреды, теги, трактаты, продукты — неактивные по умолчанию).
- Тесты: `backend/tests/` + `conftest.py` (фиктивный BOT_TOKEN, генератор подписанного initData), `pytest.ini`.

## ⚠️ Известные проблемы (чинить первыми)

1. ~~2 падающих теста~~ — ИСПРАВЛЕНО (тема health заменена на валидные). Все 28 backend-тестов проходят.
2. PostgreSQL локально недоступен — миграции проверены на SQLite; при доступном PG прогнать `alembic upgrade head` на чистой БД.

## 📋 Оставшиеся задачи (по порядку)

### Этап 3 (доделать backend)
- [x] Починить 2 теста с темой `health` — сделано, 28 passed.
- [ ] `tests/test_payments.py`: идемпотентность платежей, проверка сумм, выдача Premium только после подтверждённой оплаты (mock Telegram Stars provider, без реального токена).
- [ ] Smoke-тесты `/healthz`, `/readyz`.

### Этап 4 (frontend — НЕ НАЧАТ)
- [ ] React + TypeScript + Vite в `/workspace/frontend`.
- [ ] Telegram WebApp SDK: `initData` → `POST /api/v1/auth/telegram`, затем Bearer/X-Telegram-Init-Data.
- [ ] Экраны: загрузка/ошибки, выбор спреда+темы (+вопрос), результат расклада, история (курсорная пагинация), premium-статус/продукты.
- [ ] Реальные endpoints backend, никаких фиктивных данных. Обработка пустых состояний.
- [ ] `tsc --noEmit` + production build + frontend-тесты (Vitest).

### Этап 5 (бот — НЕ НАЧАТ)
- [ ] aiogram 3.x в `/workspace/bot`: `/start`, описание, кнопка/ссылка запуска Mini App (`tg://app?bot_username=...`), конфиг через env.
- [ ] Unit-тесты без реального токена (handler-функции изолированно).

### Этап 6 (инфраструктура/доки)
- [ ] `.env.example` (backend, bot, frontend) без секретов.
- [ ] Dockerfile (backend, frontend) + docker-compose.yml (postgres + backend + bot + frontend/nginx).
- [ ] README.md: точные команды setup / alembic upgrade / seed (cli.py load-content) / pytest / npm run dev/build / запуск бота.

### Этап 7 (финальные проверки)
- [ ] Полный прогон pytest; alembic upgrade head→downgrade base→upgrade на чистой БД.
- [ ] Фронтенд: tsc, build, vitest.
- [ ] Smoke API: auth→catalog→create reading→history→quota→premium gating (TestClient/httpx).
- [ ] Проверка безопасности: подпись, auth_date expiry, обход dev-auth в production, лимиты.

## Статус git (проверено 2026-10-25)
- Локальная ветка `qwen-code-7348fb8f-...` содержит ВСЕ три коммита: `9ed49d4` ← `c1e5b64` ← `bcf3fd8` (HEAD = 9ed49d4, рабочее дерево чистое).
- GitHub-ветка `creating-a-product-from-md-e052d` — это ДРУГАЯ ветка (указывает на `bcf3fd8`); она не обязана показывать более поздние коммиты локальной ветки.
- **Push в GitHub из этой среды невозможен**: клон был сделан без учётных данных (remote.origin.url отсутствовал; после восстановления URL github.com требует Username/Password, токена в окружении нет). Это ограничение среды, а не потеря изменений.
- Резервная копия всей истории создана: `/workspace/backup-tarot-progress.bundle` (git bundle verify — okay, complete history, оба ref'а).
- Как опубликовать вручную с машины с доступом к GitHub:
  ```bash
  git clone --bundle /workspace/backup-tarot-progress.bundle restored && cd restored
  git push <remote-url> main:refs/heads/qwen-progress
  # либо просто: git push origin qwen-code-7348fb8f-890c-42e7-a001-8630636e052d
  ```

## Команды окружения
```bash
# backend
cd /workspace/backend && pip install -r requirements.txt
DATABASE_URL=sqlite:///./test.db python -m pytest tests/ -q
alembic upgrade head
python cli.py validate-content && python cli.py load-content
uvicorn app.main:app --reload
```
