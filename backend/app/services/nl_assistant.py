"""Natural-language assistant over the canonical unified ledger & forecasts."""
from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business import Business, Product
from app.models.transaction import Invoice
from app.models.user import User
from app.services.classifier import LEGACY_CATEGORY_ALIASES, TAXONOMY
from app.services.forecasting import generate_business_ai_forecast
from app.services.unified_ledger import query_unified_transactions


def _has_term(low_text: str, term: str) -> bool:
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", low_text))


def _extract_time_window(q: str, now: datetime) -> tuple[datetime | None, datetime | None, str]:
    low = q.lower()
    if "today" in low:
        start = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=UTC)
        return start, now, "today"
    if "this week" in low or "past 7 days" in low or "last 7 days" in low:
        return now - timedelta(days=7), now, "last 7 days"
    if "last month" in low:
        first_this_month = datetime(now.year, now.month, 1, tzinfo=UTC)
        prev_end = first_this_month - timedelta(seconds=1)
        prev_start = datetime(prev_end.year, prev_end.month, 1, tzinfo=UTC)
        return prev_start, prev_end, "last month"
    if "this month" in low or "past 30 days" in low or "last 30 days" in low:
        start = datetime(now.year, now.month, 1, 0, 0, 0, tzinfo=UTC)
        return start, now, "this month"
    return None, None, "all recorded dates"


def _extract_taxonomy_filter(q: str) -> tuple[str | None, str | None]:
    low = q.lower()
    # 1. Check specific non-generic subcategory names first (more specific than parent category)
    for cat, subcats in TAXONOMY.items():
        generic_leaf = subcats[-1]
        for sub in subcats:
            if sub == generic_leaf:
                continue
            sub_low = sub.lower()
            for token in sub_low.replace("&", " ").split():
                if len(token) >= 3 and token not in ("and", "general", "retail") and _has_term(low, token):
                    return cat, sub

    # 2. Check alias keywords (e.g. "groceries" -> Food > Grocery, "food" -> Food (all subcats))
    for alias, (cat, sub) in sorted(LEGACY_CATEGORY_ALIASES.items(), key=lambda x: len(x[0]), reverse=True):
        if len(alias) >= 3 and alias not in ("other", "general") and _has_term(low, alias):
            # Generic leaves and coarse group aliases map to parent-level breakdown (subcategory=None)
            is_coarse = sub == TAXONOMY[cat][-1] or alias in ("food & dining", "food and dining")
            return cat, None if is_coarse else sub

    # 3. Check top-level category names
    for cat in TAXONOMY:
        cat_first = cat.split("&")[0].strip().lower()
        if cat_first != "other" and _has_term(low, cat_first):
            return cat, None

    return None, None


