from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status

from app.admin.schemas import (
    AdminLogOut,
    EmployeeCreate,
    EmployeeOut,
    EmployeeUpdate,
    TodayEntry,
    TodayStats,
)
from app.auth.service import hash_password
from app.config import settings
from app.dependencies import AdminOnly, get_db

router = APIRouter(prefix="/admin", tags=["admin"])


# ── Employees ─────────────────────────────────────────────────────────────────

@router.get("/employees", response_model=list[EmployeeOut])
async def list_employees(
    db: Annotated[asyncpg.Pool, Depends(get_db)],
    _: Annotated[dict, AdminOnly],
    is_active: bool | None = None,
) -> list[dict]:
    query = "SELECT id, phone, name, role, is_active, created_at FROM users"
    args: list = []
    if is_active is not None:
        query += " WHERE is_active = $1"
        args.append(is_active)
    query += " ORDER BY name"
    async with db.acquire() as conn:
        rows = await conn.fetch(query, *args)
    return [dict(r) for r in rows]


@router.post("/employees", status_code=status.HTTP_201_CREATED, response_model=EmployeeOut)
async def create_employee(
    body: EmployeeCreate,
    db: Annotated[asyncpg.Pool, Depends(get_db)],
    _: Annotated[dict, AdminOnly],
) -> dict:
    async with db.acquire() as conn:
        existing = await conn.fetchval("SELECT id FROM users WHERE phone = $1", body.phone)
        if existing:
            raise HTTPException(status_code=409, detail="Телефон уже занят")

        row = await conn.fetchrow(
            """
            INSERT INTO users (phone, name, password_hash, role)
            VALUES ($1, $2, $3, $4)
            RETURNING id, phone, name, role, is_active, created_at
            """,
            body.phone,
            body.name,
            hash_password(body.password),
            body.role,
        )
    return dict(row)


@router.patch("/employees/{employee_id}", response_model=EmployeeOut)
async def update_employee(
    employee_id: int,
    body: EmployeeUpdate,
    db: Annotated[asyncpg.Pool, Depends(get_db)],
    _: Annotated[dict, AdminOnly],
) -> dict:
    async with db.acquire() as conn:
        user = await conn.fetchrow("SELECT id FROM users WHERE id = $1", employee_id)
        if not user:
            raise HTTPException(status_code=404, detail="Сотрудник не найден")

        updates = []
        args: list = []
        idx = 1

        if body.name is not None:
            updates.append(f"name = ${idx}")
            args.append(body.name)
            idx += 1
        if body.phone is not None:
            updates.append(f"phone = ${idx}")
            args.append(body.phone)
            idx += 1
        if body.password is not None:
            updates.append(f"password_hash = ${idx}")
            args.append(hash_password(body.password))
            idx += 1
        if body.role is not None:
            updates.append(f"role = ${idx}")
            args.append(body.role)
            idx += 1
        if body.is_active is not None:
            updates.append(f"is_active = ${idx}")
            args.append(body.is_active)
            idx += 1

        if not updates:
            raise HTTPException(status_code=400, detail="Нет данных для обновления")

        args.append(employee_id)
        row = await conn.fetchrow(
            f"""
            UPDATE users SET {', '.join(updates)}
            WHERE id = ${idx}
            RETURNING id, phone, name, role, is_active, created_at
            """,
            *args,
        )
    return dict(row)


@router.delete("/employees/{employee_id}")
async def delete_employee(
    employee_id: int,
    db: Annotated[asyncpg.Pool, Depends(get_db)],
    _: Annotated[dict, AdminOnly],
) -> dict:
    async with db.acquire() as conn:
        result = await conn.execute("DELETE FROM users WHERE id = $1", employee_id)
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    return {"message": "Удалено"}


# ── Logs ──────────────────────────────────────────────────────────────────────

@router.get("/logs", response_model=list[AdminLogOut])
async def list_logs(
    db: Annotated[asyncpg.Pool, Depends(get_db)],
    _: Annotated[dict, AdminOnly],
    user_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    suspicious_only: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    conditions = []
    args: list = []
    idx = 1

    if user_id is not None:
        conditions.append(f"al.user_id = ${idx}")
        args.append(user_id)
        idx += 1
    if suspicious_only:
        conditions.append("al.is_suspicious = TRUE")
    if date_from:
        conditions.append(f"al.timestamp >= ${idx}::timestamptz")
        args.append(date_from)
        idx += 1
    if date_to:
        conditions.append(f"al.timestamp <= ${idx}::timestamptz")
        args.append(date_to)
        idx += 1

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    args.extend([limit, offset])

    query = f"""
        SELECT al.id, al.user_id, u.name AS employee_name,
               al.action, al.timestamp, al.ip_address,
               al.device_id, al.user_agent,
               al.is_suspicious, al.suspicious_reason
        FROM attendance_logs al
        JOIN users u ON u.id = al.user_id
        {where}
        ORDER BY al.timestamp DESC
        LIMIT ${idx} OFFSET ${idx + 1}
    """
    async with db.acquire() as conn:
        rows = await conn.fetch(query, *args)
    return [dict(r) for r in rows]


@router.get("/logs/suspicious", response_model=list[AdminLogOut])
async def list_suspicious_logs(
    db: Annotated[asyncpg.Pool, Depends(get_db)],
    _: Annotated[dict, AdminOnly],
    limit: int = 50,
) -> list[dict]:
    async with db.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT al.id, al.user_id, u.name AS employee_name,
                   al.action, al.timestamp, al.ip_address,
                   al.device_id, al.user_agent,
                   al.is_suspicious, al.suspicious_reason
            FROM attendance_logs al
            JOIN users u ON u.id = al.user_id
            WHERE al.is_suspicious = TRUE
            ORDER BY al.timestamp DESC
            LIMIT $1
            """,
            limit,
        )
    return [dict(r) for r in rows]


# ── Today stats ───────────────────────────────────────────────────────────────

@router.get("/stats/today", response_model=TodayStats)
async def stats_today(
    db: Annotated[asyncpg.Pool, Depends(get_db)],
    _: Annotated[dict, AdminOnly],
) -> dict:
    now = datetime.now(timezone.utc)
    shift_total_minutes = settings.shift_start_hour * 60 + settings.late_threshold_minutes

    async with db.acquire() as conn:
        # All active employees
        all_employees = await conn.fetch(
            "SELECT id, name FROM users WHERE is_active = TRUE AND role = 'employee' ORDER BY name"
        )

        # Today's first check-in per employee
        today_checkins = await conn.fetch(
            """
            SELECT DISTINCT ON (user_id)
                user_id, timestamp
            FROM attendance_logs
            WHERE action = 'check_in'
              AND timestamp >= NOW()::date
            ORDER BY user_id, timestamp ASC
            """
        )

    checkin_map = {r["user_id"]: r["timestamp"] for r in today_checkins}

    present = []
    absent = []
    late = []

    for emp in all_employees:
        uid = emp["id"]
        name = emp["name"]

        if uid not in checkin_map:
            absent.append(TodayEntry(user_id=uid, name=name))
        else:
            ts: datetime = checkin_map[uid]
            checked_in_str = ts.strftime("%H:%M")
            entry_minutes = ts.hour * 60 + ts.minute

            if entry_minutes > shift_total_minutes:
                late_min = entry_minutes - shift_total_minutes
                late.append(TodayEntry(
                    user_id=uid,
                    name=name,
                    checked_in_at=checked_in_str,
                    late_minutes=late_min,
                ))
            else:
                present.append(TodayEntry(user_id=uid, name=name, checked_in_at=checked_in_str))

    return {"present": present, "absent": absent, "late": late}
