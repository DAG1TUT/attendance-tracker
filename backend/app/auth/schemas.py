from __future__ import annotations

import re

from pydantic import BaseModel, field_validator


def normalize_phone(v: str) -> str:
    """Strip formatting, validate and normalise to +7XXXXXXXXXX."""
    # Remove spaces, dashes, parentheses
    cleaned = re.sub(r"[\s\-\(\)]", "", v.strip())

    if cleaned.startswith("8") and len(cleaned) == 11:
        cleaned = "+7" + cleaned[1:]
    elif cleaned.startswith("+7") and len(cleaned) == 12:
        pass  # already canonical
    elif cleaned.startswith("7") and len(cleaned) == 11:
        cleaned = "+7" + cleaned[1:]
    else:
        raise ValueError(
            "Номер должен начинаться с +7 или 8 и содержать 11 цифр"
        )

    if not re.fullmatch(r"\+7\d{10}", cleaned):
        raise ValueError("Неверный формат номера телефона")

    return cleaned


class LoginRequest(BaseModel):
    phone: str
    password: str
    device_id: str
    user_agent: str

    @field_validator("phone", mode="before")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return normalize_phone(v)


class RegisterRequest(BaseModel):
    name: str
    phone: str
    password: str

    @field_validator("phone", mode="before")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return normalize_phone(v)


class BootstrapRequest(BaseModel):
    name: str
    phone: str
    password: str
    bootstrap_secret: str

    @field_validator("phone", mode="before")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return normalize_phone(v)


class UserOut(BaseModel):
    id: int
    phone: str
    name: str
    role: str
    status: str = "active"
