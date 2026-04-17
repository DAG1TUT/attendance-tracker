from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status

from app.admin.schemas import (
    AdminLogOut,
    EmployeeCreate,
    EmployeeOut,
    EmployeeUpdate,
    RevenueOut,
    RevenueUpsert,
    SalaryEntry,
    SalaryReport,
    TodayEntry,
    TodayStats,
)
from app.auth.service import hash_password
from app.config import settings
from app.dependencies import AdminOnly, get_db

router = APIRouter(prefix="/admin", tags=["admin"])


# ── Pending approvals ─────────────────────────────────────────────────────────

@router.get("/employees/pending", response_model=list[EmployeeOut])
async def list_pending(
    db: Annotated[asyncpg.Pool, Depends(get_db)],
    _: Annotated[dict, AdminOnly],
) -> list[dict]:
    async with db.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, phone, name, role, is_active, status,
                      hourly_rate, bonus_percent, created_at
               FROM users WHERE status = 'pending' ORDER BY created_at"""
        )
    return [dict(r) for r in rows]


@router.post("/employees/{employee_id}/approve", response_model=EmployeeOut)
async def approve_employee(
    employee_id: int,
    db: Annotated[asyncpg.Pool, Depends(get_db)],
    _: Annotated[dict, AdminOnly],
) -> dict:
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            """UPDATE users SET status = 'active'
               WHERE id = $1 AND status = 'pending'
               RETURNING id, phone, name, role, is_active, status,
                         hourly_rate, bonus_percent, created_at""",
            employee_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Сотрудник не найден или уже подтверждён")
    return dict(row)


@router.post("/employees/{employee_id}/reject")
async def reject_employee(
    employee_id: int,
    db: Annotated[asyncpg.Pool, Depends(get_db)],
    _: Annotated[dict, AdminOnly],
) -> dict:
    async with db.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM users WHERE id = $1 AND status = 'pending'", employee_id
        )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    return {"message": "Заявка отклонена"}


# ── Employees ─────────────────────────────────────────────────────────────────

@router.get("/employees", response_model=list[EmployeeOut])
async def list_employees(
    db: Annotated[asyncpg.Pool, Depends(get_db)],
    _: Annotated[dict, AdminOnly],
    is_active: bool | None = None,
) -> list[dict]:
    conditions = ["status = 'active'"]
    args: list = []
    if is_active is not None:
        conditions.append(f"is_active = ${len(args) + 1}")
        args.append(is_active)
    where = "WHERE " + " AND ".join(conditions)
    query = f"""SELECT id, phone, name, role, is_active, status,
                       hourly_rate, bonus_percent, created_at
                FROM users {where} ORDER BY name"""
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
            """INSERT INTO users (phone, name, password_hash, role, hourly_rate, bonus_percent, status)
               VALUES ($1, $2, $3, $4, $5, $6, 'active')
               RETURNING id, phone, name, role, is_active, status,
                         hourly_rate, bonus_percent, created_at""",
            body.phone, body.name, hash_password(body.password),
            body.role, body.hourly_rate, body.bonus_percent,
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

        updates, args = [], []
        idx = 1
        for field, value in {
            "name": body.name, "phone": body.phone, "role": body.role,
            "is_active": body.is_active, "hourly_rate": body.hourly_rate,
            "bonus_percent": body.bonus_percent,
        }.items():
            if value is not None:
                updates.append(f"{field} = ${idx}"); args.append(value); idx += 1
        if body.password is not None:
            updates.append(f"password_hash = ${idx}"); args.append(hash_password(body.password)); idx += 1

        if not updates:
            raise HTTPException(status_code=400, detail="Нет данных для обновления")

        args.append(employee_id)
        row = await conn.fetchrow(
            f"""UPDATE users SET {', '.join(updates)} WHERE id = ${idx}
                RETURNING id, phone, name, role, is_active, status,
                          hourly_rate, bonus_percent, created_at""",
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
    conditions, args = [], []
    idx = 1
    if user_id is not None:
        conditions.append(f"al.user_id = ${idx}"); args.append(user_id); idx += 1
    if suspicious_only:
        conditions.append("al.is_suspicious = TRUE")
    if date_from:
        conditions.append(f"al.timestamp >= ${idx}::timestamptz"); args.append(date_from); idx += 1
    if date_to:
        conditions.append(f"al.timestamp <= ${idx}::timestamptz"); args.append(date_to); idx += 1

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    args.extend([limit, offset])
    query = f"""
        SELECT al.id, al.user_id, u.name AS employee_name,
               al.action, al.timestamp, al.ip_address,
               al.device_id, al.user_agent, al.is_suspicious, al.suspicious_reason
        FROM attendance_logs al JOIN users u ON u.id = al.user_id
        {where} ORDER BY al.timestamp DESC LIMIT ${idx} OFFSET ${idx + 1}
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
            """SELECT al.id, al.user_id, u.name AS employee_name,
                      al.action, al.timestamp, al.ip_address,
                      al.device_id, al.user_agent, al.is_suspicious, al.suspicious_reason
               FROM attendance_logs al JOIN users u ON u.id = al.user_id
               WHERE al.is_suspicious = TRUE ORDER BY al.timestamp DESC LIMIT $1""",
            limit,
        )
    return [dict(r) for r in rows]


# ── Today stats ───────────────────────────────────────────────────────────────

