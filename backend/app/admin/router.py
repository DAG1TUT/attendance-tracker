from __future__ import annotations

from datetime import date, datetime, time as dt_time, timedelta, timezone
from decimal import Decimal
from typing import Annotated
from zoneinfo import ZoneInfo

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status

from app.admin.schemas import (
    AdminLogOut,
    AttendanceDayEdit,
    DayCell,
    DaySchedule,
    EmployeeCreate,
    EmployeeOut,
    EmployeeUpdate,
    RevenueOut,
    RevenueUpsert,
    SalaryEntry,
    SalaryReport,
    ScheduleEntry,
    ScheduleSession,
    TodayEntry,
    TodayStats,
    WeekSchedule,
    WeekScheduleEntry,
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
    tz = ZoneInfo(settings.timezone)
    shift_total_minutes = settings.shift_start_hour * 60 + settings.late_threshold_minutes

    # Today's date in Moscow timezone
    today_moscow = datetime.now(tz).date()

    async with db.acquire() as conn:
        all_employees = await conn.fetch(
            """SELECT id, name FROM users
               WHERE is_active = TRUE AND role = 'employee' AND status = 'active'
               ORDER BY name"""
        )
        # Find first check-in today (in Moscow time)
        today_checkins = await conn.fetch(
            """SELECT DISTINCT ON (user_id) user_id, timestamp
               FROM attendance_logs
               WHERE action = 'check_in'
                 AND (timestamp AT TIME ZONE $1)::date = $2
               ORDER BY user_id, timestamp ASC""",
            settings.timezone, today_moscow,
        )

    checkin_map = {r["user_id"]: r["timestamp"] for r in today_checkins}
    present, absent, late = [], [], []
    for emp in all_employees:
        uid, name = emp["id"], emp["name"]
        if uid not in checkin_map:
            absent.append(TodayEntry(user_id=uid, name=name))
        else:
            ts: datetime = checkin_map[uid]
            # Convert UTC timestamp to Moscow time for display and late check
            ts_moscow = ts.astimezone(tz)
            checked_in_str = ts_moscow.strftime("%H:%M")
            entry_minutes = ts_moscow.hour * 60 + ts_moscow.minute
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


# ── Daily schedule / Timeline ─────────────────────────────────────────────────

@router.get("/stats/schedule", response_model=DaySchedule)
async def stats_schedule(
    db: Annotated[asyncpg.Pool, Depends(get_db)],
    _: Annotated[dict, AdminOnly],
    target_date: date | None = None,
) -> dict:
    tz = ZoneInfo(settings.timezone)
    day = target_date or datetime.now(tz).date()

    async with db.acquire() as conn:
        employees = await conn.fetch(
            """SELECT id, name, hourly_rate, bonus_percent
               FROM users
               WHERE is_active = TRUE AND status = 'active' AND role = 'employee'
               ORDER BY name"""
        )
        logs = await conn.fetch(
            """SELECT user_id, action, timestamp
               FROM attendance_logs
               WHERE (timestamp AT TIME ZONE $1)::date = $2
                 AND action IN ('check_in', 'check_out')
               ORDER BY user_id, timestamp ASC""",
            settings.timezone, day,
        )
        rev_row = await conn.fetchrow(
            "SELECT COALESCE(amount, 0) AS total FROM revenue_entries WHERE date = $1",
            day,
        )

    revenue = Decimal(str(rev_row["total"])) if rev_row else Decimal("0")

    user_logs: dict[int, list] = {}
    for log in logs:
        user_logs.setdefault(log["user_id"], []).append(log)

    result = []
    now_utc = datetime.now(timezone.utc)

    for emp in employees:
        events = user_logs.get(emp["id"], [])
        sessions: list[ScheduleSession] = []
        last_in: datetime | None = None
        total_seconds = 0.0
        is_active = False

        for ev in events:
            ts: datetime = ev["timestamp"]
            if ev["action"] == "check_in":
                last_in = ts
            elif ev["action"] == "check_out" and last_in:
                minutes = int((ts - last_in).total_seconds() / 60)
                total_seconds += minutes * 60
                sessions.append(ScheduleSession(check_in=last_in, check_out=ts, minutes=minutes))
                last_in = None

        if last_in:
            minutes = int((now_utc - last_in).total_seconds() / 60)
            total_seconds += minutes * 60
            sessions.append(ScheduleSession(check_in=last_in, check_out=None, minutes=minutes))
            is_active = True

        total_hours = round(total_seconds / 3600, 2)
        rate = Decimal(str(emp["hourly_rate"]))
        pct = Decimal(str(emp["bonus_percent"]))
        base = (Decimal(str(total_hours)) * rate).quantize(Decimal("0.01"))
        bonus = (revenue * pct / Decimal("100")).quantize(Decimal("0.01"))

        result.append(ScheduleEntry(
            user_id=emp["id"], name=emp["name"],
            hourly_rate=rate, bonus_percent=pct,
            sessions=sessions, total_hours=total_hours,
            base_pay=base, bonus_pay=bonus, total_pay=(base + bonus),
            is_active=is_active,
        ))

    return DaySchedule(date=day, revenue=revenue, employees=result)


# ── Weekly schedule table ─────────────────────────────────────────────────────

@router.get("/stats/week", response_model=WeekSchedule)
async def stats_week(
    date_from: date,
    date_to: date,
    db: Annotated[asyncpg.Pool, Depends(get_db)],
    _: Annotated[dict, AdminOnly],
) -> dict:
    tz = ZoneInfo(settings.timezone)
    dates = [date_from + timedelta(days=i) for i in range((date_to - date_from).days + 1)]

    async with db.acquire() as conn:
        employees = await conn.fetch(
            """SELECT id, name FROM users
               WHERE is_active = TRUE AND status = 'active' AND role = 'employee'
               ORDER BY name"""
        )
        logs = await conn.fetch(
            """SELECT user_id, action, timestamp
               FROM attendance_logs
               WHERE (timestamp AT TIME ZONE $1)::date >= $2
                 AND (timestamp AT TIME ZONE $1)::date <= $3
                 AND action IN ('check_in', 'check_out')
               ORDER BY user_id, timestamp ASC""",
            settings.timezone, date_from, date_to,
        )

    # Group logs by user_id → date (Moscow) → list
    from collections import defaultdict
    user_day: dict[int, dict[date, list]] = defaultdict(lambda: defaultdict(list))
    for log in logs:
        ts_moscow = log["timestamp"].astimezone(tz)
        user_day[log["user_id"]][ts_moscow.date()].append(
            {"action": log["action"], "timestamp": log["timestamp"]}
        )

    result = []
    for emp in employees:
        days = []
        for d in dates:
            day_logs = sorted(user_day[emp["id"]].get(d, []), key=lambda x: x["timestamp"])
            check_in_ts = None
            check_out_ts = None
            total_sec = 0.0
            last_in = None
            for ev in day_logs:
                if ev["action"] == "check_in":
                    if check_in_ts is None:
                        check_in_ts = ev["timestamp"]
                    last_in = ev["timestamp"]
                elif ev["action"] == "check_out" and last_in:
                    check_out_ts = ev["timestamp"]
                    total_sec += (ev["timestamp"] - last_in).total_seconds()
                    last_in = None
            days.append(DayCell(
                date=d,
                check_in=check_in_ts,
                check_out=check_out_ts,
                hours=round(total_sec / 3600, 1),
            ))
        result.append(WeekScheduleEntry(user_id=emp["id"], name=emp["name"], days=days))

    return WeekSchedule(date_from=date_from, date_to=date_to, dates=dates, employees=result)


# ── Edit attendance day (admin manual edit) ───────────────────────────────────

@router.put("/attendance/day")
async def edit_attendance_day(
    body: AttendanceDayEdit,
    db: Annotated[asyncpg.Pool, Depends(get_db)],
    _: Annotated[dict, AdminOnly],
) -> dict:
    tz = ZoneInfo(settings.timezone)

    async with db.acquire() as conn:
        # Verify employee exists
        emp = await conn.fetchrow("SELECT id FROM users WHERE id = $1", body.user_id)
        if not emp:
            raise HTTPException(status_code=404, detail="Сотрудник не найден")

        # Delete existing logs for this user on this date (Moscow)
        await conn.execute(
            """DELETE FROM attendance_logs
               WHERE user_id = $1
                 AND (timestamp AT TIME ZONE $2)::date = $3""",
            body.user_id, settings.timezone, body.date,
        )

        if body.check_in:
            naive = datetime.combine(body.date, dt_time.fromisoformat(body.check_in))
            ts = naive.replace(tzinfo=tz)
            await conn.execute(
                """INSERT INTO attendance_logs
                   (user_id, action, timestamp, ip_address, device_id, user_agent)
                   VALUES ($1, 'check_in', $2, 'manual', 'admin-edit', 'admin-edit')""",
                body.user_id, ts,
            )

        if body.check_out:
            naive = datetime.combine(body.date, dt_time.fromisoformat(body.check_out))
            ts = naive.replace(tzinfo=tz)
            await conn.execute(
                """INSERT INTO attendance_logs
                   (user_id, action, timestamp, ip_address, device_id, user_agent)
                   VALUES ($1, 'check_out', $2, 'manual', 'admin-edit', 'admin-edit')""",
                body.user_id, ts,
            )

    return {"message": "Обновлено"}
