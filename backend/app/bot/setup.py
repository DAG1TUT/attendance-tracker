"""Register webhook URL with Telegram API."""
from __future__ import annotations

import httpx

from app.config import settings


async def register_webhook(base_url: str) -> dict:
    """Call this to register the webhook with Telegram."""
    if not settings.telegram_bot_token:
        return {"error": "No bot token configured"}

    webhook_url = f"{base_url.rstrip('/')}/api/v1/telegram/webhook"
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/setWebhook"

    payload: dict = {"url": webhook_url, "allowed_updates": ["message"]}
    if settings.telegram_webhook_secret:
        payload["secret_token"] = settings.telegram_webhook_secret

    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(url, json=payload)
        return r.json()
