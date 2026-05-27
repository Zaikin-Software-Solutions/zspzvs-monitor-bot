"""check_tls — срок годности TLS-сертификатов из blackbox-exporter.

Метрика probe_ssl_earliest_cert_expiry — unix-timestamp NotAfter.
Алерт если осталось < 14 дней.
"""

from __future__ import annotations

import logging
import time

from ..notifier import Event
from ._prom import prom_query

log = logging.getLogger("check.tls")


THRESHOLD_DAYS = 14
# Какие instance из job=blackbox_tls_expiry отслеживаем.
WATCHED = {
    "crm.zspzvs.ru:443": "crm",
    "panel.zspzvs.ru:8443": "panel",
}


async def check_tls() -> list[Event]:
    rows = await prom_query('probe_ssl_earliest_cert_expiry{job="blackbox_tls_expiry"}')
    if not rows:
        log.info("no blackbox_tls_expiry data — skip")
        return []

    now = int(time.time())
    events: list[Event] = []
    for item in rows:
        m = item.get("metric", {})
        instance = m.get("instance", "?")
        if instance not in WATCHED:
            continue
        slug_part = WATCHED[instance]
        try:
            expire_ts = int(float(item.get("value", ["", "0"])[1]))
        except (ValueError, TypeError):
            continue
        days_left = (expire_ts - now) // 86400
        status = "down" if days_left < THRESHOLD_DAYS else "up"
        events.append(Event(
            category="tls",
            slug=f"tls:{slug_part}",
            title=f"TLS {instance}",
            status=status,
            detail=f"expires in {days_left} days",
        ))
    return events
