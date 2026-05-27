"""Набор проверок мониторинга. Каждая возвращает list[Event]."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from ..notifier import Event

Check = Callable[[], Awaitable[list[Event]]]
