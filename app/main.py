"""Точка входа: aiogram polling + цикл проверок параллельно."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand, BotCommandScopeChat, MenuButtonCommands

from .config import settings
from .db import Database
from .handlers import build_root_router
from .notifier import Notifier
from .scheduler import run_scheduler


# Команды, показываемые в нативном меню Telegram (кнопочка слева от поля ввода).
# Видны только админу (scope = чат с админом).
ADMIN_COMMANDS = [
    BotCommand(command="menu",    description="🤖 Открыть админку"),
    BotCommand(command="status",  description="📋 Активные инциденты"),
    BotCommand(command="mute",    description="🔇 Замьютить inbound по slug"),
    BotCommand(command="unmute",  description="🔔 Снять mute с inbound по slug"),
]


async def setup_menu_button(bot: Bot) -> None:
    """Прописывает кнопочку «Меню» в чате с админом + список команд.

    После этого админу не нужно вводить /menu руками — есть постоянная кнопка
    слева от поля ввода, по которой выпадает список с описаниями.
    """
    # 1) Список команд — только для чата с админом (другим пользователям бот
    #    отвечает «Нет доступа», им меню и не нужно).
    await bot.set_my_commands(
        commands=ADMIN_COMMANDS,
        scope=BotCommandScopeChat(chat_id=settings.admin_tg_id),
    )
    # 2) Сама кнопочка «Меню» рядом с полем ввода (тип = commands = открывает
    #    список из set_my_commands). Действует для всех чатов; админ — единственный,
    #    кто это увидит у себя.
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())


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

    # Регистрируем постоянную кнопку «Меню» + список команд для админа.
    # Делаем это до старта polling, чтобы при первом /start команды уже были видны.
    try:
        await setup_menu_button(bot)
    except Exception as e:
        logger.warning("setup_menu_button failed (non-fatal): %s", e)

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
