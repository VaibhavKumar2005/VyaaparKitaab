"""Customer hierarchical spending classification and summary helpers."""
from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Invoice
from app.models.user import User
from app.services.classifier import LEGACY_CATEGORY_ALIASES, classify_hierarchical

CATEGORY_MAP: dict[str, str] = {k: v[0] for k, v in LEGACY_CATEGORY_ALIASES.items()}


def classify_transaction(invoice: Invoice) -> str:
    """Classifies a store invoice into the top-level hierarchical category."""
    cat, _, _ = classify_hierarchical(
        text=invoice.invoice_number or "",
        source_type="store_sale" if getattr(invoice, "type", "SALE") == "SALE" else "store_purchase",
    )
    return cat


async def get_spending_summary(
    db_or_customer_id: Any,
    user_or_from: User | date | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict[str, dict[str, float]]:
    """
    Returns nested `{category: {subcategory: total_amount}}` spending breakdown
    from the canonical `unified_transactions` ledger.
    Supports both `(db: AsyncSession, user: User, from_date, to_date)` and the
    legacy stub signature `(customer_id, from_date, to_date)`.
    """
    if isinstance(db_or_customer_id, AsyncSession) and isinstance(user_or_from, User):
        from app.services.unified_ledger import query_unified_transactions

        start_dt = (
            datetime.combine(from_date, time.min, tzinfo=UTC)
            if from_date is not None
            else None
        )
        end_dt = (
            datetime.combine(to_date, time.max, tzinfo=UTC)
            if to_date is not None
            else None
        )
        result = await query_unified_transactions(
            db_or_customer_id,
            user_or_from,
            view="customer",
            from_date=start_dt,
            to_date=end_dt,
            limit=500,
        )
        return result["nested_summary"]

    return defaultdict(lambda: defaultdict(float))
