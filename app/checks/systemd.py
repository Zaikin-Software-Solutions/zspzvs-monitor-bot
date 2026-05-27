"""check_systemd — статусы systemd-юнитов из node-exporter (текстфайл-коллектор).

В Prometheus сейчас собирается только telemt + telemt-panel (для crm и ns1).
docker/wg-quick@wg0/fail2ban на crm НЕ собираются — для них требуется
дополнительный textfile-скрипт.
"""

from __future__ import annotations

import logging

from ..notifier import Event
from ._prom import prom_query

log = logging.getLogger("check.systemd")


# Каждый кортеж: (хост-метка из Prometheus, имя юнита без .service).
# Сюда добавляем только те юниты, которые гарантированно есть в systemd_unit_active.
WATCHED_UNITS: list[tuple[str, str]] = [
    ("crm", "telemt"),
    ("crm", "telemt-panel"),
    ("ns1", "telemt"),
    ("ns1", "telemt-panel"),
]


async def check_systemd() -> list[Event]:
    """Возвращает Event для каждого юнита из WATCHED_UNITS."""
    rows = await prom_query("systemd_unit_active")
    # Индексируем: (host, unit-без-.service) -> value
    by_key: dict[tuple[str, str], str] = {}
    for item in rows:
        m = item.get("metric", {})
        host = m.get("host", "?")
        unit = m.get("unit", "").removesuffix(".service")
        value = item.get("value", ["", "0"])[1]
        by_key[(host, unit)] = value

    events: list[Event] = []
    for host, unit in WATCHED_UNITS:
        value = by_key.get((host, unit))
        if value is None:
            # метрики нет вовсе — не алертим, лишь логируем (TODO: textfile-скрипт)
            log.info("systemd metric missing for %s/%s — skip", host, unit)
            continue
        status = "up" if value == "1" else "down"
        events.append(Event(
            category="systemd",
            slug=f"systemd:{host}:{unit}",
            title=f"{unit} @ {host}",
            status=status,
            detail=f"systemd unit {unit}.service",
        ))
    return events
