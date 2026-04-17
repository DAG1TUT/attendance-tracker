"""salary system: rates, revenue, pending status

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-17
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add salary fields + pending status to users
    op.add_column("users", sa.Column("hourly_rate", sa.Numeric(10, 2), nullable=False, server_default="150.00"))
    op.add_column("users", sa.Column("bonus_percent", sa.Numeric(5, 2), nullable=False, server_default="5.00"))
    op.add_column("users", sa.Column("status", sa.Text(), nullable=False, server_default="active"))
    op.execute("ALTER TABLE users ADD CONSTRAINT users_status_check CHECK (status IN ('active','pending'))")

    # Daily revenue entries
    op.execute("""
        CREATE TABLE revenue_entries (
            id          SERIAL PRIMARY KEY,
            date        DATE NOT NULL UNIQUE,
            amount      NUMERIC(12,2) NOT NULL,
            note        TEXT,
            created_by  INTEGER NOT NULL REFERENCES users(id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX idx_rev_date ON revenue_entries(date DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS revenue_entries")
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_status_check")
    op.drop_column("users", "status")
    op.drop_column("users", "bonus_percent")
    op.drop_column("users", "hourly_rate")
