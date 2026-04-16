from __future__ import annotations

import ipaddress
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import close_pool, create_pool
from app.auth.router import router as auth_router
from app.attendance.router import router as attendance_router
from app.admin.router import router as admin_router


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
    if request.url.path == "/api/v1/health":
        return await call_next(request)
    ip_str = (request.headers.get("X-Forwarded-For") or request.client.host).split(",")[0].strip()
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
