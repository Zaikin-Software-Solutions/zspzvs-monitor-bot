"""Цикл проверок: каждые CHECK_INTERVAL секунд запускает все check_*, складывает Event'ы в Notifier."""

from __future__ import annotations

import asyncio
import logging

from .checks.hosts import check_hosts
from .checks.nodes import check_nodes
from .config import settings
from .notifier import Notifier

log = logging.getLogger("scheduler")


async def run_scheduler(notifier: Notifier) -> None:
    """Бесконечный цикл проверок."""
    # Стартовая задержка 10 секунд — даём grace для prometheus после старта.
    await asyncio.sleep(10)

    while True:
        try:
            await tick(notifier)
        except Exception as e:
            log.exception("tick failed: %s", e)
        await asyncio.sleep(settings.check_interval)


async def tick(notifier: Notifier) -> None:
    log.info("tick start")
    # Все check_* можно запускать параллельно.
    results = await asyncio.gather(
        check_hosts(),
        check_nodes(),
        return_exceptions=True,
    )
    all_events = []
    for r in results:
        if isinstance(r, Exception):
            log.warning("check failed: %s", r)
            continue
        all_events.extend(r)

    log.info("collected %d events", len(all_events))

    for ev in all_events:
        try:
            await notifier.process(ev)
        except Exception as e:
            log.warning("notifier.process(%s) failed: %s", ev.slug, e)

    log.info("tick done")
