"""check_remnawave_nodes — статусы RW-нод из Postgres.

Аналог bash-функции: читает таблицу nodes — name, is_connected, is_disabled, last_status_message.
"""

from __future__ import annotations

import logging

import asyncpg

from ..config import settings
from ..notifier import Event

log = logging.getLogger("check.nodes")


async def check_nodes() -> list[Event]:
    try:
        conn = await asyncpg.connect(settings.remnawave_db_dsn, timeout=10)
    except Exception as e:
        log.warning("postgres connect failed: %s", e)
        return []

    try:
        rows = await conn.fetch(
            "SELECT name, is_connected::int AS connected, "
            "COALESCE(is_disabled::int, 0) AS disabled, "
            "COALESCE(last_status_message, '') AS reason FROM nodes ORDER BY name"
        )
    except Exception as e:
        log.warning("postgres query failed: %s", e)
        await conn.close()
        return []
    finally:
        try:
            await conn.close()
        except Exception:
            pass

    events: list[Event] = []
    for r in rows:
        name = r["name"]
        if r["disabled"]:
            continue  # disabled ноды игнорируем
        status = "up" if r["connected"] else "down"
        events.append(Event(
            category="node",
            slug=f"node:{name}",
            title=name,
            status=status,
            detail=r["reason"] or "",
        ))
    return events
