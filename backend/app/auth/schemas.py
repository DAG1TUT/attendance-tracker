from __future__ import annotations

from pydantic import BaseModel


class LoginRequest(BaseModel):
    phone: str
    password: str
    device_id: str
    user_agent: str


class RegisterRequest(BaseModel):
    name: str
    phone: str
    password: str


class BootstrapRequest(BaseModel):
    name: str
    phone: str
    password: str
    bootstrap_secret: str


class UserOut(BaseModel):
    id: int
    phone: str
    name: str
    role: str
    status: str = "active"
