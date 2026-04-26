from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Annotated
from zoneinfo import ZoneInfo

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.attendance.schemas import AttendanceLogOut, CheckRequest, StatusOut
from app.config import settings
from app.dependencies import AnyRole, LocalNetworkGuard, get_db, get_client_ip
from app.fraud import evaluate_fraud
from app.telegram import notify_late, notify_suspicious

router = APIRouter(prefix="/attendance", tags=["attendance"])

_MOSCOW = ZoneInfo(settings.timezone)


def _is_late(now: datetime) -> bool:
    """Check if current Moscow time is past the shift start threshold."""
    now_moscow = now.astimezone(_MOSCOW)
    total_minutes = settings.shift_start_hour * 60 + settings.late_threshold_minutes
    current_minutes = now_moscow.hour * 60 + now_moscow.minute
    return current_minutes > total_minutes


@router.post("/check-in", dependencies=[LocalNetworkGuard])
async def check_in(
    body: CheckRequest,
    request: Request,
    current_user: Annotated[dict, AnyRole],
    db: Annotated[asyncpg.Pool, Depends(get_db)],
) -> dict:
    ip_address = get_client_ip(request)
    user_id = current_user["id"]

    async with db.acquire() as conn:
        # Prevent duplicate check-in
        last_log = await conn.fetchrow(
            """
            SELECT action FROM attendance_logs
            WHERE user_id = $1
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            user_id,
        )
        if last_log and last_log["action"] == "check_in":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Вы уже отметились как пришедший",
            )

        is_suspicious, reason = await evaluate_fraud(
            conn, user_id, body.device_id, ip_address, "check_in"
        )

        row = await conn.fetchrow(
            """
            INSERT INTO attendance_logs
                (user_id, action, ip_address, device_id, user_agent, is_suspicious, suspicious_reason)
            VALUES ($1, 'check_in', $2, $3, $4, $5, $6)
            RETURNING id, timestamp
            """,
            user_id,
            ip_address,
            body.device_id,
            body.user_agent,
            is_suspicious,
            reason,
        )

    ts: datetime = row["timestamp"]
    ts_str = ts.strftime("%d.%m.%Y %H:%M")

    if is_suspicious:
        asyncio.create_task(
            notify_suspicious(current_user["name"], "check_in", reason, ip_address, ts_str)
        )

    # Check for lateness (compare in UTC)
    now_utc = datetime.now(timezone.utc)
    if _is_late(now_utc):
        asyncio.create_task(notify_late(current_user["name"], ts.strftime("%H:%M")))

    return {
        "log_id": row["id"],
        "timestamp": ts,
        "is_suspicious": is_suspicious,
        "message": "Приход зафиксирован",
    }


@router.post("/check-out", dependencies=[LocalNetworkGuard])
async def check_out(
    body: CheckRequest,
    request: Request,
    current_user: Annotated[dict, AnyRole],
    db: Annotated[asyncpg.Pool, Depends(get_db)],
) -> dict:
    ip_address = get_client_ip(request)
    user_id = current_user["id"]

    async with db.acquire() as conn:
        last_log = await conn.fetchrow(
            """
            SELECT id, action, timestamp FROM attendance_logs
            WHERE user_id = $1
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            user_id,
        )
        if not last_log or last_log["action"] == "check_out":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Вы не отметились как пришедший",
            )

        is_suspicious, reason = await evaluate_fraud(
            conn, user_id, body.device_id, ip_address, "check_out"
        )

        row = await conn.fetchrow(
            """
            INSERT INTO attendance_logs
                (user_id, action, ip_address, device_id, user_agent, is_suspicious, suspicious_reason)
            VALUES ($1, 'check_out', $2, $3, $4, $5, $6)
            RETURNING id, timestamp
            """,
            user_id,
            ip_address,
            body.device_id,
            body.user_agent,
            is_suspicious,
            reason,
        )

    ts: datetime = row["timestamp"]
    ts_str = ts.strftime("%d.%m.%Y %H:%M")

    # Calculate duration
    check_in_ts: datetime = last_log["timestamp"]
    duration_minutes = int((ts - check_in_ts).total_seconds() / 60)

    if is_suspicious:
        asyncio.create_task(
            notify_suspicious(current_user["name"], "check_out", reason, ip_address, ts_str)
        )

    return {
        "log_id": row["id"],
        "timestamp": ts,
        "duration_minutes": duration_minutes,
        "message": "Уход зафиксирован",
    }


@router.get("/status", response_model=StatusOut)
async def get_status(
    current_user: Annotated[dict, AnyRole],
    db: Annotated[asyncpg.Pool, Depends(get_db)],
) -> dict:
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT action, timestamp FROM attendance_logs
            WHERE user_id = $1
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            current_user["id"],
        )
    if not row:
        return {"action": None, "since": None}
    return {"action": row["action"], "since": row["timestamp"]}


@router.get("/week")
async def get_my_week(
    current_user: Annotated[dict, AnyRole],
    db: Annotated[asyncpg.Pool, Depends(get_db)],
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    """Employee's own weekly schedule."""
    today = datetime.now(_MOSCOW).date()
    if not date_from:
        date_from = today - timedelta(days=today.weekday())  # Monday
    if not date_to:
        date_to = date_from + timedelta(days=6)

    async with db.acquire() as conn:
        logs = await conn.fetch(
            """SELECT action, timestamp
               FROM attendance_logs
               WHERE user_id = $1
                 AND (timestamp AT TIME ZONE $2)::date >= $3
                 AND (timestamp AT TIME ZONE $2)::date <= $4
                 AND action IN ('check_in', 'check_out')
               ORDER BY timestamp ASC""",
            current_user["id"], settings.timezone, date_from, date_to,
        )

    dates = [date_from + timedelta(days=i) for i in range((date_to - date_from).days + 1)]

    day_logs: dict[date, list] = defaultdict(list)
    for log in logs:
        d = log["timestamp"].astimezone(_MOSCOW).date()
        day_logs[d].append({"action": log["action"], "timestamp": log["timestamp"]})

    cells = []
    total_hours = 0.0
    for d in dates:
        events = sorted(day_logs.get(d, []), key=lambda x: x["timestamp"])
        check_in_ts = check_out_ts = last_in = None
        total_sec = 0.0
        for ev in events:
            if ev["action"] == "check_in":
                if check_in_ts is None:
                    check_in_ts = ev["timestamp"]
                last_in = ev["timestamp"]
            elif ev["action"] == "check_out" and last_in:
                check_out_ts = ev["timestamp"]
                total_sec += (ev["timestamp"] - last_in).total_seconds()
                last_in = None
        hours = round(total_sec / 3600, 1)
        total_hours += hours
        cells.append({
            "date": d.isoformat(),
            "check_in": check_in_ts.isoformat() if check_in_ts else None,
            "check_out": check_out_ts.isoformat() if check_out_ts else None,
            "hours": hours,
        })

    return {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "total_hours": round(total_hours, 1),
        "days": cells,
    }


@router.get("/history", response_model=list[AttendanceLogOut])
async def get_history(
    current_user: Annotated[dict, AnyRole],
    db: Annotated[asyncpg.Pool, Depends(get_db)],
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    async with db.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, action, timestamp, ip_address, device_id, is_suspicious, suspicious_reason
            FROM attendance_logs
            WHERE user_id = $1
            ORDER BY timestamp DESC
            LIMIT $2 OFFSET $3
            """,
            current_user["id"],
            limit,
            offset,
        )
    return [dict(r) for r in rows]
