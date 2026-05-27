# zspzvs-monitor-bot

[![CI](https://github.com/Zaikin-Software-Solutions/zspzvs-monitor-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/Zaikin-Software-Solutions/zspzvs-monitor-bot/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Zaikin-Software-Solutions/zspzvs-monitor-bot?display_name=tag&sort=semver&cacheSeconds=300)](https://github.com/Zaikin-Software-Solutions/zspzvs-monitor-bot/releases)
[![Docker image](https://img.shields.io/badge/ghcr.io-zspzvs--monitor--bot-blue?logo=docker&logoColor=white)](https://github.com/Zaikin-Software-Solutions/zspzvs-monitor-bot/pkgs/container/zspzvs-monitor-bot)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Telegram-бот для мониторинга zspzvs-инфраструктуры (Remnawave + VPN-ноды). Заменяет старый bash-скрипт `zspzvs-monitor.sh`.

## Что делает

- Каждые 2 минуты (настраивается) запускает набор проверок:
  - **Host-checks** — статусы proxy endpoints из Prometheus (xray-checker `xray_proxy_status`).
  - **Node-checks** — `is_connected` для каждой RW-ноды (читает Postgres панели Remnawave).
- Шлёт уведомления по **двум маршрутам**:
  - **DM админу** — подробные сообщения по всем категориям.
  - **Telegram-канал** — короткие сообщения о падении/восстановлении хостов и нод (русский + флаги, эмодзи).
- **Админка** в Telegram (только для `ADMIN_TG_ID`):
  - `/menu` — переключатель «пуши в канал ВКЛ/ВЫКЛ»
  - Кнопки «Mute канал на 1ч / 4ч / 24ч»
  - `/status` — список активных инцидентов
  - `/mute <slug>` / `/unmute <slug>` — отключить конкретный inbound
  - Тестовая отправка в канал
- **State в sqlite** — переживает рестарт, не теряет cooldown.

## Стек

- Python 3.12, aiogram 3.27, aiosqlite, httpx, asyncpg, pydantic-settings.
- Long polling (без webhook — на низком трафике проще и устойчивее).
- Docker + docker-compose, мультиарх образ через GitHub Actions → GHCR.

## Структура

```
app/
├── main.py              # точка входа: polling + scheduler параллельно
├── config.py            # настройки из env
├── db.py                # aiosqlite: settings, incidents, muted_inbounds
├── scheduler.py         # цикл проверок каждые CHECK_INTERVAL
├── notifier.py          # роутинг DM/канал + решение слать ли алерт
├── formatter.py         # формат сообщений (флаги, RU)
├── checks/
│   ├── hosts.py         # Prometheus → xray_proxy_status
│   └── nodes.py         # Postgres → SELECT FROM nodes
└── handlers/
    └── admin.py         # команды и кнопки админки
```

## Деплой на VPS (где уже крутится Remnawave + Prometheus)

### 1. Получить `BOT_TOKEN`

В Telegram написать [@BotFather](https://t.me/BotFather):
```
/newbot
<имя бота, например: ZSPZVS Monitor>
<username бота, например: zspzvs_monitor_bot>
```
BotFather пришлёт токен вида `123456789:AAH...` — это `BOT_TOKEN`.

### 2. Узнать свой `ADMIN_TG_ID`

Написать [@userinfobot](https://t.me/userinfobot) — он пришлёт ваш числовой ID.

### 3. Создать канал и узнать `CHANNEL_ID`

Создать в Telegram канал, добавить бота как админа (минимум — право «Отправлять сообщения»). Чтобы узнать `CHANNEL_ID`:
- Переслать любое сообщение из канала в [@JsonDumpBot](https://t.me/JsonDumpBot)
- Или вытащить из @userinfobot после форварда канала.

Чисел будет с минусом, например `-1003667591005`.

### 4. Развернуть бот

#### Вариант A — из готового образа GHCR (рекомендуется)

CI каждый push в `main` и каждый тег `vX.Y.Z` собирает multi-arch образ
(`linux/amd64` + `linux/arm64`) и публикует в
`ghcr.io/zaikin-software-solutions/zspzvs-monitor-bot`.

```bash
mkdir -p /opt/zspzvs-monitor-bot && cd /opt/zspzvs-monitor-bot

curl -sSL https://raw.githubusercontent.com/Zaikin-Software-Solutions/zspzvs-monitor-bot/main/docker-compose.yml -o docker-compose.yml
curl -sSL https://raw.githubusercontent.com/Zaikin-Software-Solutions/zspzvs-monitor-bot/main/.env.example -o .env

$EDITOR .env
mkdir -p data

docker compose pull
docker compose up -d
docker compose logs -f monitor-bot
```

#### Вариант B — сборка из исходников

```bash
git clone https://github.com/Zaikin-Software-Solutions/zspzvs-monitor-bot.git
cd zspzvs-monitor-bot
cp .env.example .env
$EDITOR .env
mkdir -p data
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build
docker compose logs -f monitor-bot
```

В логах должно появиться:
```
[INFO] bot: Starting zspzvs-monitor-bot, admin=... channel=... interval=120s
```

### 5. Связь с Prometheus и Postgres

Бот должен быть в **той же docker-сети**, где живут `prometheus` и `remnawave-db`. По умолчанию `docker-compose.yml` использует сеть `monitoring` (external). Если у вас сеть называется иначе (например `remnawave-network`) — поменяйте в compose-файле.

Имена контейнеров для DSN/URL берутся из docker DNS — настраиваются через env:
- `PROMETHEUS_URL=http://prometheus:9090`
- `REMNAWAVE_DB_DSN=postgres://postgres:<password>@remnawave-db:5432/postgres`

### 6. Проверить работу

- Открыть бота в Telegram, написать `/start` — должно появиться меню админки.
- В админке кнопка «Канал: ВКЛ» — должен быть активен toggle.
- Кнопка «🧪 Тест-пуш в канал» — отправит проверочное сообщение в канал.

## Что хранится в БД

- `settings(key, value)` — настройки админки (`channel_alerts_enabled`, `channel_muted_until`).
- `incidents(slug, category, status, down_since_ts, …)` — состояние инцидентов, чтобы корректно слать recovery.
- `muted_inbounds(slug, muted_at)` — список замьюченных алертов.

Файл БД лежит в `./data/bot.db` (том `data/`). Бэкап = скопировать файл.

## Локальный запуск (без docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install aiogram aiosqlite httpx asyncpg python-dotenv pydantic pydantic-settings
cp .env.example .env  # отредактировать
DB_PATH=./data/bot.db python -m app.main
```

## Управление

```bash
docker compose logs -f monitor-bot    # логи
docker compose restart monitor-bot    # рестарт
docker compose up -d --build          # пересборка после изменений
docker compose down                   # остановка
```

## Миграция со старого bash-монитора

После запуска нового бота:
1. Проверить что новые алерты приходят в DM админу и канал.
2. Остановить старый таймер: `systemctl disable --now zspzvs-monitor.timer`
3. Оставить bash-скрипты в `/usr/local/bin/zspzvs-*.sh` как страховку на пару дней.

## Безопасность

- `.env` с реальными токенами **никогда не коммитить** — `.gitignore` это учитывает.
- `ADMIN_TG_ID` — единственный кто видит админку и подробные DM. Остальным бот шлёт «Нет доступа.»
- Канал должен иметь бота админом с правом «Отправлять сообщения».
- Postgres-DSN в .env содержит пароль — `chmod 600 .env` для защиты.

## Лицензия

MIT — см. [LICENSE](LICENSE).
