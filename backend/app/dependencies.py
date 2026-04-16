from __future__ import annotations

import ipaddress
from typing import Annotated

import asyncpg
from fastapi import Cookie, Depends, HTTPException, Request, status

from app.auth.service import decode_access_token
from app.config import settings
from app.database import get_pool


# ── Database ──────────────────────────────────────────────────────────────────

async def get_db() -> asyncpg.Pool:
    return get_pool()


# ── Auth ──────────────────────────────────────────────────────────────────────

async def get_current_user(
    db: Annotated[asyncpg.Pool, Depends(get_db)],
    access_token: str | None = Cookie(default=None),
) -> dict:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Не авторизован",
    )
    if not access_token:
        raise credentials_exc

    payload = decode_access_token(access_token)
    if payload is None:
        raise credentials_exc

    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exc

    async with db.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT id, phone, name, role, is_active FROM users WHERE id = $1",
            int(user_id),
        )

    if user is None or not user["is_active"]:
        raise credentials_exc

    return dict(user)


def require_role(*roles: str):
    async def checker(current_user: Annotated[dict, Depends(get_current_user)]) -> dict:
        if current_user["role"] not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недостаточно прав",
            )
        return current_user

    return checker


AdminOnly = Depends(require_role("admin"))
AnyRole = Depends(get_current_user)


# ── Network guard ─────────────────────────────────────────────────────────────

def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host


def check_local_network(request: Request) -> None:
    """Allow only requests from local network (cafe Wi-Fi). Disabled if ALLOWED_NETWORKS is empty."""
    if not settings.allowed_networks.strip():
        return

    client_ip = get_client_ip(request)
    try:
        addr = ipaddress.ip_address(client_ip)
        for cidr in settings.allowed_networks.split(","):
            if addr in ipaddress.ip_network(cidr.strip(), strict=False):
                return
    except ValueError:
        pass

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Доступ разрешён только из сети кафе",
    )


LocalNetworkGuard = Depends(check_local_network)
