"""check_docker — количество running-контейнеров на хосте через docker_container_running.

В bash-аналоге ожидалось >=13 на fd1 (crm). Здесь явно порог по хостам.
Не алертим про конкретные имена — только агрегат + список stopped.
"""

from __future__ import annotations

import logging

from ..notifier import Event
from ._prom import prom_query

log = logging.getLogger("check.docker")


# Минимальное количество running-контейнеров по хостам.
# crm: bash-скрипт ожидал >=13.
# mk1/ns1 — не покрывались bash, оставляем мягко.
EXPECTED: dict[str, int] = {
    "crm": 13,
    "mk1": 3,
    "ns1": 3,
}


async def check_docker() -> list[Event]:
    rows = await prom_query("docker_container_running")
    if not rows:
        log.info("no docker_container_running data — skip")
        return []

    # host -> (running_count, stopped_names)
    by_host: dict[str, tuple[int, list[str]]] = {}
    for item in rows:
        m = item.get("metric", {})
        host = m.get("host", "?")
        name = m.get("name", "?")
        value = item.get("value", ["", "0"])[1]
        running, stopped = by_host.get(host, (0, []))
        if value == "1":
            running += 1
        else:
            stopped.append(name)
        by_host[host] = (running, stopped)

    events: list[Event] = []
    for host, expected in EXPECTED.items():
        running, stopped = by_host.get(host, (0, []))
        if running >= expected:
            status = "up"
            detail = f"running={running} expected>={expected}"
        else:
            status = "down"
            stopped_str = ", ".join(sorted(stopped)[:5]) or "—"
            detail = f"running={running} expected>={expected}; stopped: {stopped_str}"
        events.append(Event(
            category="docker",
            slug=f"docker:expected:{host}",
            title=f"Docker @ {host}",
            status=status,
            detail=detail,
        ))
    return events
