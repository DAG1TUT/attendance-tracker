"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-16
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE users (
            id            SERIAL PRIMARY KEY,
            phone         TEXT UNIQUE NOT NULL,
            name          TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role          TEXT NOT NULL DEFAULT 'employee'
                          CHECK (role IN ('employee', 'admin')),
            is_active     BOOLEAN NOT NULL DEFAULT TRUE,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE attendance_logs (
            id                SERIAL PRIMARY KEY,
            user_id           INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            action            TEXT NOT NULL CHECK (action IN ('check_in', 'check_out')),
            timestamp         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            ip_address        TEXT NOT NULL,
            device_id         TEXT NOT NULL,
            user_agent        TEXT NOT NULL,
            is_suspicious     BOOLEAN NOT NULL DEFAULT FALSE,
            suspicious_reason TEXT
        )
    """)

    op.execute("CREATE INDEX idx_al_user ON attendance_logs(user_id, timestamp DESC)")
    op.execute("CREATE INDEX idx_al_ts   ON attendance_logs(timestamp DESC)")
    op.execute("CREATE INDEX idx_al_susp ON attendance_logs(is_suspicious, timestamp DESC)")

    op.execute("""
        CREATE TABLE known_devices (
            id         SERIAL PRIMARY KEY,
            user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            device_id  TEXT NOT NULL,
            first_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_seen  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(user_id, device_id)
        )
    """)

    op.execute("CREATE INDEX idx_kd_user ON known_devices(user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS known_devices CASCADE")
    op.execute("DROP TABLE IF EXISTS attendance_logs CASCADE")
    op.execute("DROP TABLE IF EXISTS users CASCADE")
