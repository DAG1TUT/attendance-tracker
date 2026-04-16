from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class EmployeeCreate(BaseModel):
    name: str
    phone: str
    password: str
    role: str = "employee"


class EmployeeUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    password: str | None = None
    role: str | None = None
    is_active: bool | None = None


class EmployeeOut(BaseModel):
    id: int
    phone: str
    name: str
    role: str
    is_active: bool
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
