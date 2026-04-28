# VK Micro Habits Bot — «Мелкодел»

Полноценный VK-бот для маленьких ежедневных дел: регистрация, ежедневная рассылка, кнопка «✅ Сделано!», streak, жизнь раз в неделю, статистика, лидерборд, уровни, монеты, ачивки, категории, сложность, вечерние напоминания и Render-деплой через GitHub.

## Что внутри

- VK Callback API endpoint: `POST /vk/callback`
- Подтверждение сервера VK: событие `confirmation` возвращает `VK_CONFIRMATION_TOKEN`
- Обработка входящих сообщений: `message_new`
- Обработка inline callback-кнопок: `message_event`
- Ежедневные задания по локальному времени пользователя
- Вечернее напоминание, если задание не закрыто
- «✅ Сделано!» редактирует исходное сообщение задания через `messages.edit`; если редактирование не удалось, бот отправит fallback-сообщение
- Streak: серия дней подряд
- 1 жизнь в неделю: первый пропуск за неделю спасает серию
- Личный профиль: серия, лучший streak, выполнено всего, очки, монеты, уровень, жизни, ачивки
- Лидерборд по текущей серии
- Настройки: время, часовой пояс, категории, сложность
- Ачивки и уровни
- База заданий на разные категории
- Render Blueprint: `render.yaml` создаёт web service + cron job + PostgreSQL

## Структура

```text
app/
  main.py          # FastAPI app + VK webhook
  bot_logic.py     # вся логика бота
  jobs.py          # ежедневные рассылки и напоминания
  scheduler.py     # локальный scheduler для разработки/standalone
  models.py        # SQLAlchemy модели
  seed.py          # сидинг заданий и ачивок
  content.py       # задания, тексты, категории
  keyboards.py     # VK keyboard JSON
  vk_client.py     # обёртка VK API
  cli.py           # init-db / run-due
render.yaml        # Render Blueprint
requirements.txt
.env.example
```

## Локальный запуск

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python -m app.cli init-db
uvicorn app.main:app --host 0.0.0.0 --port 10000 --reload
```

Для локального теста VK webhook нужен публичный HTTPS URL. Удобно использовать любой туннель, например ngrok/cloudflared, и указать в VK адрес:

```text
https://YOUR_PUBLIC_URL/vk/callback
```

## Переменные окружения

Обязательные:

```env
VK_GROUP_TOKEN=...
VK_CONFIRMATION_TOKEN=...
VK_SECRET=...
VK_GROUP_ID=123456789
DATABASE_URL=...
```

Опциональные:

```env
BOT_NAME=Мелкодел
VK_API_VERSION=5.199
DEFAULT_TIMEZONE=Europe/Moscow
DEFAULT_DAILY_TIME=09:00
DEFAULT_REMINDER_TIME=20:00
ENABLE_INTERNAL_SCHEDULER=true
ADMIN_TOKEN=...
CRON_SECRET=...
PUBLIC_BASE_URL=https://your-service.onrender.com
```

## Настройка VK

1. Создай/открой сообщество VK.
2. Включи сообщения сообщества.
3. В разделе управления сообществом открой API / Callback API.
4. Добавь сервер:
   - URL: `https://YOUR_RENDER_SERVICE.onrender.com/vk/callback`
   - Secret key: значение из `VK_SECRET`
   - API version: `5.199` или актуальную версию, которую используешь в `VK_API_VERSION`
5. Скопируй confirmation-строку в `VK_CONFIRMATION_TOKEN`.
6. Включи типы событий:
   - `message_new`
   - `message_event`
7. Создай ключ доступа сообщества с правами на сообщения и вставь его в `VK_GROUP_TOKEN`.

## Деплой на Render через GitHub

1. Создай GitHub-репозиторий и загрузи туда весь проект.
2. В Render выбери **New → Blueprint** и укажи репозиторий.
3. Render прочитает `render.yaml` и создаст:
   - web service `vk-micro-habits-bot`
   - cron job `vk-micro-habits-bot-cron`
   - PostgreSQL `vk-micro-habits-db`
4. При создании Render попросит значения для `sync: false` переменных:
   - `VK_GROUP_TOKEN`
   - `VK_CONFIRMATION_TOKEN`
   - `VK_SECRET`
   - `VK_GROUP_ID`
5. После деплоя возьми URL web service и добавь в VK Callback API:

```text
https://YOUR_RENDER_SERVICE.onrender.com/vk/callback
```

## Важное про cron и scheduler

В `render.yaml` web service запускается с:

```env
ENABLE_INTERNAL_SCHEDULER=false
```

Потому что ежедневные рассылки делает отдельный Render cron job каждые 5 минут:

```yaml
schedule: "*/5 * * * *"
```

Это надёжнее, чем держать рассылку только внутри web-процесса. Локально можно поставить `ENABLE_INTERNAL_SCHEDULER=true`.

## Проверка после деплоя

Открой:

```text
https://YOUR_RENDER_SERVICE.onrender.com/healthz
```

Должен быть ответ:

```json
{"status":"ok"}
```

Админ-статистика:

```text
https://YOUR_RENDER_SERVICE.onrender.com/admin/stats?token=YOUR_ADMIN_TOKEN
```

Ручной запуск рассылки:

```bash
curl -X POST https://YOUR_RENDER_SERVICE.onrender.com/internal/run-due \
  -H "X-Cron-Secret: YOUR_CRON_SECRET"
```

## Команды пользователя в VK

- `начать`
- `статистика`
- `лидерборд`
- `задание`
- `настройки`
- `неделя`
- `помощь`
- `сделано`
- можно написать время, например `08:30`

## Тесты

```bash
pytest -q
```

## Что можно докрутить дальше

- отдельная админка для добавления заданий без деплоя
- реферальные ссылки и «челлендж с другом»
- недельный leaderboard
- платные/донатные косметические бейджи
- экспорт статистики в CSV
