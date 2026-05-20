"""Add position column to users

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-20
"""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None

def upgrade():
    op.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS position TEXT NOT NULL DEFAULT 'employee'
    """)

def downgrade():
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS position")