async def answer_financial_question(
    db: AsyncSession,
    user: User,
    question: str,
) -> dict[str, Any]:
    """
    Answers user questions accurately from real PostgreSQL data (`unified_transactions`
    and time-series forecasts) without external API dependencies or fabricated metrics.
    """
    clean_q = (question or "").strip()
    low = clean_q.lower()
    now = datetime.now(UTC)

    from_dt, to_dt, period_label = _extract_time_window(low, now)
    target_cat, target_sub = _extract_taxonomy_filter(low)

    store_keywords = (
        "store",
        "revenue",
        "sales",
        "cash",
        "business",
        "profit",
        "margin",
        "earnings",
        "restock",
        "stock",
        "inventory",
        "reorder",
        "low stock",
    )
    is_store_query = (user.role == "STORE_OWNER" and any(k in low for k in store_keywords)) or "store revenue" in low
    view = "store" if is_store_query else "customer"

    if any(k in low for k in ("restock", "reorder", "low stock")) or ("product" in low and "stock" in low):
        forecast_data = await generate_business_ai_forecast(db=db, user_id=user.id, lookback_days=30, horizon_days=7)
        owned_businesses = select(Business.id).where(Business.owner_id == user.id)
        low_stock_rows = (
            await db.execute(
                select(Product)
                .where(Product.business_id.in_(owned_businesses), Product.stock_qty <= 10)
                .order_by(Product.stock_qty.asc())
            )
        ).scalars().all()
        inv_forecasts = forecast_data.get("inventory_forecasts", [])
        alert_items = [
            f"{item['name']} ({int(item['current_stock'])} left, reorder ~{int(item['recommended_reorder_qty'])})"
            for item in inv_forecasts
            if item.get("urgency") in ("CRITICAL", "WARNING") or float(item.get("recommended_reorder_qty", 0)) > 0
        ]
        if not alert_items and low_stock_rows:
            alert_items = [f"{p.name} ({int(p.stock_qty)} {p.unit or 'units'} left)" for p in low_stock_rows[:5]]
        count_alerts = max(len(alert_items), len(low_stock_rows))
        answer = (
            f"You should restock {count_alerts} product(s): {', '.join(alert_items[:5])}."
            if alert_items
            else "All products in your store inventory are currently well-stocked above reorder thresholds."
        )
        return {
            "question": clean_q,
            "intent": "restock_alert",
            "answer": answer,
            "filters": {"period": "current inventory", "view": "store"},
            "metrics": {
                "low_stock_count": len(low_stock_rows),
                "critical_restock_count": int(forecast_data.get("critical_restock_count", 0)),
            },
            "category_breakdown": [],
            "sample_transactions": [],
        }

    if "profit" in low or "margin" in low or "net earnings" in low:
        owned_businesses = select(Business.id).where(Business.owner_id == user.id)
        stmt = select(Invoice).where(
            Invoice.business_id.in_(owned_businesses),
            Invoice.status.notin_(["CANCELLED", "DRAFT"]),
        )
        if from_dt is not None:
            stmt = stmt.where(Invoice.created_at >= from_dt)
        if to_dt is not None:
            stmt = stmt.where(Invoice.created_at <= to_dt)
        invs = (await db.execute(stmt)).scalars().all()
        sales_total = round(sum(float(i.total_amount or 0.0) for i in invs if (i.type or "").upper() == "SALE"), 2)
        purchases_total = round(sum(float(i.total_amount or 0.0) for i in invs if (i.type or "").upper() == "PURCHASE"), 2)
        discounts_total = round(sum(float(i.discount_amount or 0.0) for i in invs if (i.type or "").upper() == "SALE"), 2)
        net_profit = round(sales_total - purchases_total, 2)
        answer = (
            f"Your store net profit for {period_label} is ₹{net_profit:,.2f} "
            f"(Sales: ₹{sales_total:,.2f}, Supplier Purchases: ₹{purchases_total:,.2f}, Discounts given: ₹{discounts_total:,.2f})."
        )
        return {
            "question": clean_q,
            "intent": "store_profit",
            "answer": answer,
            "filters": {"period": period_label, "view": "store"},
            "metrics": {
                "net_profit": net_profit,
                "sales_revenue": sales_total,
                "purchase_cost": purchases_total,
                "discounts_given": discounts_total,
                "invoice_count": len(invs),
            },
            "category_breakdown": [],
            "sample_transactions": [],
        }

    if "forecast" in low or "predict" in low or "next week" in low:
        forecast_data = await generate_business_ai_forecast(db=db, user_id=user.id, lookback_days=30, horizon_days=7)
        projected = forecast_data.get("projected_7d_revenue", 0.0)
        selected_model = forecast_data.get("selected_model", "RidgeRegression")
        answer = (
            f"Based on your historical sales using {selected_model}, your projected 7-day revenue is ₹{projected:,.2f}."
            if projected > 0
            else "There is not enough historical sales data yet to compute a 7-day revenue projection."
        )
        return {
            "question": clean_q,
            "intent": "forecast",
            "answer": answer,
            "filters": {"period": "next 7 days", "view": "store"},
            "metrics": {
                "projected_7d_revenue": projected,
                "selected_model": selected_model,
            },
            "category_breakdown": [],
            "sample_transactions": [],
        }

    ledger = await query_unified_transactions(
        db,
        user,
        view=view,
        category=target_cat,
        subcategory=target_sub,
        from_date=from_dt,
        to_date=to_dt,
        limit=100,
    )

    items = ledger["items"]
    total_amt = ledger["total_amount"]
    total_disc = ledger["total_discount_saved"]
    count = ledger["total_count"]
    tree = ledger["category_tree"]

    if "discount" in low or "saved" in low or "saving" in low:
        answer = (
            f"You saved ₹{total_disc:,.2f} in total discounts across {count} transaction(s) ({period_label})."
            if total_disc > 0
            else f"No discount savings were recorded across your {count} transaction(s) for {period_label}."
        )
        intent = "discount_savings"
    elif target_cat or target_sub:
        scope_name = f"{target_cat} > {target_sub}" if target_sub else str(target_cat)
        sub_summary = ""
        if tree and not target_sub and tree[0].get("subcategories"):
            parts = [f"{s['subcategory']}: ₹{s['total_amount']:,.2f}" for s in tree[0]["subcategories"][:4]]
            sub_summary = f" Breakdown: {', '.join(parts)}."
        verb = "recorded" if is_store_query else "spent"
        answer = (
            f"You {verb} ₹{total_amt:,.2f} on {scope_name} ({period_label}) across {count} transaction(s).{sub_summary}"
            if count > 0
            else f"You have ₹0.00 recorded under {scope_name} for {period_label}."
        )
        intent = "category_spend"
    else:
        top_cats = ", ".join(f"{c['category']}: ₹{c['total_amount']:,.2f}" for c in tree[:3])
        if count == 0:
            answer = f"No transactions were found in your ledger for {period_label}."
        elif is_store_query:
            answer = (
                f"Your store recorded ₹{total_amt:,.2f} across {count} transaction(s) ({period_label}), "
                f"with ₹{total_disc:,.2f} given in discounts."
                + (f" Top categories: {top_cats}." if top_cats else "")
            )
        else:
            answer = (
                f"Your total spending for {period_label} is ₹{ledger['total_debits']:,.2f} across {count} transaction(s)"
                + (f" (saved ₹{total_disc:,.2f} in discounts)" if total_disc > 0 else "")
                + (f". Top categories: {top_cats}." if top_cats else ".")
            )
        intent = "overall_summary"

    return {
        "question": clean_q,
        "intent": intent,
        "answer": answer,
        "filters": {
            "view": view,
            "period": period_label,
            "category": target_cat,
            "subcategory": target_sub,
        },
        "metrics": {
            "total_amount": total_amt,
            "total_debits": ledger["total_debits"],
            "total_credits": ledger["total_credits"],
            "total_discount_saved": total_disc,
            "transaction_count": count,
        },
        "category_breakdown": tree,
        "sample_transactions": items[:5],
    }
