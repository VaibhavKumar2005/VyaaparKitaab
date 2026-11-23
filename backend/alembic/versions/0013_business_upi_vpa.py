"""add optional upi_vpa to businesses

Revision ID: 0013_business_upi_vpa
Revises: 0012_unified_transactions
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_business_upi_vpa"
down_revision: str | None = "0012_unified_transactions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("businesses", sa.Column("upi_vpa", sa.String(length=150), nullable=True))


def downgrade() -> None:
    op.drop_column("businesses", "upi_vpa")
