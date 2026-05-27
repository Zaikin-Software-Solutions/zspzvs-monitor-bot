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

    # Параметры цикла
    check_interval: int = Field(120, alias="CHECK_INTERVAL")
    host_down_threshold_ticks: int = Field(2, alias="HOST_DOWN_THRESHOLD_TICKS")
    alert_cooldown_secs: int = Field(3600, alias="ALERT_COOLDOWN_SECS")


settings = Settings()  # type: ignore[call-arg]
