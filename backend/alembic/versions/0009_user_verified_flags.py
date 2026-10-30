"""add phone_verified and email_verified columns to users

Revision ID: 0009_user_verified_flags
Revises: 0008_bank_transactions
Create Date: 2026-10-30 21:12:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_user_verified_flags"
down_revision: str | None = "0008_bank_transactions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("phone_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "users",
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("users", "email_verified")
    op.drop_column("users", "phone_verified")

