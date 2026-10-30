"""add bank_transactions table for real outside statement and UPI imports

Revision ID: 0008_bank_transactions
Revises: 0007_payments
Create Date: 2026-10-30 19:50:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_bank_transactions"
down_revision: str | None = "0007_payments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bank_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("txn_id", sa.String(length=120), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("date", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False, server_default="DEBIT"),
        sa.Column("mode", sa.String(length=30), nullable=False, server_default="UPI"),
        sa.Column("app", sa.String(length=50), nullable=False, server_default="UPI"),
        sa.Column("vpa", sa.String(length=150), nullable=True),
        sa.Column("narration", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False, server_default="General"),
        sa.Column("counterparty", sa.String(length=150), nullable=False, server_default="Merchant / Peer"),
        sa.Column("masked_acc", sa.String(length=50), nullable=False, server_default="XXXX-XXXX-4821"),
        sa.Column("source", sa.String(length=50), nullable=False, server_default="statement_import"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "txn_id", name="uq_bank_transactions_user_txn"),
    )
    op.create_index("ix_bank_transactions_user_id", "bank_transactions", ["user_id"])
    op.create_index("ix_bank_transactions_txn_id", "bank_transactions", ["txn_id"])


def downgrade() -> None:
    op.drop_index("ix_bank_transactions_txn_id", table_name="bank_transactions")
    op.drop_index("ix_bank_transactions_user_id", table_name="bank_transactions")
    op.drop_table("bank_transactions")

