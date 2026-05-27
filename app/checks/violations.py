"""check_violations — нотификации о нарушении лимита устройств (HWID/IP) у юзеров.

Аналог syvlech/remnawave-limiter в режиме `ACTION_MODE=manual`:
  1. GET /api/nodes — все ноды
  2. POST /api/ip-control/fetch-users-ips/{nodeUUID} → jobId
  3. GET /api/ip-control/fetch-users-ips/result/{jobId} — IP-адреса юзеров на ноде
  4. Агрегация: по каждому юзеру — set уникальных IP за окно ACTIVE_IP_WINDOW
  5. GET /api/users — узнаём `hwidDeviceLimit` каждого юзера (id → uuid → limit)
  6. Если active_ips > limit (и limit > 0) → пишем в violation_log
  7. Если за окно VIOLATION_WINDOW накопилось >= VIOLATION_THRESHOLD нарушений
     и прошёл COOLDOWN — шлём админу DM (только DM, не в канал!).

Все алерты идут админу в DM напрямую — не через Notifier (своя cooldown-логика).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import time

import httpx
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from ..config import settings
from ..db import Database
from ..formatter import admin_violation

log = logging.getLogger("check.violations")


async def check_violations(bot: Bot, db: Database) -> None:
    """Сделать одну проверку нарушений. Молча ничего не возвращает.

    Алерты пишет напрямую в DM админа.
    """
    if not settings.enable_limiter:
        return
    if not settings.remnawave_api_token:
        log.warning("ENABLE_LIMITER=true, но REMNAWAVE_API_TOKEN пуст — пропускаю.")
        return

    base = settings.remnawave_base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {settings.remnawave_api_token}"}

    try:
        async with httpx.AsyncClient(timeout=15, headers=headers) as client:
            users_by_id = await _fetch_users(client, base)
            if not users_by_id:
                log.info("violations: нет юзеров с hwidDeviceLimit > 0, пропуск")
                return

            node_uuids = await _fetch_active_node_uuids(client, base)
            if not node_uuids:
                log.info("violations: нет онлайн нод, пропуск")
                return

            # Параллельно запускаем job на каждой ноде.
            job_ids = await asyncio.gather(
                *[_start_fetch_ips(client, base, nu) for nu in node_uuids],
                return_exceptions=True,
            )
            results = await asyncio.gather(
                *[
                    _wait_job(client, base, j)
                    for j in job_ids
                    if isinstance(j, str)
                ],
                return_exceptions=True,
            )
    except Exception as e:  # noqa: BLE001 — нам важно не уронить scheduler
        log.warning("violations: API запросы упали: %s", e)
        return

    # Агрегация: user_id (числовой) → set уникальных свежих IP
    user_ips: dict[str, set[str]] = {}
    now = int(time.time())
    window = settings.limiter_active_ip_window

    for res in results:
        if isinstance(res, Exception) or not res:
            continue
        for user_entry in res.get("users") or []:
            uid = str(user_entry.get("userId", ""))
            if not uid:
                continue
            bucket = user_ips.setdefault(uid, set())
            for ip_entry in user_entry.get("ips") or []:
                ip = ip_entry.get("ip")
                if not ip:
                    continue
                if not _is_fresh(ip_entry.get("lastSeen"), now, window):
                    continue
                bucket.add(ip)

    # Сверяем с лимитами.
    threshold = settings.limiter_violation_threshold
    win_secs = settings.limiter_violation_window
    cooldown = settings.limiter_cooldown
    since = now - win_secs

    for uid, ips in user_ips.items():
        user = users_by_id.get(uid)
        if not user:
            continue
        limit = user.get("hwidDeviceLimit") or 0
        if limit <= 0:
            continue
        active = len(ips)
        if active <= limit:
            continue

        # Зафиксировали нарушение.
        user_uuid = user["uuid"]
        ips_list = sorted(ips)
        await db.add_violation(user_uuid, now, active, json.dumps(ips_list))

        # Сколько нарушений за окно?
        count = await db.count_recent_violations(user_uuid, since)
        if count < threshold:
            continue

        # Cooldown между алертами на одного юзера.
        last = await db.get_violation_alert_ts(user_uuid)
        if last and now - last < cooldown:
            continue

        text = admin_violation(
            username=user.get("username", "?"),
            user_uuid=user_uuid,
            limit=limit,
            actual=active,
            ips=ips_list,
        )
        try:
            await bot.send_message(settings.admin_tg_id, text)
            await db.set_violation_alert_ts(user_uuid, now)
            log.info(
                "violation alert sent: user=%s active=%d/%d",
                user.get("username"), active, limit,
            )
        except TelegramAPIError as e:
            log.warning("violation DM failed: %s", e)

    # Подчищаем старое раз в день (грубая отсечка: > 2*window).
    await db.prune_violation_log(now - max(win_secs * 2, 86400))


# ---------- internal helpers ----------


def _is_fresh(last_seen_iso: str | None, now_ts: int, window_secs: int) -> bool:
    """True если ISO-timestamp lastSeen младше window_secs."""
    if not last_seen_iso:
        return False
    try:
        # API даёт ISO с миллисекундами и Z, например 2026-05-27T14:21:53.000Z
        ts = dt.datetime.fromisoformat(last_seen_iso.replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return False
    return (now_ts - int(ts)) <= window_secs


async def _fetch_users(client: httpx.AsyncClient, base: str) -> dict[str, dict]:
    """Возвращает map id (str) → user dict. Качаем пачками по 250."""
    out: dict[str, dict] = {}
    start = 0
    size = 250
    while True:
        r = await client.get(f"{base}/api/users", params={"start": start, "size": size})
        r.raise_for_status()
        body = r.json().get("response", {})
        users = body.get("users") or []
        for u in users:
            uid = u.get("id")
            if uid is None:
                continue
            out[str(uid)] = u
        total = int(body.get("total") or 0)
        start += size
        if start >= total or not users:
            break
    return out


async def _fetch_active_node_uuids(client: httpx.AsyncClient, base: str) -> list[str]:
    r = await client.get(f"{base}/api/nodes")
    r.raise_for_status()
    nodes = r.json().get("response") or []
    return [
        n["uuid"]
        for n in nodes
        if n.get("isConnected") and not n.get("isDisabled")
    ]


async def _start_fetch_ips(
    client: httpx.AsyncClient, base: str, node_uuid: str
) -> str:
    r = await client.post(f"{base}/api/ip-control/fetch-users-ips/{node_uuid}")
    r.raise_for_status()
    body = r.json().get("response") or {}
    job_id = body.get("jobId")
    if not job_id:
        raise RuntimeError(f"fetch-users-ips: no jobId in response: {body}")
    return str(job_id)


async def _wait_job(
    client: httpx.AsyncClient,
    base: str,
    job_id: str,
    max_attempts: int = 10,
    delay: float = 1.0,
) -> dict | None:
    """Опрашиваем result/{jobId} пока isCompleted=true. Возвращаем `result` dict."""
    for _ in range(max_attempts):
        r = await client.get(f"{base}/api/ip-control/fetch-users-ips/result/{job_id}")
        r.raise_for_status()
        body = r.json().get("response") or {}
        if body.get("isCompleted"):
            if body.get("isFailed"):
                log.warning("fetch-users-ips job %s failed: %s", job_id, body)
                return None
            return body.get("result") or {}
        await asyncio.sleep(delay)
    log.warning("fetch-users-ips job %s did not finish in time", job_id)
    return None
