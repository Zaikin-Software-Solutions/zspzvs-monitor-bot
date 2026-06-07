"""Prometheus-экспортёр метрик нод, которых нет в /metrics панели.

Панель Remnawave отдаёт loadAvg / memory / uptime ТОЛЬКО в REST API
(/api/nodes → node.system.stats), но НЕ в своём Prometheus /metrics
(там только remnawave_node_cpu_count и пр., без CPU usage / load).

Этот экспортёр периодически дёргает /api/nodes и публикует на :9101/metrics:
  remnawave_node_loadavg{node_name, period="1m|5m|15m"}
  remnawave_node_memory_used_bytes{node_name}
  remnawave_node_cpu_cores{node_name}
  remnawave_node_load_per_core{node_name, period}   # loadavg/cpus — удобно для %

Источник правды для node_name — поле name из API (а не basic_info из панели).
"""

from __future__ import annotations

import asyncio
import logging

import httpx
from aiohttp import web

from .config import settings

log = logging.getLogger("metrics_exporter")

# Кэш последнего скрейпа API: node_name -> dict со статами
_NODE_STATS: dict[str, dict] = {}
_REFRESH_INTERVAL = 30  # секунд между опросами API панели


async def _refresh_loop() -> None:
    """Каждые _REFRESH_INTERVAL секунд тянет /api/nodes и обновляет кэш."""
    headers = {"Authorization": f"Bearer {settings.remnawave_api_token}"} if settings.remnawave_api_token else {}
    url = f"{settings.remnawave_base_url.rstrip('/')}/api/nodes"
    while True:
        try:
            async with httpx.AsyncClient(timeout=10, verify=True) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            nodes = data.get("response", data)
            if isinstance(nodes, dict):
                nodes = nodes.get("nodes", [])
            fresh: dict[str, dict] = {}
            for n in nodes or []:
                name = n.get("name")
                sysd = (n.get("system") or {})
                info = sysd.get("info") or {}
                stats = sysd.get("stats") or {}
                if not name:
                    continue
                fresh[name] = {
                    "loadAvg": stats.get("loadAvg") or [],
                    "memoryUsed": stats.get("memoryUsed"),
                    "memoryFree": stats.get("memoryFree"),
                    "cpus": info.get("cpus"),
                    "uptime": stats.get("uptime"),
                    "isConnected": 1 if n.get("isConnected") else 0,
                }
            _NODE_STATS.clear()
            _NODE_STATS.update(fresh)
            log.debug("refreshed node stats: %d nodes", len(fresh))
        except Exception as e:
            log.warning("metrics refresh failed: %s", e)
        await asyncio.sleep(_REFRESH_INTERVAL)


def _render() -> str:
    """Формирует текст в Prometheus exposition format из кэша."""
    lines: list[str] = []

    def emit(metric: str, value, labels: dict):
        if value is None:
            return
        lbl = ",".join(f'{k}="{v}"' for k, v in labels.items())
        lines.append(f"{metric}{{{lbl}}} {value}")

    lines.append("# HELP remnawave_node_loadavg System load average from panel API")
    lines.append("# TYPE remnawave_node_loadavg gauge")
    periods = ["1m", "5m", "15m"]
    for name, s in _NODE_STATS.items():
        la = s.get("loadAvg") or []
        for i, p in enumerate(periods):
            if i < len(la):
                emit("remnawave_node_loadavg", la[i], {"node_name": name, "period": p})

    lines.append("# HELP remnawave_node_load_per_core loadavg divided by cpu cores")
    lines.append("# TYPE remnawave_node_load_per_core gauge")
    for name, s in _NODE_STATS.items():
        la = s.get("loadAvg") or []
        cpus = s.get("cpus") or 0
        if cpus and la:
            for i, p in enumerate(periods):
                if i < len(la):
                    emit("remnawave_node_load_per_core", round(la[i] / cpus, 4), {"node_name": name, "period": p})

    lines.append("# HELP remnawave_node_cpu_cores CPU cores from panel API")
    lines.append("# TYPE remnawave_node_cpu_cores gauge")
    for name, s in _NODE_STATS.items():
        emit("remnawave_node_cpu_cores", s.get("cpus"), {"node_name": name})

    lines.append("# HELP remnawave_node_memory_used_bytes Memory used from panel API")
    lines.append("# TYPE remnawave_node_memory_used_bytes gauge")
    for name, s in _NODE_STATS.items():
        emit("remnawave_node_memory_used_bytes", s.get("memoryUsed"), {"node_name": name})

    lines.append("# HELP remnawave_node_api_connected Node isConnected from panel API")
    lines.append("# TYPE remnawave_node_api_connected gauge")
    for name, s in _NODE_STATS.items():
        emit("remnawave_node_api_connected", s.get("isConnected"), {"node_name": name})

    return "\n".join(lines) + "\n"


async def _handle_metrics(request: web.Request) -> web.Response:
    return web.Response(text=_render(), content_type="text/plain", charset="utf-8")


async def run_metrics_exporter(port: int = 9101) -> None:
    """Поднимает aiohttp /metrics на :port и запускает refresh-loop."""
    asyncio.create_task(_refresh_loop())
    app = web.Application()
    app.router.add_get("/metrics", _handle_metrics)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    log.info("metrics exporter on :%d/metrics", port)
