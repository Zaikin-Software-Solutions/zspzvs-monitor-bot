"""Конфиг бота, читается из переменных окружения / .env."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Telegram
    bot_token: str = Field(..., alias="BOT_TOKEN")
    admin_tg_id: int = Field(..., alias="ADMIN_TG_ID")
    channel_id: int = Field(..., alias="CHANNEL_ID")

    # Источники
    prometheus_url: str = Field("http://prometheus:9090", alias="PROMETHEUS_URL")
    remnawave_db_dsn: str = Field(
        "postgres://postgres:postgres@remnawave-db:5432/postgres",
        alias="REMNAWAVE_DB_DSN",
    )
    remnawave_base_url: str = Field("https://crm.zspzvs.ru", alias="REMNAWAVE_BASE_URL")

    # Хранилище
    db_path: str = Field("/data/bot.db", alias="DB_PATH")

    # === Backup-проверка (R2 / S3-совместимое) ===
    # Бот проверяет свежесть последнего объекта бэкапа в R2-бакете.
    # Если не задан S3_ENDPOINT — backup-проверка молча пропускается.
    s3_endpoint: str = Field("", alias="S3_ENDPOINT")
    s3_access_key: str = Field("", alias="S3_ACCESS_KEY")
    s3_secret_key: str = Field("", alias="S3_SECRET_KEY")
    s3_bucket: str = Field("", alias="S3_BUCKET")
    s3_region: str = Field("auto", alias="S3_REGION")
    s3_prefix: str = Field("", alias="S3_PREFIX")
    # Алерт если самый свежий бэкап старше этого (часы).
    backup_max_age_hours: int = Field(26, alias="BACKUP_MAX_AGE_HOURS")

    # Параметры цикла
    check_interval: int = Field(120, alias="CHECK_INTERVAL")
    host_down_threshold_ticks: int = Field(2, alias="HOST_DOWN_THRESHOLD_TICKS")
    alert_cooldown_secs: int = Field(3600, alias="ALERT_COOLDOWN_SECS")

    # === Flap-detection ===
    # Сколько мини-отвалов (down→up без достижения DOWN-порога) за окно
    # вызовут отдельный «нестабилен» алерт.
    flap_threshold_count: int = Field(3, alias="FLAP_THRESHOLD_COUNT")
    # Окно (секунды) в котором считаем флапы. 1800 = 30 мин.
    flap_window_secs: int = Field(1800, alias="FLAP_WINDOW_SECS")
    # Cooldown между повторными «нестабилен» алертами по одному slug.
    flap_alert_cooldown_secs: int = Field(3600, alias="FLAP_ALERT_COOLDOWN_SECS")

    # === Limiter (нотификации только) ===
    # Включает проверку нарушений лимита устройств (HWID/IP) у юзеров.
    enable_limiter: bool = Field(False, alias="ENABLE_LIMITER")
    # JWT для REST-API Remnawave (role=API). Нужен только лимитеру.
    remnawave_api_token: str = Field("", alias="REMNAWAVE_API_TOKEN")
    # Сколько секунд между check_violations (отдельно от общего check_interval).
    limiter_check_interval: int = Field(60, alias="LIMITER_CHECK_INTERVAL")
    # Сколько нарушений за окно нужно набрать чтобы кинуть алерт.
    limiter_violation_threshold: int = Field(3, alias="LIMITER_VIOLATION_THRESHOLD")
    # Окно скользящего счётчика нарушений (секунды).
    limiter_violation_window: int = Field(3600, alias="LIMITER_VIOLATION_WINDOW")
    # Cooldown между одинаковыми алертами на одного юзера (секунды).
    limiter_cooldown: int = Field(300, alias="LIMITER_COOLDOWN")
    # Окно «свежести» IP — IP считается активным если lastSeen <= этого (секунды).
    limiter_active_ip_window: int = Field(120, alias="LIMITER_ACTIVE_IP_WINDOW")


settings = Settings()  # type: ignore[call-arg]
