"""Цикл проверок: каждые CHECK_INTERVAL секунд запускает все check_*, складывает Event'ы в Notifier.

Дополнительно: отдельная корутина крутит check_violations() каждые LIMITER_CHECK_INTERVAL
секунд — у неё своя cadence и своя логика, она не идёт через Notifier (только DM админу).
"""

from __future__ import annotations

import asyncio
import logging

from .checks.api import check_api
from .checks.backup import check_backup
from .checks.disk import check_disk
from .checks.docker import check_docker
from .checks.hosts import check_hosts
from .checks.load import check_load
from .checks.nodes import check_nodes
from .checks.systemd import check_systemd
from .checks.tls import check_tls
from .checks.violations import check_violations
from .config import settings
from .notifier import Notifier

log = logging.getLogger("scheduler")


async def run_scheduler(notifier: Notifier) -> None:
    """Бесконечный цикл проверок up/down + параллельный цикл violations."""
    # Стартовая задержка 10 секунд — даём grace для prometheus после старта.
    await asyncio.sleep(10)

    # Параллельный таск для violations (у него своя задержка и интервал).
    violations_task: asyncio.Task | None = None
    if settings.enable_limiter:
        violations_task = asyncio.create_task(run_violations_loop(notifier))

    try:
        while True:
            try:
                await tick(notifier)
            except Exception as e:
                log.exception("tick failed: %s", e)
            await asyncio.sleep(settings.check_interval)
    finally:
        if violations_task is not None and not violations_task.done():
            violations_task.cancel()


async def run_violations_loop(notifier: Notifier) -> None:
    """Отдельный цикл для check_violations() — у него свой интервал."""
    await asyncio.sleep(15)
    while True:
        try:
            await check_violations(notifier.bot, notifier.db)
        except Exception as e:
            log.exception("violations tick failed: %s", e)
        await asyncio.sleep(settings.limiter_check_interval)


async def tick(notifier: Notifier) -> None:
    log.info("tick start")
    # Все check_* можно запускать параллельно.
    results = await asyncio.gather(
        check_hosts(),
        check_nodes(),
        check_systemd(),
        check_docker(),
        check_tls(),
        check_load(),
        check_api(),
        check_backup(),
        check_disk(),
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
