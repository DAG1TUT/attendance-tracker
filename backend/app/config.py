from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql://postgres:password@localhost:5432/attendance_db"

    # JWT
    jwt_secret: str = "CHANGE_THIS_TO_A_LONG_RANDOM_STRING"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 30

    # Bootstrap
    admin_bootstrap_secret: str = "CHANGE_THIS_TOO"

    # Network security (comma-separated CIDRs, empty = disabled)
    allowed_networks: str = "192.168.0.0/16,10.0.0.0/8"

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Shift config
    shift_start_hour: int = 10
    late_threshold_minutes: int = 0
    timezone: str = "Europe/Moscow"


settings = Settings()
