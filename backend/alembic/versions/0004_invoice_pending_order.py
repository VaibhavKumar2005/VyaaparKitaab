"""add pending_order_id and pending_order_amount to invoices

Revision ID: 0004_invoice_pending_order
Revises: 0003_encrypt_pii
Create Date: 2026-10-21 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = "0004_invoice_pending_order"
down_revision = "0003_encrypt_pii"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("invoices", sa.Column("pending_order_id", sa.String(length=64), nullable=True))
    op.add_column("invoices", sa.Column("pending_order_amount", sa.Numeric(12, 2), nullable=True))
    op.create_index("ix_invoices_pending_order_id", "invoices", ["pending_order_id"])


def downgrade() -> None:
    op.drop_index("ix_invoices_pending_order_id", table_name="invoices")
    op.drop_column("invoices", "pending_order_amount")
    op.drop_column("invoices", "pending_order_id")

