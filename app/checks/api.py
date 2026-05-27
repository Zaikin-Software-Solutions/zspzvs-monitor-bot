"""check_api — доступность Remnawave backend.

Использует metric up{job="remnawave"} — 1=жив, 0=Prometheus не смог
доскрейпить /metrics. Это эквивалент bash-проверки HTTP /api/system/health.
"""

from __future__ import annotations

import logging

from ..notifier import Event
from ._prom import prom_query

log = logging.getLogger("check.api")


async def check_api() -> list[Event]:
    rows = await prom_query('up{job="remnawave"}')
    if not rows:
        # Если job вообще исчез — это само по себе подозрительно.
        log.warning('up{job="remnawave"} returned no data')
        return [Event(
            category="api",
            slug="api:rw-backend",
            title="Remnawave backend",
            status="down",
            detail="no scrape target",
        )]

    events: list[Event] = []
    for item in rows:
        value = item.get("value", ["", "0"])[1]
        status = "up" if value == "1" else "down"
        events.append(Event(
            category="api",
            slug="api:rw-backend",
            title="Remnawave backend",
            status=status,
            detail=f"up={value}",
        ))
    return events
