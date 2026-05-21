"""Add is_owner and permissions to users

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-21
"""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_owner BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS permissions JSONB")
    # Make the first admin (lowest id) the owner
    op.execute("UPDATE users SET is_owner = TRUE WHERE id = (SELECT MIN(id) FROM users WHERE role = 'admin')")


def downgrade():
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS is_owner")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS permissions")
