"""check_disk — заполнение корневой файловой системы.

(node_filesystem_size_bytes - node_filesystem_avail_bytes) / size > 0.90 ⇒ алерт.
"""

from __future__ import annotations

import logging

from ..notifier import Event
from ._prom import prom_query

log = logging.getLogger("check.disk")


THRESHOLD = 0.90


async def check_disk() -> list[Event]:
    avail_rows = await prom_query('node_filesystem_avail_bytes{mountpoint="/"}')
    size_rows = await prom_query('node_filesystem_size_bytes{mountpoint="/"}')
    if not avail_rows or not size_rows:
        log.info("no node_filesystem_* data — skip")
        return []

    size_by_host: dict[str, float] = {}
    for item in size_rows:
        host = item.get("metric", {}).get("host", "?")
        try:
            size_by_host[host] = float(item.get("value", ["", "0"])[1])
        except (ValueError, TypeError):
            continue

    events: list[Event] = []
    for item in avail_rows:
        host = item.get("metric", {}).get("host", "?")
        try:
            avail = float(item.get("value", ["", "0"])[1])
        except (ValueError, TypeError):
            continue
        size = size_by_host.get(host)
        if not size or size <= 0:
            continue
        used_pct = (size - avail) / size
        status = "down" if used_pct > THRESHOLD else "up"
        events.append(Event(
            category="disk",
            slug=f"disk:host={host}",
            title=f"Disk / @ {host}",
            status=status,
            detail=f"used {used_pct*100:.1f}% of {size/1e9:.1f}G",
        ))
    return events
