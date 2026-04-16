from __future__ import annotations

import asyncpg

REASON_LABELS: dict[str, str] = {
    "new_device": "Новое устройство",
    "ip_change": "Смена IP-адреса",
    "duplicate_device": "Устройство уже использовалось другим сотрудником (<30 мин)",
}


async def evaluate_fraud(
    conn: asyncpg.Connection,
    user_id: int,
    device_id: str,
    ip_address: str,
    action: str,  # "check_in" | "check_out" | "login"
) -> tuple[bool, str | None]:
    """
    Returns (is_suspicious, reason_code | None).

    Rules:
      1. New device for this user → "new_device"
      2. IP changed since last logged event → "ip_change"
      3. Same device used for another user's check_in within 30 min → "duplicate_device"
    """
    # Rule 1: new device?
    row = await conn.fetchrow(
        "SELECT id FROM known_devices WHERE user_id = $1 AND device_id = $2",
        user_id,
        device_id,
    )
    if row is None:
        await conn.execute(
            "INSERT INTO known_devices (user_id, device_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            user_id,
            device_id,
        )
        return (True, "new_device")
    else:
        await conn.execute(
            "UPDATE known_devices SET last_seen = NOW() WHERE user_id = $1 AND device_id = $2",
            user_id,
            device_id,
        )

    # Rule 2: IP changed from last session?
    last = await conn.fetchrow(
        """
        SELECT ip_address FROM attendance_logs
        WHERE user_id = $1
        ORDER BY timestamp DESC
        LIMIT 1
        """,
        user_id,
    )
    if last and last["ip_address"] != ip_address:
        return (True, "ip_change")

    # Rule 3: same device used by another user's check_in in last 30 min?
    if action == "check_in":
        dup = await conn.fetchrow(
            """
            SELECT id FROM attendance_logs
            WHERE device_id = $1
              AND user_id != $2
              AND action = 'check_in'
              AND timestamp >= NOW() - INTERVAL '30 minutes'
            """,
            device_id,
            user_id,
        )
        if dup:
            return (True, "duplicate_device")

    return (False, None)
