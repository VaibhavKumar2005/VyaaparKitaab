"""link personal purchases to businesses and customers

Revision ID: 0011_link_purchases_to_business_customers
Revises: 0010_add_aa_consent_otp_purpose
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_link_purchases_to_business_customers"
down_revision: str | None = "0010_add_aa_consent_otp_purpose"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "personal_purchases",
        sa.Column(
            "business_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("businesses.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "personal_purchases",
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_personal_purchases_business_id", "personal_purchases", ["business_id"])
    op.create_index("ix_personal_purchases_customer_id", "personal_purchases", ["customer_id"])


def downgrade() -> None:
    op.drop_index("ix_personal_purchases_customer_id", table_name="personal_purchases")
    op.drop_index("ix_personal_purchases_business_id", table_name="personal_purchases")
    op.drop_column("personal_purchases", "customer_id")
    op.drop_column("personal_purchases", "business_id")
