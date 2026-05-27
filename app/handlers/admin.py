"""Админка бота.

Команды и кнопки доступны ТОЛЬКО админу (settings.admin_tg_id).
Остальным — короткий «нет доступа».

Функционал:
- /start, /menu — главное меню
- toggle: пуши в канал ВКЛ/ВЫКЛ (channel_alerts_enabled)
- mute канал на 1ч / 4ч / 24ч
- /status — список активных инцидентов
- mute/unmute конкретный inbound
- test push в канал
"""

from __future__ import annotations

import time

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message,
)

from ..config import settings
from ..db import Database

router = Router(name="admin")


def _is_admin(user_id: int | None) -> bool:
    return user_id == settings.admin_tg_id


async def _main_menu_kb(db: Database) -> InlineKeyboardMarkup:
    enabled = await db.is_channel_enabled()
    muted_until = await db.channel_muted_until()
    now = int(time.time())

    if not enabled:
        toggle_text = "🔕 Канал: ВЫКЛ"
        toggle_cb = "ch:on"
    elif muted_until > now:
        rem = muted_until - now
        mins = rem // 60
        toggle_text = f"⏸ Канал: mute ({mins} мин)"
        toggle_cb = "ch:unmute"
    else:
        toggle_text = "🔔 Канал: ВКЛ"
        toggle_cb = "ch:off"

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=toggle_text, callback_data=toggle_cb)],
        [
            InlineKeyboardButton(text="⏸ Mute 1ч", callback_data="ch:mute:1"),
            InlineKeyboardButton(text="⏸ Mute 4ч", callback_data="ch:mute:4"),
            InlineKeyboardButton(text="⏸ Mute 24ч", callback_data="ch:mute:24"),
        ],
        [InlineKeyboardButton(text="📋 Статус инцидентов", callback_data="status")],
        [InlineKeyboardButton(text="🔇 Замьюченные inbound'ы", callback_data="muted_list")],
        [InlineKeyboardButton(text="🧪 Тест-пуш в канал", callback_data="test_push")],
    ])


@router.message(Command("start", "menu"))
async def cmd_menu(msg: Message, db: Database) -> None:
    if not _is_admin(msg.from_user.id if msg.from_user else None):
        await msg.answer("Нет доступа.")
        return
    kb = await _main_menu_kb(db)
    await msg.answer(
        "🤖 <b>zspzvs-monitor-bot</b>\n\nАдминка. Управление пушами в канал.",
        reply_markup=kb,
    )


@router.message(Command("status"))
async def cmd_status(msg: Message, db: Database) -> None:
    if not _is_admin(msg.from_user.id if msg.from_user else None):
        await msg.answer("Нет доступа.")
        return
    await _send_status(msg, db)


async def _send_status(msg: Message, db: Database) -> None:
    incidents = await db.list_active_incidents()
    if not incidents:
        await msg.answer("✅ Активных инцидентов нет.")
        return
    now = int(time.time())
    lines = ["📋 <b>Активные инциденты:</b>\n"]
    for inc in incidents:
        dur = now - (inc.down_since_ts or now)
        mins = dur // 60
        lines.append(f"• [{inc.category}] {inc.title} — {mins} мин")
    await msg.answer("\n".join(lines))


@router.callback_query(F.data == "ch:on")
async def cb_channel_on(cq: CallbackQuery, db: Database) -> None:
    if not _is_admin(cq.from_user.id):
        await cq.answer("Нет доступа.", show_alert=True)
        return
    await db.set_setting("channel_alerts_enabled", "1")
    await cq.answer("Канал: ВКЛ", show_alert=False)
    if cq.message:
        await cq.message.edit_reply_markup(reply_markup=await _main_menu_kb(db))


@router.callback_query(F.data == "ch:off")
async def cb_channel_off(cq: CallbackQuery, db: Database) -> None:
    if not _is_admin(cq.from_user.id):
        await cq.answer("Нет доступа.", show_alert=True)
        return
    await db.set_setting("channel_alerts_enabled", "0")
    await cq.answer("Канал: ВЫКЛ", show_alert=False)
    if cq.message:
        await cq.message.edit_reply_markup(reply_markup=await _main_menu_kb(db))


