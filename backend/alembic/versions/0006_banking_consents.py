"""add banking_consents and payment_webhook_events tables

Revision ID: 0006_banking_consents
Revises: 0005_personal_purchases_and_rls
Create Date: 2026-10-30 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_banking_consents"
down_revision = "0005_personal_purchases_and_rls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "banking_consents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("consent_id", sa.String(length=100), nullable=False),
        sa.Column("fip_id", sa.String(length=50), nullable=False),
        sa.Column("fip_name", sa.String(length=150), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="APPROVED"),
        sa.Column("redirect_url", sa.Text(), nullable=False),
        sa.Column("purpose_text", sa.Text(), nullable=False),
        sa.Column("masked_acc", sa.String(length=50), nullable=False),
        sa.Column("fi_types", sa.String(length=100), nullable=False, server_default='["DEPOSIT"]'),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_banking_consents_user_id", "banking_consents", ["user_id"])
    op.create_index("ix_banking_consents_consent_id", "banking_consents", ["consent_id"], unique=True)

    op.create_table(
        "payment_webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="PROCESSED"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_payment_webhook_events_event_id", "payment_webhook_events", ["event_id"], unique=True)
    op.create_index("ix_payment_webhook_events_event_type", "payment_webhook_events", ["event_type"])


def downgrade() -> None:
    op.drop_index("ix_payment_webhook_events_event_type", table_name="payment_webhook_events")
    op.drop_index("ix_payment_webhook_events_event_id", table_name="payment_webhook_events")
    op.drop_table("payment_webhook_events")

    op.drop_index("ix_banking_consents_consent_id", table_name="banking_consents")
    op.drop_index("ix_banking_consents_user_id", table_name="banking_consents")
    op.drop_table("banking_consents")
