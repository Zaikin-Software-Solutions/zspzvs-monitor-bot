"""check_backup — свежесть бэкапа Remnawave в R2 (S3-совместимое хранилище).

Бот ходит в R2-бакет (S3_BUCKET) через S3 API и берёт mtime самого свежего
объекта `remnawave_backup_*`. Алерт если он старше BACKUP_MAX_AGE_HOURS.

Если S3_ENDPOINT не задан — проверка молча пропускается (нет источника).
Раньше проверка читала textfile-метрику rw_backup_last_mtime_seconds от
node-exporter, который убран — теперь источник правды это сам R2.
"""

from __future__ import annotations

import asyncio
import logging
import time

from ..config import settings
from ..notifier import Event

log = logging.getLogger("check.backup")


def _latest_backup_epoch() -> float | None:
    """Синхронно (boto3) находит mtime самого свежего объекта бэкапа в R2.

    Возвращает epoch-секунды последнего объекта или None если бакет пуст
    либо S3 недоступен.
    """
    import boto3
    from botocore.config import Config

    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region or "auto",
        config=Config(signature_version="s3v4", connect_timeout=8, read_timeout=8, retries={"max_attempts": 2}),
    )
    prefix = settings.s3_prefix or ""
    paginator = client.get_paginator("list_objects_v2")
    latest: float | None = None
    for page in paginator.paginate(Bucket=settings.s3_bucket, Prefix=prefix):
        for obj in page.get("Contents", []) or []:
            # учитываем только архивы бэкапа
            if "remnawave_backup_" not in obj["Key"]:
                continue
            ts = obj["LastModified"].timestamp()
            if latest is None or ts > latest:
                latest = ts
    return latest


async def check_backup() -> list[Event]:
    if not settings.s3_endpoint or not settings.s3_bucket:
        log.info("S3_ENDPOINT/S3_BUCKET не заданы — backup-проверка пропущена")
        return []

    try:
        latest = await asyncio.to_thread(_latest_backup_epoch)
    except Exception as e:
        log.warning("R2 backup check failed: %s", e)
        # Не молчим: недоступность R2 — это само по себе проблема бэкапа.
        return [Event(
            category="backup",
            slug="backup:r2",
            title="RW backup → R2",
            status="down",
            detail=f"R2 недоступен: {str(e)[:80]}",
        )]

    if latest is None:
        return [Event(
            category="backup",
            slug="backup:r2",
            title="RW backup → R2",
            status="down",
            detail=f"в бакете {settings.s3_bucket} нет бэкапов",
        )]

    age_h = (time.time() - latest) / 3600
    status = "down" if age_h > settings.backup_max_age_hours else "up"
    return [Event(
        category="backup",
        slug="backup:r2",
        title="RW backup → R2",
        status=status,
        detail=f"последний бэкап {age_h:.1f}ч назад (порог {settings.backup_max_age_hours}ч)",
    )]
