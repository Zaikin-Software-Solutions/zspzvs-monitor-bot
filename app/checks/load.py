"""check_load — 15-минутный load average > cpu_count * 1.5 для каждого хоста.

cpu_count берём из node_cpu_seconds_total: count by host через PromQL.
"""

from __future__ import annotations

import logging

from ..notifier import Event
from ._prom import prom_query

log = logging.getLogger("check.load")


MULTIPLIER = 1.5


async def check_load() -> list[Event]:
    # load15 по хостам
    load_rows = await prom_query("node_load15")
    # cpu count по хостам
    cpu_rows = await prom_query(
        "count(count(node_cpu_seconds_total) by (cpu, host)) by (host)"
    )
    if not load_rows or not cpu_rows:
        log.info("no node_load15 / cpu data — skip")
        return []

    cpu_by_host: dict[str, int] = {}
    for item in cpu_rows:
        host = item.get("metric", {}).get("host", "?")
        try:
            cpu_by_host[host] = int(float(item.get("value", ["", "1"])[1]))
        except (ValueError, TypeError):
            continue

    events: list[Event] = []
    for item in load_rows:
        host = item.get("metric", {}).get("host", "?")
        try:
            load = float(item.get("value", ["", "0"])[1])
        except (ValueError, TypeError):
            continue
        cpus = cpu_by_host.get(host, 1)
        threshold = cpus * MULTIPLIER
        status = "down" if load > threshold else "up"
        events.append(Event(
            category="load",
            slug=f"load:host={host}",
            title=f"Load @ {host}",
            status=status,
            detail=f"load15={load:.2f} cpu={cpus} threshold={threshold:.2f}",
        ))
    return events
