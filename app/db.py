"""SQLite-слой бота.

Таблицы:
- settings: key-value (channel_alerts_enabled, channel_muted_until, и т.п.).
- incidents: состояние инцидентов для каждого slug (down с какого времени, последний алерт).
- per_inbound_mute: переключатели «не алертить этот конкретный inbound».
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS incidents (
    slug              TEXT PRIMARY KEY,
    category          TEXT NOT NULL,
    title             TEXT NOT NULL,
    status            TEXT NOT NULL,           -- 'down' | 'up'
    down_since_ts     INTEGER,                 -- когда первый раз ушёл в down
    consecutive_down  INTEGER NOT NULL DEFAULT 0,
    last_alert_ts     INTEGER NOT NULL DEFAULT 0,
    last_sent_to_channel INTEGER NOT NULL DEFAULT 0,  -- 1 если down ушёл в канал — нужен парный up
    updated_at        INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS muted_inbounds (
    slug       TEXT PRIMARY KEY,
    muted_at   INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status);

-- История зафиксированных нарушений лимита устройств у юзера (скользящее окно).
CREATE TABLE IF NOT EXISTS violation_log (
    user_uuid   TEXT    NOT NULL,
    ts          INTEGER NOT NULL,
    ips_count   INTEGER NOT NULL,
    ips         TEXT    NOT NULL          -- JSON-массив строк
);
CREATE INDEX IF NOT EXISTS idx_violation_log_user_ts ON violation_log(user_uuid, ts);

-- Последний алерт по юзеру — для cooldown между повторными нотификациями.
CREATE TABLE IF NOT EXISTS violation_alerts_sent (
    user_uuid     TEXT PRIMARY KEY,
    last_alert_ts INTEGER NOT NULL
);
"""


# Дефолтные значения настроек.
DEFAULTS = {
    "channel_alerts_enabled": "1",   # 1 = пушим в канал, 0 = молчим
    "channel_muted_until": "0",      # epoch до которого канал замьючен (0 = не замьючен)
}


@dataclass(slots=True)
class Incident:
    slug: str
    category: str
    title: str
    status: str
    down_since_ts: int | None
    consecutive_down: int
    last_alert_ts: int
    last_sent_to_channel: int


