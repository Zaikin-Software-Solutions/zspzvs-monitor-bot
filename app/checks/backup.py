"""check_backup — свежесть БД-бэкапа Remnawave.

textfile-метрика rw_backup_last_mtime_seconds = mtime последнего *.tar.gz
в /opt/rw-backup-restore/backup/. Алерт если > 26 часов давности.
"""

from __future__ import annotations

import logging
import time

from ..notifier import Event
from ._prom import prom_query

log = logging.getLogger("check.backup")


MAX_AGE_SECS = 26 * 3600


async def check_backup() -> list[Event]:
    rows = await prom_query("rw_backup_last_mtime_seconds")
    if not rows:
        log.info("no rw_backup_last_mtime_seconds — skip")
        return []

    now = int(time.time())
    events: list[Event] = []
    for item in rows:
        host = item.get("metric", {}).get("host", "?")
        try:
            mtime = int(float(item.get("value", ["", "0"])[1]))
        except (ValueError, TypeError):
            continue
        age = now - mtime
        age_h = age // 3600
        status = "down" if age > MAX_AGE_SECS else "up"
        events.append(Event(
            category="backup",
            slug=f"backup:rw-db:{host}",
            title=f"RW DB backup @ {host}",
            status=status,
            detail=f"last backup {age_h}h ago",
        ))
    return events
