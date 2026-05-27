# zspzvs-monitor-bot

Telegram-бот для мониторинга zspzvs-инфраструктуры (Remnawave + VPN-ноды). Заменяет старый bash-скрипт `zspzvs-monitor.sh`.

## Возможности

- 🔄 **Тикает каждые 2 минуты** (настраивается через `CHECK_INTERVAL`):
  - **Host-checks** (`xray-checker` через Prometheus) — статусы всех inbound по нодам
  - **Node-checks** (Postgres Remnawave) — `is_connected` для каждой RW-ноды
  - (на подходе: systemd, docker, TLS, load, API, backup, disk)

- 📩 **Два канала уведомлений**:
  - **DM админу** — подробные сообщения по всем категориям
  - **Telegram-канал** — короткие сообщения о падении/восстановлении хостов и нод

- ⚙️ **Админка** (`/menu`):
  - Переключатель «пуши в канал ВКЛ/ВЫКЛ»
  - Mute канала на 1ч / 4ч / 24ч
  - `/status` — список активных инцидентов
  - `/mute <slug>` / `/unmute <slug>` — отключить конкретный inbound
  - Тестовая отправка в канал

- 💾 **State в sqlite** — переживает рестарт, не теряет cooldown.

## Структура

```
app/
├── main.py        — точка входа (aiogram polling + scheduler)
├── config.py      — pydantic-settings из .env
├── db.py          — sqlite schema (settings, incidents, muted_inbounds)
├── scheduler.py   — цикл проверок
├── notifier.py    — маршрут DM/канал + решение слать ли алерт
├── formatter.py   — форматы сообщений (с эмодзи-флагами)
├── checks/
│   ├── hosts.py   — Prometheus → xray_proxy_status
│   └── nodes.py   — Postgres → SELECT FROM nodes
└── handlers/
    └── admin.py   — команды, кнопки админки
```

## Разработка локально

```bash
cd ~/PycharmProjects/zspzvs-monitor-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

cp .env.example .env
# заполнить BOT_TOKEN, ADMIN_TG_ID, CHANNEL_ID (рекомендуется отдельный тест-канал)

python -m app.main
```

## Сборка docker-образа

```bash
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build
```

## Деплой на сервер

```bash
# на fd1
mkdir -p /opt/zspzvs-monitor-bot
cd /opt/zspzvs-monitor-bot
# скопировать docker-compose.yml + .env с production-значениями
docker compose up -d
```

GHCR-image билдится через GitHub Actions и публикуется как `ghcr.io/zaikin-software-solutions/zspzvs-monitor-bot:latest`.

## Миграция со старого bash-монитора

После запуска нового бота:
1. Остановить старый таймер: `systemctl disable --now zspzvs-monitor.timer`
2. Оставить bash-скрипты в `/usr/local/bin/zspzvs-*.sh` как страховку.
3. Проверять что новые алерты идут так же или лучше старых.
