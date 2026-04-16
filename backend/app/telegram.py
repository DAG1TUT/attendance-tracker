from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.fraud import REASON_LABELS

logger = logging.getLogger(__name__)

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


async def send_telegram(text: str) -> None:
    """Fire-and-forget. Silently skips if Telegram is not configured."""
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return
    url = _TELEGRAM_API.format(token=settings.telegram_bot_token)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                url,
                json={
                    "chat_id": settings.telegram_chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                },
            )
    except Exception as exc:
        logger.warning("Telegram send failed: %s", exc)


async def notify_suspicious(
    employee_name: str,
    action: str,
    reason: str,
    ip_address: str,
    timestamp_str: str,
) -> None:
    action_label = "Приход" if action == "check_in" else "Уход"
    reason_label = REASON_LABELS.get(reason, reason)
    text = (
        f"⚠️ <b>Подозрительное событие</b>\n"
        f"Сотрудник: {employee_name}\n"
        f"Действие: {action_label}\n"
        f"Причина: {reason_label}\n"
        f"IP: {ip_address}\n"
        f"Время: {timestamp_str}"
    )
    await send_telegram(text)


async def notify_late(employee_name: str, checked_in_at: str) -> None:
    text = (
        f"🕐 <b>Опоздание</b>\n"
        f"Сотрудник: {employee_name}\n"
        f"Пришёл в: {checked_in_at}\n"
        f"Начало смены: {settings.shift_start_hour:02d}:{settings.late_threshold_minutes:02d}"
    )
    await send_telegram(text)
