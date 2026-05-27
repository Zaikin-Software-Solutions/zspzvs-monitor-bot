"""Точка входа: aiogram polling + цикл проверок параллельно."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from .config import settings
from .db import Database
from .handlers import build_root_router
from .notifier import Notifier
from .scheduler import run_scheduler


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger = logging.getLogger("bot")

    db = Database(settings.db_path)
    await db.connect()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode="HTML"),
    )
    dp = Dispatcher()
    dp.include_router(build_root_router())

    notifier = Notifier(bot, db)

    logger.info(
        "Starting zspzvs-monitor-bot, admin=%s channel=%s interval=%ds",
        settings.admin_tg_id, settings.channel_id, settings.check_interval,
    )

    polling = asyncio.create_task(dp.start_polling(bot, db=db))
    scheduler = asyncio.create_task(run_scheduler(notifier))

    try:
        # Если упадёт любой из двух — выходим из main.
        await asyncio.wait({polling, scheduler}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for t in (polling, scheduler):
            if not t.done():
                t.cancel()
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