class Database:
    def __init__(self, path: str) -> None:
        self._path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        Path(os.path.dirname(self._path) or ".").mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(_SCHEMA)
        # Применяем дефолты для setting'ов, которых ещё нет.
        for k, v in DEFAULTS.items():
            await self._conn.execute(
                "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, v)
            )
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database is not connected.")
        return self._conn

    # ---------- settings ----------

    async def get_setting(self, key: str, default: str = "") -> str:
        async with self.conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ) as cur:
            row = await cur.fetchone()
        return row["value"] if row else default

    async def set_setting(self, key: str, value: str) -> None:
        await self.conn.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        await self.conn.commit()

    async def is_channel_enabled(self) -> bool:
        v = await self.get_setting("channel_alerts_enabled", "1")
        return v == "1"

    async def is_channel_muted_now(self) -> bool:
        v = int(await self.get_setting("channel_muted_until", "0") or "0")
        return v > int(time.time())

    async def channel_muted_until(self) -> int:
        return int(await self.get_setting("channel_muted_until", "0") or "0")

    # ---------- incidents ----------

    async def get_incident(self, slug: str) -> Incident | None:
        async with self.conn.execute(
            "SELECT * FROM incidents WHERE slug = ?", (slug,)
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        return Incident(
            slug=row["slug"],
            category=row["category"],
            title=row["title"],
            status=row["status"],
            down_since_ts=row["down_since_ts"],
            consecutive_down=row["consecutive_down"],
            last_alert_ts=row["last_alert_ts"],
            last_sent_to_channel=row["last_sent_to_channel"],
        )

    async def upsert_incident(
        self,
        *,
        slug: str,
        category: str,
        title: str,
        status: str,
        down_since_ts: int | None,
        consecutive_down: int,
        last_alert_ts: int,
        last_sent_to_channel: int,
    ) -> None:
        await self.conn.execute(
            """
            INSERT INTO incidents(slug, category, title, status, down_since_ts,
                                  consecutive_down, last_alert_ts, last_sent_to_channel, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(slug) DO UPDATE SET
                category = excluded.category,
                title = excluded.title,
                status = excluded.status,
                down_since_ts = excluded.down_since_ts,
                consecutive_down = excluded.consecutive_down,
                last_alert_ts = excluded.last_alert_ts,
                last_sent_to_channel = excluded.last_sent_to_channel,
                updated_at = excluded.updated_at
            """,
            (
                slug, category, title, status, down_since_ts,
                consecutive_down, last_alert_ts, last_sent_to_channel,
                int(time.time()),
            ),
        )
        await self.conn.commit()

    async def list_active_incidents(self) -> list[Incident]:
        async with self.conn.execute(
            "SELECT * FROM incidents WHERE status = 'down' ORDER BY down_since_ts"
        ) as cur:
            rows = await cur.fetchall()
        return [
            Incident(
                slug=r["slug"], category=r["category"], title=r["title"],
                status=r["status"], down_since_ts=r["down_since_ts"],
                consecutive_down=r["consecutive_down"], last_alert_ts=r["last_alert_ts"],
                last_sent_to_channel=r["last_sent_to_channel"],
            )
            for r in rows
        ]

    # ---------- muted_inbounds ----------

    async def is_inbound_muted(self, slug: str) -> bool:
        async with self.conn.execute(
            "SELECT 1 FROM muted_inbounds WHERE slug = ?", (slug,)
        ) as cur:
            return await cur.fetchone() is not None

    async def mute_inbound(self, slug: str) -> None:
        await self.conn.execute(
            "INSERT OR IGNORE INTO muted_inbounds(slug, muted_at) VALUES (?, ?)",
            (slug, int(time.time())),
        )
        await self.conn.commit()

    async def unmute_inbound(self, slug: str) -> None:
        await self.conn.execute("DELETE FROM muted_inbounds WHERE slug = ?", (slug,))
        await self.conn.commit()

    async def list_muted_inbounds(self) -> list[str]:
        async with self.conn.execute(
            "SELECT slug FROM muted_inbounds ORDER BY slug"
        ) as cur:
            rows = await cur.fetchall()
        return [r["slug"] for r in rows]

    # ---------- violation_log ----------

    async def add_violation(
        self, user_uuid: str, ts: int, ips_count: int, ips_json: str
    ) -> None:
        await self.conn.execute(
            "INSERT INTO violation_log(user_uuid, ts, ips_count, ips) VALUES (?, ?, ?, ?)",
            (user_uuid, ts, ips_count, ips_json),
        )
        await self.conn.commit()

    async def count_recent_violations(
        self, user_uuid: str, since_ts: int
    ) -> int:
        async with self.conn.execute(
            "SELECT COUNT(*) AS c FROM violation_log WHERE user_uuid = ? AND ts >= ?",
            (user_uuid, since_ts),
        ) as cur:
            row = await cur.fetchone()
        return int(row["c"]) if row else 0

    async def prune_violation_log(self, older_than_ts: int) -> None:
        """Подчищаем старые записи чтобы таблица не пухла бесконечно."""
        await self.conn.execute(
            "DELETE FROM violation_log WHERE ts < ?", (older_than_ts,)
        )
        await self.conn.commit()

    # ---------- violation_alerts_sent ----------

    async def get_violation_alert_ts(self, user_uuid: str) -> int:
        async with self.conn.execute(
            "SELECT last_alert_ts FROM violation_alerts_sent WHERE user_uuid = ?",
            (user_uuid,),
        ) as cur:
            row = await cur.fetchone()
        return int(row["last_alert_ts"]) if row else 0

    async def set_violation_alert_ts(self, user_uuid: str, ts: int) -> None:
        await self.conn.execute(
            "INSERT INTO violation_alerts_sent(user_uuid, last_alert_ts) VALUES (?, ?) "
            "ON CONFLICT(user_uuid) DO UPDATE SET last_alert_ts = excluded.last_alert_ts",
            (user_uuid, ts),
        )
        await self.conn.commit()
