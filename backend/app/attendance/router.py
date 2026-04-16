from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.attendance.schemas import AttendanceLogOut, CheckRequest, StatusOut
from app.config import settings
from app.dependencies import AnyRole, LocalNetworkGuard, get_db, get_client_ip
from app.fraud import evaluate_fraud
from app.telegram import notify_late, notify_suspicious

router = APIRouter(prefix="/attendance", tags=["attendance"])


def _is_late(now: datetime) -> bool:
    """Check if the current time is past the late threshold."""
    threshold_minute = settings.late_threshold_minutes
    threshold_hour = settings.shift_start_hour
    # Calculate shift start + late threshold in minutes
    total_minutes = threshold_hour * 60 + threshold_minute
    current_minutes = now.hour * 60 + now.minute
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
