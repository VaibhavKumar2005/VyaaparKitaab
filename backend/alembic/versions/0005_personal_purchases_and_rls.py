"""add personal_purchases table and postgresql row-level security policies

Revision ID: 0005_personal_purchases_and_rls
Revises: 0004_invoice_pending_order
Create Date: 2026-10-28 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_personal_purchases_and_rls"
down_revision = "0004_invoice_pending_order"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "personal_purchases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("marketplace", sa.String(length=60), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="INR"),
        sa.Column("order_id", sa.String(length=1024), nullable=True),
        sa.Column("items_note", sa.String(length=1024), nullable=True),
        sa.Column("order_id_bidx", sa.String(length=64), nullable=True),
        sa.Column("payment_method", sa.String(length=40), nullable=False, server_default="UPI"),
        sa.Column("purchased_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("user_id", "marketplace", "order_id_bidx", name="uq_user_mkt_order_bidx"),
    )
    op.create_index("ix_personal_purchases_user_id", "personal_purchases", ["user_id"])
    op.create_index("ix_personal_purchases_marketplace", "personal_purchases", ["marketplace"])
    op.create_index("ix_personal_purchases_order_id_bidx", "personal_purchases", ["order_id_bidx"])
    op.create_index("ix_personal_purchases_purchased_at", "personal_purchases", ["purchased_at"])

    # Enable Row-Level Security (RLS) policies that allow either unset session context
    # (application-enforced tenant filter) or matching app.current_user_id / app.current_business_id
    for table in ("businesses", "personal_purchases"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY businesses_tenant_isolation ON businesses
        USING (
            current_setting('app.current_user_id', true) IS NULL
            OR current_setting('app.current_user_id', true) = ''
            OR owner_id::text = current_setting('app.current_user_id', true)
        );
        """
    )
    op.execute(
        """
        CREATE POLICY personal_purchases_user_isolation ON personal_purchases
        USING (
            current_setting('app.current_user_id', true) IS NULL
            OR current_setting('app.current_user_id', true) = ''
            OR user_id::text = current_setting('app.current_user_id', true)
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS personal_purchases_user_isolation ON personal_purchases;")
    op.execute("DROP POLICY IF EXISTS businesses_tenant_isolation ON businesses;")
    op.execute("ALTER TABLE personal_purchases DISABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE businesses DISABLE ROW LEVEL SECURITY;")

    op.drop_index("ix_personal_purchases_purchased_at", table_name="personal_purchases")
    op.drop_index("ix_personal_purchases_order_id_bidx", table_name="personal_purchases")
    op.drop_index("ix_personal_purchases_marketplace", table_name="personal_purchases")
    op.drop_index("ix_personal_purchases_user_id", table_name="personal_purchases")
    op.drop_table("personal_purchases")

