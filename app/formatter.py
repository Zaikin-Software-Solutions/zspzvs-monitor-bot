"""Форматирование сообщений для DM админу и для канала.

Канал: коротко, с эмодзи-флагами. По требованию пользователя — русский полный, recovery всегда.
DM админу: подробнее (host, port, длительность).
"""

from __future__ import annotations

# Карта алиасов страны → эмодзи-флаг и русское название.
COUNTRY_FLAGS = {
    "fi": ("🇫🇮", "Финляндия"),
    "ru": ("🇷🇺", "Россия"),
    "nl": ("🇳🇱", "Нидерланды"),
    "uk": ("🇬🇧", "Великобритания"),
    "us": ("🇺🇸", "США"),
    "de": ("🇩🇪", "Германия"),
}


def country_from_name(name: str) -> str:
    """Извлечь ISO-код страны из xray-checker name (там стоит эмодзи флага)."""
    if "🇫🇮" in name or "Финл" in name.lower() or "FI" in name:
        return "fi"
    if "🇷🇺" in name or "росс" in name.lower() or "RU" in name:
        return "ru"
    if "🇳🇱" in name or "нидерл" in name.lower() or "NL" in name:
        return "nl"
    if "🇬🇧" in name or "велик" in name.lower() or "UK" in name:
        return "uk"
    if "🇺🇸" in name:
        return "us"
    if "🇩🇪" in name:
        return "de"
    return ""


def short_name_for_channel(name: str) -> str:
    """Подрезаем название xray-checker для канала: убираем декорации, оставляем суть.

    '🇫🇮🔗 Финляндия (TLS·TCP)' → 'Финляндия TLS·TCP'
    """
    s = name
    # уберём ведущий эмодзи + 🔗
    for emoji in ("🇫🇮", "🇷🇺", "🇳🇱", "🇬🇧", "🇺🇸", "🇩🇪", "🔗", "★"):
        s = s.replace(emoji, "")
    s = s.replace("()", "").replace("  ", " ").strip()
    # уберём скобки
    s = s.replace("(", "").replace(")", "")
    return s


def fmt_duration(seconds: int) -> str:
    """Длительность в минутах/часах для русского текста."""
    if seconds < 60:
        return f"{seconds} сек"
    mins = seconds // 60
    if mins < 60:
        return f"{mins} мин"
    hours = mins // 60
    rem = mins % 60
    if rem == 0:
        return f"{hours} ч"
    return f"{hours} ч {rem} мин"


def channel_down(country_code: str, short_name: str) -> str:
    """Краткое сообщение в канал об отвале хоста."""
    flag, _ = COUNTRY_FLAGS.get(country_code, ("⚫", ""))
    return f"🔴 {flag} {short_name} — упало"


def channel_up(country_code: str, short_name: str, duration_secs: int) -> str:
    """Краткое сообщение в канал о восстановлении хоста."""
    flag, _ = COUNTRY_FLAGS.get(country_code, ("⚫", ""))
    return f"🟢 {flag} {short_name} — восстановлено ({fmt_duration(duration_secs)})"


def channel_node_down(node_name: str, reason: str = "") -> str:
    """Краткое сообщение в канал об отвале RW-ноды."""
    suffix = f": {reason}" if reason else ""
    return f"🔴 Нода {node_name} — отключилась{suffix}"


def channel_node_up(node_name: str, duration_secs: int) -> str:
    """Краткое сообщение в канал о восстановлении ноды."""
    return f"🟢 Нода {node_name} — подключилась ({fmt_duration(duration_secs)})"


def admin_down(category: str, title: str, detail: str = "", duration_secs: int = 0) -> str:
    """Подробное сообщение админу в DM. HTML-разметка."""
    cat_icon = {
        "host": "🌐",
        "node": "🖥",
        "systemd": "⚙️",
        "docker": "🐳",
        "tls": "🔐",
        "load": "📈",
        "api": "🔌",
        "backup": "💾",
        "disk": "💽",
    }.get(category, "❗")
    msg = f"{cat_icon}❌ <b>{title}</b>"
    if detail:
        msg += f"\n<code>{detail}</code>"
    if duration_secs:
        msg += f"\n⏱ <i>длится {fmt_duration(duration_secs)}</i>"
    return msg


def admin_violation(
    *,
    username: str,
    user_uuid: str,
    limit: int,
    actual: int,
    ips: list[str],
    asns: list[str] | None = None,
) -> str:
    """Алерт админу о нарушении лимита устройств у юзера.

    Кнопок пока нет — только текст с подсказкой что делать через RW панель.
    """
    ips_str = ", ".join(ips) if ips else "—"
    msg = (
        "⚠️ <b>Нарушение лимитов</b>\n"
        f"Юзер: <b>{username}</b> (<code>{user_uuid}</code>)\n"
        f"Лимит: <b>{limit}</b> устройств, фактически: <b>{actual}</b>\n"
        f"IPs: <code>{ips_str}</code>"
    )
    if asns:
        msg += f"\nASN/страны: {', '.join(asns)}"
    msg += (
        "\n\n<i>Действия пока через RW-панель: можно отключить юзера, "
        "сбросить трафик или поднять лимит устройств.</i>"
    )
    return msg


def admin_flap(*, title: str, count: int, window_min: int) -> str:
    """Сообщение админу о нестабильности (множество флапов за окно)."""
    return (
        f"⚠️ <b>{title}</b> — нестабилен\n"
        f"<i>{count} коротких отвалов за {window_min} мин.</i>"
    )


def channel_flap(country_code: str, short_name: str, count: int, window_min: int) -> str:
    """Краткое сообщение в канал о нестабильности."""
    flag, _ = COUNTRY_FLAGS.get(country_code, ("⚫", ""))
    return f"⚠️ {flag} {short_name} — нестабилен ({count} флапов за {window_min} мин)"


def admin_up(category: str, title: str, duration_secs: int = 0) -> str:
    """Подробное сообщение админу о восстановлении."""
    cat_icon = {
        "host": "🌐",
        "node": "🖥",
        "systemd": "⚙️",
        "docker": "🐳",
        "tls": "🔐",
        "load": "📈",
        "api": "🔌",
        "backup": "💾",
        "disk": "💽",
    }.get(category, "✅")
    msg = f"{cat_icon}✅ <b>{title}</b> — восстановилось"
    if duration_secs:
        msg += f" ({fmt_duration(duration_secs)})"
    return msg
