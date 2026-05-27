"""Хелпер для запросов к Prometheus HTTP API.

Все check_* используют один и тот же AsyncClient timeout=10.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from ..config import settings

log = logging.getLogger("check.prom")


async def prom_query(query: str) -> list[dict[str, Any]]:
    """Выполнить instant-query, вернуть data.result (или [] при ошибке)."""
    url = f"{settings.prometheus_url}/api/v1/query"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, params={"query": query})
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        log.warning("prom query %r failed: %s", query, e)
        return []

    if data.get("status") != "success":
        log.warning("prom query %r non-success: %s", query, data)
        return []

    return data.get("data", {}).get("result", []) or []
