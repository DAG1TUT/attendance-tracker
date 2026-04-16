from __future__ import annotations

from typing import Annotated

import asyncpg
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status

from app.auth.schemas import BootstrapRequest, LoginRequest, UserOut
from app.auth.service import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from app.config import settings
from app.dependencies import AnyRole, get_db

router = APIRouter(prefix="/auth", tags=["auth"])

COOKIE_OPTS = {
    "httponly": True,
    "samesite": "lax",
    "secure": False,  # set True in production with HTTPS
}


@router.post("/bootstrap", status_code=status.HTTP_201_CREATED)
async def bootstrap(
    body: BootstrapRequest,
    db: Annotated[asyncpg.Pool, Depends(get_db)],
) -> dict:
    """Create the first admin account. Works only if no admin exists yet."""
    if body.bootstrap_secret != settings.admin_bootstrap_secret:
        raise HTTPException(status_code=403, detail="Неверный bootstrap-секрет")

    async with db.acquire() as conn:
        existing_admin = await conn.fetchval(
            "SELECT id FROM users WHERE role = 'admin' LIMIT 1"
        )
        if existing_admin:
            raise HTTPException(status_code=409, detail="Администратор уже существует")

        existing_phone = await conn.fetchval(
            "SELECT id FROM users WHERE phone = $1", body.phone
        )
        if existing_phone:
            raise HTTPException(status_code=409, detail="Телефон уже занят")

        await conn.execute(
            """
            INSERT INTO users (phone, name, password_hash, role)
            VALUES ($1, $2, $3, 'admin')
            """,
            body.phone,
            body.name,
            hash_password(body.password),
        )

    return {"message": "Аккаунт администратора создан"}


@router.post("/login")
async def login(
    body: LoginRequest,
    response: Response,
    db: Annotated[asyncpg.Pool, Depends(get_db)],
) -> dict:
    async with db.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT id, name, password_hash, role, is_active FROM users WHERE phone = $1",
            body.phone.strip(),
        )

    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Неверный телефон или пароль")

    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="Аккаунт деактивирован")

    access_token = create_access_token(user["id"])
    refresh_token = create_refresh_token(user["id"])

    response.set_cookie(
        "access_token", access_token,
        max_age=settings.access_token_expire_minutes * 60,
        **COOKIE_OPTS,
    )
    response.set_cookie(
        "refresh_token", refresh_token,
        max_age=settings.refresh_token_expire_days * 86400,
        **COOKIE_OPTS,
    )

    return {
        "message": "Вход выполнен",
        "role": user["role"],
        "name": user["name"],
        "user_id": user["id"],
    }


@router.post("/refresh")
async def refresh(
    response: Response,
    db: Annotated[asyncpg.Pool, Depends(get_db)],
    refresh_token: str | None = Cookie(default=None),
) -> dict:
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Нет токена обновления")

    payload = decode_refresh_token(refresh_token)
    if not payload:
        raise HTTPException(status_code=401, detail="Недействительный токен обновления")

    user_id = int(payload["sub"])
    async with db.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT id, is_active FROM users WHERE id = $1", user_id
        )

    if not user or not user["is_active"]:
        raise HTTPException(status_code=401, detail="Пользователь не найден или деактивирован")

    new_access = create_access_token(user_id)
    new_refresh = create_refresh_token(user_id)

    response.set_cookie(
        "access_token", new_access,
        max_age=settings.access_token_expire_minutes * 60,
        **COOKIE_OPTS,
    )
    response.set_cookie(
        "refresh_token", new_refresh,
        max_age=settings.refresh_token_expire_days * 86400,
        **COOKIE_OPTS,
    )

    return {"message": "Токены обновлены"}


@router.post("/logout")
async def logout(response: Response) -> dict:
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return {"message": "Выход выполнен"}


@router.get("/me", response_model=UserOut)
async def me(current_user: Annotated[dict, AnyRole]) -> dict:
    return current_user
