"""widen PII columns for Fernet encryption and add customer blind indexes

Revision ID: 0003_encrypt_pii
Revises: 0002_add_refresh_tokens
Create Date: 2026-10-20 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = "0003_encrypt_pii"
down_revision = "0002_add_refresh_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("businesses", "gstin", type_=sa.String(length=512), existing_nullable=True)
    op.alter_column("businesses", "address", type_=sa.String(length=1024), existing_nullable=True)
    op.alter_column("businesses", "phone", type_=sa.String(length=512), existing_nullable=True)

    op.alter_column("customers", "phone", type_=sa.String(length=512), existing_nullable=True)
    op.alter_column("customers", "email", type_=sa.String(length=512), existing_nullable=True)
    op.add_column("customers", sa.Column("phone_hash", sa.String(length=64), nullable=True))
    op.add_column("customers", sa.Column("email_hash", sa.String(length=64), nullable=True))
    op.create_index("ix_customers_phone_hash", "customers", ["phone_hash"])
    op.create_index("ix_customers_email_hash", "customers", ["email_hash"])


def downgrade() -> None:
    op.drop_index("ix_customers_email_hash", table_name="customers")
    op.drop_index("ix_customers_phone_hash", table_name="customers")
    op.drop_column("customers", "email_hash")
    op.drop_column("customers", "phone_hash")
    op.alter_column("customers", "email", type_=sa.String(length=255), existing_nullable=True)
    op.alter_column("customers", "phone", type_=sa.String(length=20), existing_nullable=True)

    op.alter_column("businesses", "phone", type_=sa.String(length=20), existing_nullable=True)
    op.alter_column("businesses", "address", type_=sa.String(length=500), existing_nullable=True)
    op.alter_column("businesses", "gstin", type_=sa.String(length=20), existing_nullable=True)

