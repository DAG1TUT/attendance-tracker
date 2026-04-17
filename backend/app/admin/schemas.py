from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class EmployeeCreate(BaseModel):
    name: str
    phone: str
    password: str
    role: str = "employee"
    hourly_rate: Decimal = Decimal("150.00")
    bonus_percent: Decimal = Decimal("5.00")


class EmployeeUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    password: str | None = None
    role: str | None = None
    is_active: bool | None = None
    hourly_rate: Decimal | None = None
    bonus_percent: Decimal | None = None


class EmployeeOut(BaseModel):
    id: int
    phone: str
    name: str
    role: str
    is_active: bool
    status: str
    hourly_rate: Decimal
    bonus_percent: Decimal
    created_at: datetime


class AdminLogOut(BaseModel):
    id: int
    user_id: int
    employee_name: str
    action: str
    timestamp: datetime
    ip_address: str
    device_id: str
    user_agent: str
    is_suspicious: bool
    suspicious_reason: str | None


class TodayEntry(BaseModel):
    user_id: int
    name: str
    checked_in_at: str | None = None
    late_minutes: int | None = None


class TodayStats(BaseModel):
    present: list[TodayEntry]
    absent: list[TodayEntry]
    late: list[TodayEntry]


# ── Revenue ───────────────────────────────────────────────────────────────────

class RevenueUpsert(BaseModel):
    date: date
    amount: Decimal
    note: str | None = None


class RevenueOut(BaseModel):
    id: int
    date: date
    amount: Decimal
    note: str | None
    created_at: datetime


# ── Salary ────────────────────────────────────────────────────────────────────

class SalaryEntry(BaseModel):
    user_id: int
    name: str
    role: str
    hourly_rate: Decimal
    bonus_percent: Decimal
    hours_worked: float
    base_pay: Decimal
    bonus_pay: Decimal
    total_pay: Decimal


class SalaryReport(BaseModel):
    date_from: date
    date_to: date
    total_revenue: Decimal
    employees: list[SalaryEntry]
