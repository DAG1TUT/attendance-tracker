from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class CheckRequest(BaseModel):
    device_id: str
    user_agent: str


class AttendanceLogOut(BaseModel):
    id: int
    action: str
    timestamp: datetime
    ip_address: str
    device_id: str
    is_suspicious: bool
    suspicious_reason: str | None


class StatusOut(BaseModel):
    action: str | None  # "check_in" | "check_out" | None
    since: datetime | None
