"""add account aggregator consent OTP purpose

Revision ID: 0010_add_aa_consent_otp_purpose
Revises: 0009_user_verified_flags
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010_add_aa_consent_otp_purpose"
down_revision: str | None = "0009_user_verified_flags"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE otp_purpose ADD VALUE IF NOT EXISTS 'AA_CONSENT'")


def downgrade() -> None:
    # PostgreSQL does not support removing an enum value in place. The value is
    # harmless for databases rolled back to the previous application version.
    pass