@router.get("/stats/today", response_model=TodayStats)
async def stats_today(
    db: Annotated[asyncpg.Pool, Depends(get_db)],
    _: Annotated[dict, AdminOnly],
) -> dict:
    shift_total_minutes = settings.shift_start_hour * 60 + settings.late_threshold_minutes
    async with db.acquire() as conn:
        all_employees = await conn.fetch(
            """SELECT id, name FROM users
               WHERE is_active = TRUE AND role = 'employee' AND status = 'active'
               ORDER BY name"""
        )
        today_checkins = await conn.fetch(
            """SELECT DISTINCT ON (user_id) user_id, timestamp
               FROM attendance_logs
               WHERE action = 'check_in' AND timestamp >= NOW()::date
               ORDER BY user_id, timestamp ASC"""
        )

    checkin_map = {r["user_id"]: r["timestamp"] for r in today_checkins}
    present, absent, late = [], [], []
    for emp in all_employees:
        uid, name = emp["id"], emp["name"]
        if uid not in checkin_map:
            absent.append(TodayEntry(user_id=uid, name=name))
        else:
            ts: datetime = checkin_map[uid]
            checked_in_str = ts.strftime("%H:%M")
            entry_minutes = ts.hour * 60 + ts.minute
            if entry_minutes > shift_total_minutes:
                late.append(TodayEntry(user_id=uid, name=name,
                                       checked_in_at=checked_in_str,
                                       late_minutes=entry_minutes - shift_total_minutes))
            else:
                present.append(TodayEntry(user_id=uid, name=name, checked_in_at=checked_in_str))

    return {"present": present, "absent": absent, "late": late}


# ── Revenue ───────────────────────────────────────────────────────────────────

@router.post("/revenue", response_model=RevenueOut)
async def upsert_revenue(
    body: RevenueUpsert,
    db: Annotated[asyncpg.Pool, Depends(get_db)],
    current_user: Annotated[dict, AdminOnly],
) -> dict:
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO revenue_entries (date, amount, note, created_by)
               VALUES ($1, $2, $3, $4)
               ON CONFLICT (date) DO UPDATE
               SET amount = EXCLUDED.amount, note = EXCLUDED.note
               RETURNING id, date, amount, note, created_at""",
            body.date, body.amount, body.note, current_user["id"],
        )
    return dict(row)


@router.get("/revenue", response_model=list[RevenueOut])
async def list_revenue(
    db: Annotated[asyncpg.Pool, Depends(get_db)],
    _: Annotated[dict, AdminOnly],
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict]:
    conditions, args = [], []
    idx = 1
    if date_from:
        conditions.append(f"date >= ${idx}"); args.append(date_from); idx += 1
    if date_to:
        conditions.append(f"date <= ${idx}"); args.append(date_to); idx += 1
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    async with db.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT id, date, amount, note, created_at FROM revenue_entries {where} ORDER BY date DESC",
            *args,
        )
    return [dict(r) for r in rows]


# ── Salary calculation ────────────────────────────────────────────────────────

@router.get("/salary", response_model=SalaryReport)
async def calculate_salary(
    date_from: date,
    date_to: date,
    db: Annotated[asyncpg.Pool, Depends(get_db)],
    _: Annotated[dict, AdminOnly],
) -> dict:
    async with db.acquire() as conn:
        employees = await conn.fetch(
            """SELECT id, name, role, hourly_rate, bonus_percent
               FROM users
               WHERE is_active = TRUE AND status = 'active' AND role = 'employee'
               ORDER BY name"""
        )
        logs = await conn.fetch(
            """SELECT user_id, action, timestamp
               FROM attendance_logs
               WHERE timestamp >= $1::date
                 AND timestamp < ($2::date + INTERVAL '1 day')
                 AND action IN ('check_in', 'check_out')
               ORDER BY user_id, timestamp ASC""",
            date_from, date_to,
        )
        rev_row = await conn.fetchrow(
            """SELECT COALESCE(SUM(amount), 0) AS total
               FROM revenue_entries WHERE date >= $1 AND date <= $2""",
            date_from, date_to,
        )

    total_revenue = Decimal(str(rev_row["total"]))

    # Group logs by user
    user_logs: dict[int, list] = {}
    for log in logs:
        user_logs.setdefault(log["user_id"], []).append(log)

    def calc_hours(events: list) -> float:
        total_sec = 0.0
        last_in = None
        for ev in sorted(events, key=lambda e: e["timestamp"]):
            if ev["action"] == "check_in":
                last_in = ev["timestamp"]
            elif ev["action"] == "check_out" and last_in:
                total_sec += (ev["timestamp"] - last_in).total_seconds()
                last_in = None
        return round(total_sec / 3600, 2)

    result = []
    for emp in employees:
        hours = calc_hours(user_logs.get(emp["id"], []))
        rate = Decimal(str(emp["hourly_rate"]))
        pct = Decimal(str(emp["bonus_percent"]))
        base = (Decimal(str(hours)) * rate).quantize(Decimal("0.01"))
        bonus = (total_revenue * pct / Decimal("100")).quantize(Decimal("0.01"))
        result.append(SalaryEntry(
            user_id=emp["id"], name=emp["name"], role=emp["role"],
            hourly_rate=rate, bonus_percent=pct,
            hours_worked=hours, base_pay=base, bonus_pay=bonus,
            total_pay=(base + bonus),
        ))

    return SalaryReport(
        date_from=date_from, date_to=date_to,
        total_revenue=total_revenue, employees=result,
    )
