"""Canonical unified ledger service normalizing all platform transaction sources."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, desc, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.cores.money import ZERO, money_to_float, to_money
from app.models.banking_consent import BankTransaction
from app.models.business import Business, Product
from app.models.purchase import PersonalPurchase
from app.models.transaction import Invoice, InvoiceItem
from app.models.unified_transaction import UnifiedTransaction
from app.models.user import User
from app.services.classifier import build_category_tree, classify_hierarchical
from app.services.customer_link import linked_customer_ids
from app.services.notifications import notify_customer_purchase, resolve_linked_customer_user


def _aware_dt(val: datetime | None) -> datetime:
    if val is None:
        return datetime.now(UTC)
    return val if val.tzinfo is not None else val.replace(tzinfo=UTC)


async def upsert_unified_transaction(
    db: AsyncSession,
    record: dict[str, Any],
    *,
    commit: bool = False,
) -> None:
    """
    Idempotently writes a normalized transaction row to `unified_transactions`
    keyed by `(source_type, source_ref_id)` and classified through `classify_hierarchical`.
    """
    source_type = str(record["source_type"])[:40]
    source_ref_id = str(record["source_ref_id"])[:180]
    direction = str(record.get("direction", "DEBIT")).upper()[:16]
    counterparty = str(record.get("counterparty") or "Merchant")[:180]
    narration = str(record.get("narration") or "")
    amount = to_money(record.get("amount", ZERO))

    cat, subcat, cls_source = classify_hierarchical(
        text=narration,
        counterparty=counterparty,
        direction=direction,
        amount=amount,
        explicit_category=record.get("category"),
        explicit_subcategory=record.get("subcategory"),
        source_type=source_type,
    )

    values = {
        "user_id": record.get("user_id"),
        "business_id": record.get("business_id"),
        "customer_id": record.get("customer_id"),
        "invoice_id": record.get("invoice_id"),
        "source_type": source_type,
        "source_ref_id": source_ref_id,
        "direction": direction,
        "side": str(record.get("side") or "CUSTOMER").upper()[:16],
        "amount": amount,
        "paid_amount": to_money(record.get("paid_amount", amount)),
        "discount_amount": max(to_money(record.get("discount_amount", ZERO) or ZERO), ZERO),
        "tax_amount": max(to_money(record.get("tax_amount", ZERO) or ZERO), ZERO),
        "currency": str(record.get("currency") or "INR")[:10],
        "status": str(record.get("status") or "RECORDED").upper()[:30],
        "channel": str(record.get("channel") or "UPI").upper()[:40],
        "app": str(record["app"])[:50] if record.get("app") else None,
        "counterparty": counterparty,
        "narration": narration,
        "category": cat,
        "subcategory": subcat,
        "classification_source": cls_source,
        "occurred_at": _aware_dt(record.get("occurred_at")),
    }

    update_fields = {
        k: v for k, v in values.items() if k not in ("source_type", "source_ref_id")
    }
    stmt = (
        insert(UnifiedTransaction)
        .values(**values)
        .on_conflict_do_update(
            constraint="uq_unified_txn_source_ref",
            set_=update_fields,
        )
    )
    await db.execute(stmt)
    if commit:
        await db.commit()


async def sync_invoice_to_unified(
    db: AsyncSession,
    invoice: Invoice,
    *,
    item_names: list[str] | None = None,
    business_name: str | None = None,
    app_name: str | None = None,
    notify: bool = False,
    event_type: str = "purchase.recorded",
    event_key: str | None = None,
    commit: bool = False,
) -> tuple[str, str]:
    """
    Normalizes a Store `Invoice` (SALE or PURCHASE) into `unified_transactions`,
    linking the verified consumer `User` when available and optionally triggering
    customer purchase/payment notifications.
    """
    if not isinstance(db, AsyncSession):
        return "Other", "General"

    biz = (
        await db.execute(select(Business).where(Business.id == invoice.business_id))
    ).scalar_one_or_none()
    resolved_store_name = business_name or (biz.name if isinstance(biz, Business) else "VyaparKitaab Store")

    if item_names is None:
        item_rows = (
            await db.execute(
                select(Product.name)
                .join(InvoiceItem, InvoiceItem.product_id == Product.id)
                .where(InvoiceItem.invoice_id == invoice.id)
            )
        ).scalars().all()
        item_names = list(item_rows)

    inv_type = (invoice.type or "SALE").upper()
    source_type = "store_sale" if inv_type == "SALE" else "store_purchase"
    linked_user = (
        await resolve_linked_customer_user(db, invoice.customer_id)
        if inv_type == "SALE" and invoice.customer_id is not None
        else None
    )

    user_owner_id = (
        linked_user.id
        if linked_user is not None
        else (biz.owner_id if (biz and inv_type == "PURCHASE") else None)
    )
    side = "BOTH" if (inv_type == "SALE" and invoice.customer_id is not None) else "STORE"
    direction = "DEBIT" if inv_type == "PURCHASE" or linked_user is not None else "CREDIT"

    narration_parts = [invoice.invoice_number, resolved_store_name]
    if item_names:
        narration_parts.append(", ".join(item_names[:6]))
    narration = " - ".join(p for p in narration_parts if p)

    cat, subcat, cls_source = classify_hierarchical(
        text=narration,
        counterparty=resolved_store_name,
        direction=direction,
        amount=to_money(invoice.total_amount or ZERO),
        source_type=source_type,
    )

    await upsert_unified_transaction(
        db,
        {
            "user_id": user_owner_id,
            "business_id": invoice.business_id,
            "customer_id": invoice.customer_id,
            "invoice_id": invoice.id,
            "source_type": source_type,
            "source_ref_id": f"inv:{invoice.id}",
            "direction": direction,
            "side": side,
            "amount": to_money(invoice.total_amount or ZERO),
            "paid_amount": to_money(invoice.paid_amount or ZERO),
            "discount_amount": to_money(invoice.discount_amount or ZERO),
            "tax_amount": to_money(invoice.tax_amount or ZERO),
            "currency": "INR",
            "status": invoice.status or "DRAFT",
            "channel": invoice.payment_method or "UPI",
            "app": app_name or invoice.payment_method,
            "counterparty": resolved_store_name,
            "narration": narration,
            "category": cat,
            "subcategory": subcat,
            "classification_source": cls_source,
            "occurred_at": invoice.created_at or datetime.now(UTC),
        },
        commit=False,
    )

    if notify and inv_type == "SALE" and (invoice.status or "").upper() in ("CONFIRMED", "PAID"):
        await notify_customer_purchase(
            db,
            invoice=invoice,
            store_name=resolved_store_name,
            category=cat,
            subcategory=subcat,
            linked_user=linked_user,
            payment_channel=invoice.payment_method,
            app_name=app_name,
            event_type=event_type,
            event_key=event_key,
            commit=False,
        )

    if commit:
        await db.commit()
    return cat, subcat


async def sync_personal_purchase_to_unified(
    db: AsyncSession,
    purchase: PersonalPurchase,
    *,
    subcategory: str | None = None,
    commit: bool = False,
) -> tuple[str, str]:
    """Normalizes a `PersonalPurchase` row into `unified_transactions`."""
    combined_note = " ".join(p for p in [purchase.marketplace, purchase.items_note or ""] if p)
    cat, subcat, cls_source = classify_hierarchical(
        text=combined_note,
        counterparty=purchase.marketplace,
        direction="DEBIT",
        amount=to_money(purchase.amount),
        explicit_category=purchase.category,
        explicit_subcategory=subcategory,
        source_type="personal_purchase",
    )

    raw_method = (purchase.payment_method or "UPI").strip()
    channel = "CARD" if "card" in raw_method.lower() else ("CASH" if "cash" in raw_method.lower() else "UPI")
    app_label = raw_method
    if "google" in raw_method.lower():
        app_label = "Google Pay"
    elif "phonepe" in raw_method.lower():
        app_label = "PhonePe"
    elif "paytm" in raw_method.lower():
        app_label = "Paytm"

    await upsert_unified_transaction(
        db,
        {
            "user_id": purchase.user_id,
            "business_id": purchase.business_id,
            "customer_id": purchase.customer_id,
            "invoice_id": None,
            "source_type": "personal_purchase",
            "source_ref_id": f"purchase:{purchase.id}",
            "direction": "DEBIT",
            "side": "CUSTOMER",
            "amount": to_money(purchase.amount),
            "paid_amount": to_money(purchase.amount),
            "discount_amount": ZERO,
            "tax_amount": ZERO,
            "currency": purchase.currency or "INR",
            "status": "RECORDED",
            "channel": channel,
            "app": app_label,
            "counterparty": purchase.marketplace,
            "narration": purchase.items_note or f"{purchase.marketplace} order",
            "category": cat,
            "subcategory": subcat,
            "classification_source": cls_source,
            "occurred_at": purchase.purchased_at,
        },
        commit=commit,
    )
    return cat, subcat


async def sync_bank_rows_to_unified(
    db: AsyncSession,
    user_id: UUID,
    rows: list[dict[str, Any]],
    *,
    commit: bool = False,
) -> None:
    """Normalizes parsed bank statement / AA / UPI bridge rows into `unified_transactions`."""
    for item in rows:
        src = str(item.get("source") or "statement_import")
        await upsert_unified_transaction(
            db,
            {
                "user_id": user_id,
                "business_id": None,
                "customer_id": None,
                "invoice_id": None,
                "source_type": src,
                "source_ref_id": f"bank:{user_id}:{item['txn_id']}",
                "direction": str(item.get("type", "DEBIT")).upper(),
                "side": "CUSTOMER",
                "amount": to_money(item["amount"]),
                "paid_amount": to_money(item["amount"]),
                "discount_amount": to_money(item.get("discount_amount", ZERO) or ZERO),
                "tax_amount": ZERO,
                "currency": "INR",
                "status": "RECORDED",
                "channel": str(item.get("mode", "UPI")).upper(),
                "app": item.get("app") or "UPI",
                "counterparty": item.get("counterparty") or "Merchant / Peer",
                "narration": item.get("narration") or "",
                "category": item.get("canonical_category") or item.get("category"),
                "subcategory": item.get("subcategory"),
                "occurred_at": item.get("timestamp") or datetime.now(UTC),
            },
            commit=False,
        )
    if commit:
        await db.commit()


async def delete_unified_source(
    db: AsyncSession,
    source_type: str,
    source_ref_id: str,
) -> None:
    await db.execute(
        delete(UnifiedTransaction).where(
            UnifiedTransaction.source_type == source_type,
            UnifiedTransaction.source_ref_id == source_ref_id,
        )
    )


async def backfill_user_unified_ledger(db: AsyncSession, user: User) -> None:
    """
    Lazily ensures any pre-existing `PersonalPurchase`, `BankTransaction`, or linked/owned `Invoice`
    created outside the unified pipeline (e.g., seed data or direct ORM fixtures) is represented
    in `unified_transactions` for seamless queries.
    """
    owned_businesses = select(Business.id).where(Business.owner_id == user.id)
    existing_refs = set(
        (
            await db.execute(
                select(UnifiedTransaction.source_ref_id).where(
                    or_(
                        UnifiedTransaction.user_id == user.id,
                        UnifiedTransaction.customer_id == user.id,
                        UnifiedTransaction.customer_id.in_(linked_customer_ids(user)),
                        UnifiedTransaction.business_id.in_(owned_businesses),
                    )
                )
            )
        )
        .scalars()
        .all()
    )

    # 1. Missing personal purchases
    purchases = (
        await db.execute(select(PersonalPurchase).where(PersonalPurchase.user_id == user.id))
    ).scalars().all()
    changed = False
    for p in purchases:
        if f"purchase:{p.id}" not in existing_refs:
            await sync_personal_purchase_to_unified(db, p, commit=False)
            changed = True

    # 2. Missing bank transactions (statements / AA / UPI bridge)
    bank_rows = (
        await db.execute(select(BankTransaction).where(BankTransaction.user_id == user.id))
    ).scalars().all()
    missing_bank = []
    for b in bank_rows:
        if f"bank:{user.id}:{b.txn_id}" not in existing_refs:
            missing_bank.append(
                {
                    "txn_id": b.txn_id,
                    "timestamp": b.timestamp,
                    "amount": to_money(b.amount),
                    "type": b.type,
                    "mode": b.mode,
                    "app": b.app,
                    "narration": b.narration,
                    "category": b.category,
                    "counterparty": b.counterparty,
                    "source": b.source,
                }
            )
    if missing_bank:
        await sync_bank_rows_to_unified(db, user.id, missing_bank, commit=False)
        changed = True

    # 3. Missing owned or linked invoices
    inv_rows = (
        await db.execute(
            select(Invoice).where(
                or_(
                    Invoice.business_id.in_(owned_businesses),
                    Invoice.customer_id == user.id,
                    Invoice.customer_id.in_(linked_customer_ids(user)),
                )
            )
        )
    ).scalars().all()
    for inv in inv_rows:
        if f"inv:{inv.id}" not in existing_refs:
            await sync_invoice_to_unified(db, inv, notify=False, commit=False)
            changed = True

    if changed:
        await db.commit()


def _unified_access_clause(user: User, view: str = "all"):
    owned_businesses = select(Business.id).where(Business.owner_id == user.id)
    store_clause = UnifiedTransaction.business_id.in_(owned_businesses)
    customer_clause = or_(
        UnifiedTransaction.user_id == user.id,
        UnifiedTransaction.customer_id == user.id,
        UnifiedTransaction.customer_id.in_(linked_customer_ids(user)),
    )
    norm_view = (view or "all").lower()
    if norm_view == "store":
        return store_clause
    if norm_view == "customer":
        return customer_clause
    return or_(store_clause, customer_clause)


async def query_unified_transactions(
    db: AsyncSession,
    user: User,
    *,
    view: str = "all",
    category: str | None = None,
    subcategory: str | None = None,
    source_type: str | None = None,
    direction: str | None = None,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    search: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """Queries the user-scoped unified ledger with hierarchical category rollup."""
    await backfill_user_unified_ledger(db, user)

    stmt = select(UnifiedTransaction).where(
        _unified_access_clause(user, view=view),
        UnifiedTransaction.status != "CANCELLED",
    )
    if (view or "all").lower() == "customer":
        stmt = stmt.where(UnifiedTransaction.status != "DRAFT")
    if category:
        stmt = stmt.where(UnifiedTransaction.category == category.strip())
    if subcategory:
        stmt = stmt.where(UnifiedTransaction.subcategory == subcategory.strip())
    if source_type:
        stmt = stmt.where(UnifiedTransaction.source_type == source_type.strip())
    if direction:
        stmt = stmt.where(UnifiedTransaction.direction == direction.strip().upper())
    if from_date is not None:
        stmt = stmt.where(UnifiedTransaction.occurred_at >= _aware_dt(from_date))
    if to_date is not None:
        stmt = stmt.where(UnifiedTransaction.occurred_at <= _aware_dt(to_date))
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                UnifiedTransaction.counterparty.ilike(pattern),
                UnifiedTransaction.narration.ilike(pattern),
                UnifiedTransaction.category.ilike(pattern),
                UnifiedTransaction.subcategory.ilike(pattern),
            )
        )

    all_rows = (
        await db.execute(stmt.order_by(desc(UnifiedTransaction.occurred_at), desc(UnifiedTransaction.created_at)))
    ).scalars().all()

    total_count = len(all_rows)
    total_discount_dec = sum((to_money(r.discount_amount) for r in all_rows), ZERO)
    total_debits_dec = sum((to_money(r.amount) for r in all_rows if r.direction == "DEBIT"), ZERO)
    total_credits_dec = sum((to_money(r.amount) for r in all_rows if r.direction == "CREDIT"), ZERO)

    is_customer_spend_view = (view or "all").lower() == "customer" and (direction or "").upper() != "CREDIT"
    summary_rows = [r for r in all_rows if r.direction == "DEBIT"] if is_customer_spend_view else all_rows
    total_amount_dec = sum((to_money(r.amount) for r in summary_rows), ZERO)

    tree_records = [
        {"category": r.category, "subcategory": r.subcategory, "amount": to_money(r.amount)}
        for r in summary_rows
    ]
    nested_summary, hierarchy_breakdown = build_category_tree(tree_records)

    page_rows = all_rows[offset : offset + limit]
    items = [
        {
            "id": str(r.id),
            "source_type": r.source_type,
            "source_ref_id": r.source_ref_id,
            "invoice_id": str(r.invoice_id) if r.invoice_id else None,
            "business_id": str(r.business_id) if r.business_id else None,
            "customer_id": str(r.customer_id) if r.customer_id else None,
            "direction": r.direction,
            "side": r.side,
            "amount": money_to_float(r.amount),
            "paid_amount": money_to_float(r.paid_amount),
            "discount_amount": money_to_float(r.discount_amount),
            "tax_amount": money_to_float(r.tax_amount),
            "currency": r.currency,
            "status": r.status,
            "channel": r.channel,
            "app": r.app,
            "counterparty": r.counterparty,
            "narration": r.narration,
            "category": r.category,
            "subcategory": r.subcategory,
            "classification_source": r.classification_source,
            "occurred_at": r.occurred_at.isoformat() if r.occurred_at else "",
        }
        for r in page_rows
    ]

    return {
        "total_count": total_count,
        "total_amount": money_to_float(total_amount_dec),
        "total_discount_saved": money_to_float(total_discount_dec),
        "total_debits": money_to_float(total_debits_dec),
        "total_credits": money_to_float(total_credits_dec),
        "nested_summary": nested_summary,
        "category_tree": hierarchy_breakdown,
        "items": items,
    }
