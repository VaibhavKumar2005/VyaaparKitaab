"""Enforce PostgreSQL Row-Level Security (FORCE RLS) across all private user financial tables.

Revision ID: 0015_beta_rls_policies
Revises: 0014_decimal_and_ratelimit
Create Date: 2026-11-27
"""

import sqlalchemy as sa
from alembic import op

revision = "0015_beta_rls_policies"
down_revision = "0014_decimal_and_ratelimit"
branch_labels = None
depends_on = None

# Tables strictly owned by a single `user_id` column
_USER_OWNED_TABLES = (
    "personal_purchases",
    "bank_transactions",
    "banking_consents",
    "refresh_tokens",
)


def _policy_expr_user_id() -> str:
    return (
        "("
        "(COALESCE(current_setting('app.rls_strict', true), '') <> 'on' "
        " AND NULLIF(current_setting('app.current_user_id', true), '') IS NULL)"
        " OR user_id::text = NULLIF(current_setting('app.current_user_id', true), '')"
        ")"
    )


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())

    # 1. Strict per-user FORCE RLS on private financial & session tables
    for tbl in _USER_OWNED_TABLES:
        if tbl not in tables:
            continue
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY;")
        op.execute(f"DROP POLICY IF EXISTS {tbl}_user_isolation ON {tbl};")
        op.execute(
            f"""
            CREATE POLICY {tbl}_user_isolation ON {tbl}
            FOR ALL
            USING {_policy_expr_user_id()}
            WITH CHECK {_policy_expr_user_id()};
            """
        )

    # 2. Two-sided tables: unified_transactions & customer_notifications
    for tbl in ("unified_transactions", "customer_notifications"):
        if tbl not in tables:
            continue
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY;")
        op.execute(f"DROP POLICY IF EXISTS {tbl}_tenant_isolation ON {tbl};")
        op.execute(
            f"""
            CREATE POLICY {tbl}_tenant_isolation ON {tbl}
            FOR ALL
            USING (
                (COALESCE(current_setting('app.rls_strict', true), '') <> 'on'
                 AND NULLIF(current_setting('app.current_user_id', true), '') IS NULL)
                OR user_id::text = NULLIF(current_setting('app.current_user_id', true), '')
                OR customer_id::text = NULLIF(current_setting('app.current_user_id', true), '')
                OR business_id IN (
                    SELECT id FROM businesses
                    WHERE owner_id::text = NULLIF(current_setting('app.current_user_id', true), '')
                )
            );
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())

    for tbl in ("unified_transactions", "customer_notifications"):
        if tbl not in tables:
            continue
        op.execute(f"DROP POLICY IF EXISTS {tbl}_tenant_isolation ON {tbl};")
        op.execute(f"ALTER TABLE {tbl} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY;")

    for tbl in ("bank_transactions", "banking_consents", "refresh_tokens"):
        if tbl not in tables:
            continue
        op.execute(f"DROP POLICY IF EXISTS {tbl}_user_isolation ON {tbl};")
        op.execute(f"ALTER TABLE {tbl} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY;")

    if "personal_purchases" in tables:
        op.execute("ALTER TABLE personal_purchases NO FORCE ROW LEVEL SECURITY;")
