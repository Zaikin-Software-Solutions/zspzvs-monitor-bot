"""check_xray_hosts — статусы proxy endpoints из Prometheus (xray-checker).

Аналог bash-функции из zspzvs-monitor.sh.
Использует метрику xray_proxy_status{address, name} (0/1).
"""

from __future__ import annotations

import logging

import httpx

from ..config import settings
from ..notifier import Event

log = logging.getLogger("check.hosts")


async def check_hosts() -> list[Event]:
    """Возвращает список Event для каждого xray-target."""
    url = f"{settings.prometheus_url}/api/v1/query"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, params={"query": "xray_proxy_status"})
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        log.warning("prometheus query failed: %s", e)
        return []

    events: list[Event] = []
    for item in data.get("data", {}).get("result", []):
        metric = item.get("metric", {})
        addr = metric.get("address", "?")
        name = metric.get("name", addr).replace("|", "/")
        value = item.get("value", ["", "?"])[1]
        slug = f"host:{addr}".replace(":", "_").replace(".", "_")

        status = "up" if value == "1" else "down"
        events.append(Event(
            category="host",
            slug=slug,
            title=name,
            status=status,
            detail=addr,
        ))
    return events
