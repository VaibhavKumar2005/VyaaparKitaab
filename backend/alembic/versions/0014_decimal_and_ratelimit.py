"""Phase 2 hardening: NUMERIC(12,2) money columns, shared rate_limit_hits, and SSE overflow table.

Revision ID: 0014_decimal_and_ratelimit
Revises: 0013_business_upi_vpa
Create Date: 2026-11-25
"""

import sqlalchemy as sa
from alembic import op

revision = "0014_decimal_and_ratelimit"
down_revision = "0013_business_upi_vpa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "payments" in tables:
        op.execute(
            "ALTER TABLE payments "
            "ALTER COLUMN amount TYPE NUMERIC(12, 2) "
            "USING ROUND(amount::numeric, 2)"
        )

    if "bank_transactions" in tables:
        op.execute(
            "ALTER TABLE bank_transactions "
            "ALTER COLUMN amount TYPE NUMERIC(12, 2) "
            "USING ROUND(amount::numeric, 2)"
        )

    if "rate_limit_hits" not in tables:
        op.create_table(
            "rate_limit_hits",
            sa.Column("key", sa.String(length=255), primary_key=True, nullable=False),
            sa.Column("window_start", sa.BigInteger(), primary_key=True, nullable=False),
            sa.Column("count", sa.Integer(), nullable=False, server_default="1"),
        )
        op.create_index(
            "ix_rate_limit_hits_window_start",
            "rate_limit_hits",
            ["window_start"],
        )

    if "sse_event_payloads" not in tables:
        op.create_table(
            "sse_event_payloads",
            sa.Column("event_id", sa.String(length=180), primary_key=True, nullable=False),
            sa.Column("event_type", sa.String(length=100), nullable=False),
            sa.Column("store_id", sa.String(length=64), nullable=True),
            sa.Column("customer_id", sa.String(length=64), nullable=True),
            sa.Column("payload_json", sa.Text(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
        op.create_index(
            "ix_sse_event_payloads_created_at",
            "sse_event_payloads",
            ["created_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "sse_event_payloads" in tables:
        op.drop_index("ix_sse_event_payloads_created_at", table_name="sse_event_payloads")
        op.drop_table("sse_event_payloads")

    if "rate_limit_hits" in tables:
        op.drop_index("ix_rate_limit_hits_window_start", table_name="rate_limit_hits")
        op.drop_table("rate_limit_hits")

    if "bank_transactions" in tables:
        op.execute(
            "ALTER TABLE bank_transactions "
            "ALTER COLUMN amount TYPE DOUBLE PRECISION "
            "USING amount::double precision"
        )

    if "payments" in tables:
        op.execute(
            "ALTER TABLE payments "
            "ALTER COLUMN amount TYPE DOUBLE PRECISION "
            "USING amount::double precision"
        )