@router.callback_query(F.data.startswith("ch:mute:"))
async def cb_channel_mute(cq: CallbackQuery, db: Database) -> None:
    if not _is_admin(cq.from_user.id):
        await cq.answer("Нет доступа.", show_alert=True)
        return
    hours = int(cq.data.split(":")[-1])
    until = int(time.time()) + hours * 3600
    await db.set_setting("channel_muted_until", str(until))
    await cq.answer(f"Канал замьючен на {hours}ч", show_alert=False)
    if cq.message:
        await cq.message.edit_reply_markup(reply_markup=await _main_menu_kb(db))


@router.callback_query(F.data == "ch:unmute")
async def cb_channel_unmute(cq: CallbackQuery, db: Database) -> None:
    if not _is_admin(cq.from_user.id):
        await cq.answer("Нет доступа.", show_alert=True)
        return
    await db.set_setting("channel_muted_until", "0")
    await cq.answer("Mute снят", show_alert=False)
    if cq.message:
        await cq.message.edit_reply_markup(reply_markup=await _main_menu_kb(db))


@router.callback_query(F.data == "status")
async def cb_status(cq: CallbackQuery, db: Database) -> None:
    if not _is_admin(cq.from_user.id):
        await cq.answer("Нет доступа.", show_alert=True)
        return
    await cq.answer()
    if cq.message:
        await _send_status(cq.message, db)


@router.callback_query(F.data == "muted_list")
async def cb_muted_list(cq: CallbackQuery, db: Database) -> None:
    if not _is_admin(cq.from_user.id):
        await cq.answer("Нет доступа.", show_alert=True)
        return
    await cq.answer()
    slugs = await db.list_muted_inbounds()
    if not slugs:
        text = "🔇 Замьюченных inbound'ов нет.\n\nДобавить: <code>/mute &lt;slug&gt;</code>\nУбрать: <code>/unmute &lt;slug&gt;</code>"
    else:
        text = "🔇 Замьючены:\n\n" + "\n".join(f"• <code>{s}</code>" for s in slugs)
    if cq.message:
        await cq.message.answer(text)


@router.message(Command("mute"))
async def cmd_mute(msg: Message, db: Database) -> None:
    if not _is_admin(msg.from_user.id if msg.from_user else None):
        await msg.answer("Нет доступа.")
        return
    parts = (msg.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await msg.answer("Использование: <code>/mute &lt;slug&gt;</code>\nСм. /menu → Замьюченные inbound'ы")
        return
    slug = parts[1].strip()
    await db.mute_inbound(slug)
    await msg.answer(f"🔇 <code>{slug}</code> замьючен.")


@router.message(Command("unmute"))
async def cmd_unmute(msg: Message, db: Database) -> None:
    if not _is_admin(msg.from_user.id if msg.from_user else None):
        await msg.answer("Нет доступа.")
        return
    parts = (msg.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await msg.answer("Использование: <code>/unmute &lt;slug&gt;</code>")
        return
    slug = parts[1].strip()
    await db.unmute_inbound(slug)
    await msg.answer(f"🔔 <code>{slug}</code> размьючен.")


@router.callback_query(F.data == "test_push")
async def cb_test_push(cq: CallbackQuery, bot: Bot, db: Database) -> None:
    if not _is_admin(cq.from_user.id):
        await cq.answer("Нет доступа.", show_alert=True)
        return
    try:
        await bot.send_message(settings.channel_id, "🧪 Тестовое сообщение от zspzvs-monitor-bot")
        await cq.answer("Отправлено в канал ✅", show_alert=False)
    except Exception as e:
        await cq.answer(f"Ошибка: {e}", show_alert=True)


# Все остальные сообщения от не-админа игнорируем тихо.
@router.message()
async def fallback(msg: Message) -> None:
    if not _is_admin(msg.from_user.id if msg.from_user else None):
        return
    await msg.answer("Команды: /menu, /status, /mute &lt;slug&gt;, /unmute &lt;slug&gt;")
