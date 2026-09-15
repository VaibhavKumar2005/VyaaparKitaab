"""add refresh_tokens table

Revision ID: 0002_add_refresh_tokens
Revises: 0001_initial
Create Date: 2026-09-15 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0002_add_refresh_tokens"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ensure uuid generator is available
    try:
        op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto";')
    except Exception:
        # extension creation may require superuser privileges; ignore if not available
        pass

    op.create_table(
        "refresh_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_refresh_tokens_user", "refresh_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_refresh_tokens_user", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
