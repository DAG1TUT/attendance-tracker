from __future__ import annotations

import ipaddress
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import close_pool, create_pool, get_pool
from app.auth.router import router as auth_router
from app.attendance.router import router as attendance_router
from app.admin.router import router as admin_router
from app.bot.handler import BotHandler
from app.bot.sender import send_message

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_pool(settings.database_url)
    yield
    await close_pool()


app = FastAPI(
    title="Attendance Tracker API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def ip_guard(request: Request, call_next):
    if not settings.allowed_networks.strip():
        return await call_next(request)
    # Railway healthcheck comes from internal IP — exempt it
    if request.url.path == "/api/v1/health":
        return await call_next(request)
    # Only check-in and check-out require cafe WiFi.
    # Viewing (status, history, week, my-salary) works from any network.
    WRITE_PATHS = ("/api/v1/attendance/check-in", "/api/v1/attendance/check-out")
    if not any(request.url.path.startswith(p) for p in WRITE_PATHS):
        return await call_next(request)
    # Fastly CDN always sets X-Forwarded-For to the real client IP
    # request.client.host is Railway's internal proxy — not useful
    xff = request.headers.get("X-Forwarded-For") or request.headers.get("X-Real-IP")
    if not xff:
        return JSONResponse({"detail": "Доступ разрешён только из сети кафе"}, status_code=403)
    ip_str = xff.split(",")[0].strip()
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return JSONResponse({"detail": "Доступ запрещён"}, status_code=403)
    for cidr in settings.allowed_networks.split(","):
        if addr in ipaddress.ip_network(cidr.strip(), strict=False):
            return await call_next(request)
    return JSONResponse({"detail": "Доступ разрешён только из сети кафе"}, status_code=403)

API_PREFIX = "/api/v1"

app.include_router(auth_router, prefix=API_PREFIX)
app.include_router(attendance_router, prefix=API_PREFIX)
app.include_router(admin_router, prefix=API_PREFIX)


@app.get("/api/v1/health")
async def health() -> dict:
    return {"status": "ok", "service": "Attendance Tracker"}


@app.get("/api/v1/debug-ip")
async def debug_ip(request: Request) -> dict:
    return {
        "x_forwarded_for": request.headers.get("X-Forwarded-For"),
        "x_real_ip": request.headers.get("X-Real-IP"),
        "client_host": request.client.host,
        "allowed_networks": settings.allowed_networks,
    }


@app.post("/api/v1/telegram/webhook")
async def telegram_webhook(request: Request) -> dict:
    """Receive updates from Telegram."""
    if not settings.telegram_bot_token:
        return {"ok": False}

    # Verify secret token
    if settings.telegram_webhook_secret:
        token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if token != settings.telegram_webhook_secret:
            return JSONResponse({"ok": False}, status_code=403)

    body = await request.json()

    message = body.get("message") or body.get("edited_message")
    if not message:
        return {"ok": True}

    chat_id = message.get("chat", {}).get("id")
    user_id = message.get("from", {}).get("id")
    text = message.get("text", "").strip()

    if not chat_id or not text:
        return {"ok": True}

    # Check allowed users
    allowed = settings.telegram_allowed_users.strip()
    if allowed:
        allowed_ids = {u.strip() for u in allowed.split(",")}
        if str(user_id) not in allowed_ids and str(chat_id) not in allowed_ids:
            return {"ok": True}  # Silently ignore unauthorized users
    elif settings.telegram_chat_id:
        # Fall back to the existing chat_id setting
        if str(chat_id) != str(settings.telegram_chat_id) and str(user_id) != str(settings.telegram_chat_id):
            return {"ok": True}

    # Process message
    try:
        pool = get_pool()
        handler = BotHandler(pool)
        response = await handler.handle(text)
    except Exception as e:
        logger.error("Bot handler error: %s", e, exc_info=True)
        response = "❌ Произошла ошибка при обработке запроса."

    await send_message(chat_id, response)
    return {"ok": True}


@app.post("/api/v1/admin/setup-webhook")
async def setup_webhook(request: Request) -> dict:
    """Register Telegram webhook. Call once after deploy. No auth required (token-protected)."""
    from app.bot.setup import register_webhook
    base_url = str(request.base_url)
    result = await register_webhook(base_url)
    return result


# ── Serve frontend static files ───────────────────────────────────────────────
# When running from project root with PYTHONPATH=backend, frontend/ is at CWD/frontend
# When running from Docker (CMD copies frontend/ to static/), check both locations
_cwd_frontend = os.path.join(os.getcwd(), "frontend")
_docker_static = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
STATIC_DIR = _cwd_frontend if os.path.isdir(_cwd_frontend) else _docker_static

if os.path.isdir(STATIC_DIR):
    static_subdir = os.path.join(STATIC_DIR, "static")
    if os.path.isdir(static_subdir):
        app.mount("/static", StaticFiles(directory=static_subdir), name="static-assets")

    @app.get("/{path:path}")
    async def spa_catch_all(request: Request, path: str):
        file_path = os.path.join(STATIC_DIR, path)
        if path and os.path.isfile(file_path):
            return FileResponse(file_path)
        # Serve index.html as default
        index = os.path.join(STATIC_DIR, "index.html")
        if os.path.isfile(index):
            return FileResponse(index)
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "Not found"}, status_code=404)
