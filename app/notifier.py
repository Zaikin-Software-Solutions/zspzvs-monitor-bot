"""Маршрутизатор уведомлений: решает кому слать (admin DM / канал) и с каким текстом."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from .config import settings
from .db import Database
from .formatter import (
    admin_down, admin_up,
    channel_down, channel_up,
    channel_node_down, channel_node_up,
    country_from_name, short_name_for_channel,
)

log = logging.getLogger("notifier")


@dataclass(slots=True)
class Event:
    """Унифицированное событие, которое генерирует любая проверка.

    category: 'host' | 'node' | 'systemd' | 'docker' | 'tls' | 'load' | 'api' | 'backup' | 'disk'
    slug:     уникальный ID — стабильный (используется как ключ инцидента)
    title:    отображаемое имя (для админа полное, для канала — будет сокращено)
    status:   'down' | 'up'  (в первой версии бот сам считает consecutive_down и принимает решение)
    detail:   опциональный текст (например, last_status_message от RW)
    """
    category: str
    slug: str
    title: str
    status: str
    detail: str = ""


# Категории, события которых ИДУТ В КАНАЛ (если канал включён и не замьючен).
CHANNEL_CATEGORIES = {"host", "node"}


class Notifier:
    def __init__(self, bot: Bot, db: Database) -> None:
        self.bot = bot
        self.db = db

    async def process(self, event: Event) -> None:
        """Обработать одно событие проверки."""
        now = int(time.time())
        prev = await self.db.get_incident(event.slug)

        if event.status == "down":
            await self._handle_down(event, prev, now)
        elif event.status == "up":
            await self._handle_up(event, prev, now)

    async def _handle_down(self, event: Event, prev, now: int) -> None:
        prev_status = prev.status if prev else "up"
        prev_consec = prev.consecutive_down if prev else 0
        prev_last_alert = prev.last_alert_ts if prev else 0
        prev_down_since = prev.down_since_ts if prev else None
        prev_sent_to_channel = prev.last_sent_to_channel if prev else 0

        consec = prev_consec + 1
        down_since = prev_down_since or now
        threshold = settings.host_down_threshold_ticks if event.category == "host" else 1
        ready = consec >= threshold

        # Принимаем решение слать ли сейчас alert
        should_alert = False
        if ready:
            if prev_status == "up":  # первый раз перешёл в down
                should_alert = True
            else:
                # уже была down — проверяем cooldown
                if now - prev_last_alert >= settings.alert_cooldown_secs:
                    should_alert = True

        sent_to_channel = prev_sent_to_channel
        if should_alert:
            duration = now - down_since
            await self._send_admin(admin_down(event.category, event.title, event.detail, duration))

            if event.category in CHANNEL_CATEGORIES:
                if await self._channel_allowed() and not await self.db.is_inbound_muted(event.slug):
                    msg = self._channel_text_down(event)
                    if await self._send_channel(msg):
                        sent_to_channel = 1

        await self.db.upsert_incident(
            slug=event.slug, category=event.category, title=event.title,
            status="down",
            down_since_ts=down_since,
            consecutive_down=consec,
            last_alert_ts=now if should_alert else prev_last_alert,
            last_sent_to_channel=sent_to_channel,
        )

    async def _handle_up(self, event: Event, prev, now: int) -> None:
        # Если предыдущего инцидента не было — нет смысла слать "up", всё и так норм.
        if prev is None or prev.status == "up":
            # ничего не делаем, только апдейтим запись чтобы был «свежий» up
            if prev is None:
                await self.db.upsert_incident(
                    slug=event.slug, category=event.category, title=event.title,
                    status="up", down_since_ts=None, consecutive_down=0,
                    last_alert_ts=0, last_sent_to_channel=0,
                )
            return

        # Был down — шлём recovery
        duration = now - (prev.down_since_ts or now)
        await self._send_admin(admin_up(event.category, event.title, duration))

        # В канал шлём recovery только если down тоже уходил в канал
        if event.category in CHANNEL_CATEGORIES and prev.last_sent_to_channel:
            # Канал может быть выключен сейчас — но мы всё равно шлём (мы должны "закрыть" down)
            # ЕСЛИ канал был отключён вообще — то и down туда не уходил, и сюда не зайдём
            msg = self._channel_text_up(event, duration)
            await self._send_channel(msg)

        await self.db.upsert_incident(
            slug=event.slug, category=event.category, title=event.title,
            status="up", down_since_ts=None, consecutive_down=0,
            last_alert_ts=0, last_sent_to_channel=0,
        )

    def _channel_text_down(self, event: Event) -> str:
        if event.category == "host":
            cc = country_from_name(event.title)
            short = short_name_for_channel(event.title)
            return channel_down(cc, short)
        if event.category == "node":
            return channel_node_down(event.title, event.detail)
        return f"🔴 {event.title}"

    def _channel_text_up(self, event: Event, duration_secs: int) -> str:
        if event.category == "host":
            cc = country_from_name(event.title)
            short = short_name_for_channel(event.title)
            return channel_up(cc, short, duration_secs)
        if event.category == "node":
            return channel_node_up(event.title, duration_secs)
        return f"🟢 {event.title}"

    async def _channel_allowed(self) -> bool:
        if not await self.db.is_channel_enabled():
            return False
        if await self.db.is_channel_muted_now():
            return False
        return True

    async def _send_admin(self, text: str) -> None:
        try:
            await self.bot.send_message(settings.admin_tg_id, text)
        except TelegramAPIError as e:
            log.warning("admin send failed: %s", e)

    async def _send_channel(self, text: str) -> bool:
        try:
            await self.bot.send_message(settings.channel_id, text)
            return True
        except TelegramAPIError as e:
            log.warning("channel send failed: %s", e)
            return False
