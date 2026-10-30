"""add payments table for recording transactions and preventing double-counts

Revision ID: 0007_payments
Revises: 0006_banking_consents
Create Date: 2026-10-30 14:45:00.000000
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007_payments"
down_revision = "0006_banking_consents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("payment_id", sa.String(length=100), nullable=False),
        sa.Column("order_id", sa.String(length=100), nullable=True),
        sa.Column(
            "business_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("invoices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(length=10), server_default="INR", nullable=False),
        sa.Column("method", sa.String(length=50), server_default="UPI", nullable=False),
        sa.Column("vpa", sa.String(length=150), nullable=True),
        sa.Column("app", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=50), server_default="captured", nullable=False),
        sa.Column("raw_response", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_payments_payment_id", "payments", ["payment_id"], unique=True)
    op.create_index("ix_payments_order_id", "payments", ["order_id"])
    op.create_index("ix_payments_business_id", "payments", ["business_id"])
    op.create_index("ix_payments_invoice_id", "payments", ["invoice_id"])
    op.create_index("ix_payments_customer_id", "payments", ["customer_id"])
    op.create_index("ix_payments_business_created", "payments", ["business_id", "created_at"])
    op.create_index("ix_payments_invoice_created", "payments", ["invoice_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_payments_invoice_created", table_name="payments")
    op.drop_index("ix_payments_business_created", table_name="payments")
    op.drop_index("ix_payments_customer_id", table_name="payments")
    op.drop_index("ix_payments_invoice_id", table_name="payments")
    op.drop_index("ix_payments_business_id", table_name="payments")
    op.drop_index("ix_payments_order_id", table_name="payments")
    op.drop_index("ix_payments_payment_id", table_name="payments")
    op.drop_table("payments")

