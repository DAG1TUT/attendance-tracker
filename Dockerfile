# ── Build stage: install deps ──────────────────────────────────────────────────
FROM python:3.12-slim AS base
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Final image ────────────────────────────────────────────────────────────────
FROM base
WORKDIR /app

COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini .
COPY frontend/ ./static/

EXPOSE 8000

CMD ["sh", "-c", \
  "python -m alembic upgrade head && \
   uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
