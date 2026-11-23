"""create unified_transactions and customer_notifications tables

Revision ID: 0012_unified_transactions
Revises: 0011_link_purchases_to_business_customers
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_unified_transactions"
down_revision: str | None = "0011_link_purchases_to_business_customers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "unified_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "business_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("businesses.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("invoices.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("source_ref_id", sa.String(length=180), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False, server_default="DEBIT"),
        sa.Column("side", sa.String(length=16), nullable=False, server_default="CUSTOMER"),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("paid_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("discount_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("tax_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="INR"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="RECORDED"),
        sa.Column("channel", sa.String(length=40), nullable=False, server_default="UPI"),
        sa.Column("app", sa.String(length=50), nullable=True),
        sa.Column("counterparty", sa.String(length=180), nullable=False, server_default="Merchant"),
        sa.Column("narration", sa.Text(), nullable=False, server_default=""),
        sa.Column("category", sa.String(length=80), nullable=False, server_default="Other"),
        sa.Column("subcategory", sa.String(length=80), nullable=False, server_default="General"),
        sa.Column("classification_source", sa.String(length=32), nullable=False, server_default="rule"),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("source_type", "source_ref_id", name="uq_unified_txn_source_ref"),
    )
    op.create_index("ix_unified_transactions_user_id", "unified_transactions", ["user_id"])
    op.create_index("ix_unified_transactions_business_id", "unified_transactions", ["business_id"])
    op.create_index("ix_unified_transactions_customer_id", "unified_transactions", ["customer_id"])
    op.create_index("ix_unified_transactions_invoice_id", "unified_transactions", ["invoice_id"])
    op.create_index("ix_unified_transactions_source_type", "unified_transactions", ["source_type"])
    op.create_index("ix_unified_transactions_source_ref_id", "unified_transactions", ["source_ref_id"])
    op.create_index("ix_unified_transactions_category", "unified_transactions", ["category"])
    op.create_index("ix_unified_transactions_subcategory", "unified_transactions", ["subcategory"])
    op.create_index("ix_unified_transactions_occurred_at", "unified_transactions", ["occurred_at"])
    op.create_index("ix_unified_txn_user_occurred", "unified_transactions", ["user_id", "occurred_at"])
    op.create_index("ix_unified_txn_biz_occurred", "unified_transactions", ["business_id", "occurred_at"])
    op.create_index("ix_unified_txn_cust_occurred", "unified_transactions", ["customer_id", "occurred_at"])

    op.create_table(
        "customer_notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "business_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("businesses.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("invoices.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event_key", sa.String(length=180), nullable=False, unique=True),
        sa.Column("event_type", sa.String(length=50), nullable=False, server_default="purchase.recorded"),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("discount_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("category", sa.String(length=80), nullable=False, server_default="Other"),
        sa.Column("subcategory", sa.String(length=80), nullable=False, server_default="General"),
        sa.Column("payment_channel", sa.String(length=50), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_customer_notifications_user_id", "customer_notifications", ["user_id"])
    op.create_index("ix_customer_notifications_customer_id", "customer_notifications", ["customer_id"])
    op.create_index("ix_customer_notifications_business_id", "customer_notifications", ["business_id"])
    op.create_index("ix_customer_notifications_invoice_id", "customer_notifications", ["invoice_id"])
    op.create_index("ix_customer_notifications_created_at", "customer_notifications", ["created_at"])


def downgrade() -> None:
    op.drop_table("customer_notifications")
    op.drop_table("unified_transactions")
