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
    allowed_networks: str = "46.172.16.80/32"

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_webhook_secret: str = ""          # Secret for webhook verification
    telegram_allowed_users: str = ""           # Comma-separated allowed Telegram user IDs (empty = only telegram_chat_id)

    # OpenAI (for smarter bot NL understanding)
    openai_api_key: str = ""

    # Shift config
    shift_start_hour: int = 10
    late_threshold_minutes: int = 0
    timezone: str = "Europe/Moscow"


settings = Settings()
