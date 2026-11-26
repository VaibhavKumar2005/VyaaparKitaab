from datetime import UTC, date, datetime, time
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.cores.database import get_db
from app.models.business import Business, Customer, Product
from app.models.transaction import Invoice, InvoiceItem
from app.models.unified_transaction import UnifiedTransaction
from app.models.user import User
from app.schemas.transaction import (
    CustomerInvoiceRead,
    CustomerNotificationRead,
    InvoiceCreate,
    InvoiceItemRead,
    InvoiceRead,
    SpendingSummary,
    UnifiedCategoryUpdate,
    UnifiedTransactionFeedResponse,
    UnifiedTransactionRead,
)
from app.services.auth import get_current_user
from app.services.classifier import learn_category_override
from app.services.customer_link import linked_customer_ids
from app.services.notifications import list_customer_notifications, mark_notifications_read
from app.services.spending import get_spending_summary
from app.services.unified_ledger import (
    _unified_access_clause,
    query_unified_transactions,
    sync_invoice_to_unified,
)

router = APIRouter(tags=["transactions"])

VALID_INVOICE_TYPES = {"SALE", "PURCHASE"}
VALID_INVOICE_STATUSES = {"DRAFT", "CONFIRMED", "PAID", "CANCELLED"}
DEFAULT_GST_RATE = 0.05


async def _load_business_map(db: AsyncSession, business_ids: set[UUID]) -> dict[UUID, Business]:
    if not business_ids:
        return {}
    rows = (await db.execute(select(Business).where(Business.id.in_(business_ids)))).scalars().all()
    return {b.id: b for b in rows}


def _serialize_invoice(invoice: Invoice, business: Business | None) -> InvoiceRead:
    return InvoiceRead(
        id=invoice.id,
        invoice_number=invoice.invoice_number,
        business_id=invoice.business_id,
        customer_id=invoice.customer_id,
        type=invoice.type,
        status=invoice.status,
        subtotal=float(invoice.subtotal or 0.0),
        tax_amount=float(invoice.tax_amount or 0.0),
        discount_amount=float(invoice.discount_amount or 0.0),
        total_amount=float(invoice.total_amount or 0.0),
        paid_amount=float(invoice.paid_amount or 0.0),
        payment_method=invoice.payment_method,
        created_at=invoice.created_at,
        store_name=business.name if business else None,
        store_gstin=business.gstin if business else None,
        store_address=business.address if business else None,
        store_phone=business.phone if business else None,
        store_upi_vpa=business.upi_vpa if business else None,
        items=[
            InvoiceItemRead(
                id=it.id,
                product_id=it.product_id,
                quantity=float(it.quantity),
                unit_price=float(it.unit_price),
                discount=float(it.discount or 0.0),
                line_total=float(it.line_total),
            )
            for it in (invoice.items or [])
        ],
    )


async def _serialize_invoices(db: AsyncSession, invoices: list[Invoice]) -> list[InvoiceRead]:
    biz_map = await _load_business_map(db, {inv.business_id for inv in invoices})
    return [_serialize_invoice(inv, biz_map.get(inv.business_id)) for inv in invoices]


@router.post("/invoices", response_model=InvoiceRead)
async def create_invoice(
    payload: InvoiceCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    biz_res = await db.execute(
        select(Business).where(Business.id == payload.business_id, Business.owner_id == user.id)
    )
    business = biz_res.scalar_one_or_none()
    if not business or business.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized for this business")

    inv_type = payload.type.upper()
    if inv_type not in VALID_INVOICE_TYPES:
        raise HTTPException(status_code=400, detail="Invalid invoice type")

    inv_status = payload.status.upper()
    if inv_status not in VALID_INVOICE_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid invoice status")

    # Compute line totals and subtotal strictly server-side using exact Decimal arithmetic
    from decimal import Decimal

    from app.cores.money import ZERO, to_money

    computed_subtotal = ZERO
    validated_items: list[tuple[Product | None, Decimal, Decimal, Decimal, Decimal]] = []

    for item in payload.items:
        qty_dec = to_money(item.quantity)
        price_dec = to_money(item.unit_price)
        disc_dec = to_money(item.discount)
        if qty_dec <= ZERO or price_dec < ZERO or disc_dec < ZERO:
            raise HTTPException(status_code=400, detail="Invalid item quantity, price, or discount")

        prod_res = await db.execute(
            select(Product).where(
                Product.id == item.product_id,
                Product.business_id == payload.business_id,
            )
        )
        product = prod_res.scalar_one_or_none()
        if not product:
            raise HTTPException(status_code=400, detail=f"Product {item.product_id} does not belong to this business")

        line_total = max(to_money(qty_dec * price_dec) - disc_dec, ZERO)
        computed_subtotal += line_total
        validated_items.append((product, qty_dec, price_dec, disc_dec, line_total))

    computed_subtotal = to_money(computed_subtotal)
    invoice_discount = max(to_money(payload.discount_amount or ZERO), ZERO)
    taxable_amount = max(computed_subtotal - invoice_discount, ZERO)
    if payload.gst_rate is not None:
        computed_tax = to_money(taxable_amount * Decimal(str(payload.gst_rate)))
    else:
        computed_tax = (
            to_money(taxable_amount * Decimal(str(DEFAULT_GST_RATE)))
            if payload.tax_amount is None or to_money(payload.tax_amount) > ZERO
            else ZERO
        )
    computed_total = to_money(taxable_amount + computed_tax)

    initial_paid = (
        computed_total
        if inv_status == "PAID"
        else min(max(to_money(payload.paid_amount or ZERO), ZERO), computed_total)
    )

    invoice = Invoice(
        invoice_number=payload.invoice_number,
        business_id=payload.business_id,
        customer_id=payload.customer_id,
        type=inv_type,
        status=inv_status,
        subtotal=computed_subtotal,
        tax_amount=computed_tax,
        discount_amount=invoice_discount,
        total_amount=computed_total,
        paid_amount=initial_paid,
        payment_method=payload.payment_method,
    )
    db.add(invoice)
    await db.flush()

    item_models = []
    for product, qty, unit_price, discount, line_total in validated_items:
        item_model = InvoiceItem(
            invoice_id=invoice.id,
            product_id=product.id,
            quantity=qty,
            unit_price=unit_price,
            discount=discount,
            line_total=line_total,
        )
        db.add(item_model)
        item_models.append(item_model)

        # Deduct or replenish stock when invoice is confirmed or paid
        if inv_status in ("CONFIRMED", "PAID") and product is not None:
            if inv_type == "SALE":
                product.stock_qty = max(ZERO, to_money(product.stock_qty) - qty)
            elif inv_type == "PURCHASE":
                product.stock_qty = to_money(product.stock_qty) + qty

    await sync_invoice_to_unified(
        db,
        invoice,
        item_names=[p.name for p, *_ in validated_items if p is not None],
        business_name=business.name,
        notify=(inv_type == "SALE" and inv_status in ("CONFIRMED", "PAID")),
        event_type="purchase.recorded",
        event_key=f"inv_create:{invoice.id}:{inv_status}",
        commit=False,
    )

    await db.commit()
    refreshed = await db.execute(
        select(Invoice).options(selectinload(Invoice.items)).where(Invoice.id == invoice.id)
    )
    return _serialize_invoice(refreshed.scalar_one(), business)


@router.get("/invoices", response_model=list[InvoiceRead])
async def list_invoices(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    owned_businesses = select(Business.id).where(Business.owner_id == user.id)
    result = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.items))
        .where(Invoice.business_id.in_(owned_businesses))
    )
    return await _serialize_invoices(db, list(result.scalars().all()))


@router.get("/invoices/export/gstr1")
async def export_gstr1_summary(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Exports an Indian GSTR-1 JSON summary across all confirmed/paid SALE invoices for the store owner."""
    owned_businesses = (
        await db.execute(select(Business).where(Business.owner_id == user.id))
    ).scalars().all()
    if not owned_businesses:
        return {
            "gstin": None,
            "store_name": None,
            "fp": datetime.now(UTC).strftime("%m%Y"),
            "generated_at": datetime.now(UTC).isoformat(),
            "summary": {
                "total_invoices": 0,
                "taxable_value": 0.0,
                "cgst": 0.0,
                "sgst": 0.0,
                "igst": 0.0,
                "total_tax": 0.0,
                "invoice_value": 0.0,
            },
            "invoices": [],
        }

    biz_ids = [b.id for b in owned_businesses]
    primary_biz = owned_businesses[0]
    inv_rows = (
        await db.execute(
            select(Invoice)
            .where(
                Invoice.business_id.in_(biz_ids),
                Invoice.type == "SALE",
                Invoice.status.in_(["CONFIRMED", "PAID"]),
            )
            .order_by(Invoice.created_at.desc())
        )
    ).scalars().all()

    total_taxable = 0.0
    total_tax = 0.0
    total_value = 0.0
    export_rows = []
    for inv in inv_rows:
        taxable = round(max(float(inv.subtotal or 0.0) - float(inv.discount_amount or 0.0), 0.0), 2)
        tax = round(float(inv.tax_amount or 0.0), 2)
        val = round(float(inv.total_amount or 0.0), 2)
        half_tax = round(tax / 2.0, 2)
        rate_pct = round((tax / taxable) * 100.0, 1) if taxable > 0 else 0.0
        total_taxable = round(total_taxable + taxable, 2)
        total_tax = round(total_tax + tax, 2)
        total_value = round(total_value + val, 2)
        export_rows.append(
            {
                "inum": inv.invoice_number,
                "idt": inv.created_at.strftime("%d-%m-%Y") if inv.created_at else "",
                "status": inv.status,
                "txval": taxable,
                "rt": rate_pct,
                "camt": half_tax,
                "samt": round(tax - half_tax, 2),
                "iamt": 0.0,
                "val": val,
            }
        )

    total_cgst = round(total_tax / 2.0, 2)
    return {
        "gstin": primary_biz.gstin,
        "store_name": primary_biz.name,
        "fp": datetime.now(UTC).strftime("%m%Y"),
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": {
            "total_invoices": len(export_rows),
            "taxable_value": total_taxable,
            "cgst": total_cgst,
            "sgst": round(total_tax - total_cgst, 2),
            "igst": 0.0,
            "total_tax": total_tax,
            "invoice_value": total_value,
        },
        "invoices": export_rows,
    }


@router.get("/portal/my-bills", response_model=list[CustomerInvoiceRead])
async def list_customer_bills(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Strictly isolated customer endpoint: returns only SALE invoices belonging to the customer."""
    result = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.items))
        .where(
            Invoice.type == "SALE",
            (Invoice.customer_id == user.id) | (Invoice.customer_id.in_(linked_customer_ids(user))),
        )
        .order_by(Invoice.created_at.desc())
    )
    return await _serialize_invoices(db, list(result.scalars().all()))


@router.get("/portal/my-bills/{invoice_id}", response_model=CustomerInvoiceRead)
async def get_customer_bill(invoice_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Single bill for the linked customer; 404 for anything that is not theirs."""
    result = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.items))
        .where(
            Invoice.id == invoice_id,
            Invoice.type == "SALE",
            (Invoice.customer_id == user.id) | (Invoice.customer_id.in_(linked_customer_ids(user))),
        )
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Bill not found")
    biz_map = await _load_business_map(db, {invoice.business_id})
    return _serialize_invoice(invoice, biz_map.get(invoice.business_id))


@router.get("/invoices/{invoice_id}", response_model=InvoiceRead)
async def get_invoice(invoice_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    owned_businesses = select(Business.id).where(Business.owner_id == user.id)
    result = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.items))
        .where(Invoice.id == invoice_id, Invoice.business_id.in_(owned_businesses))
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    biz_map = await _load_business_map(db, {invoice.business_id})
    return _serialize_invoice(invoice, biz_map.get(invoice.business_id))


@router.patch("/invoices/{invoice_id}/status", response_model=InvoiceRead)
async def update_invoice_status(
    invoice_id: UUID,
    status: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    clean_status = status.strip().upper()
    if clean_status not in VALID_INVOICE_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Allowed: {', '.join(VALID_INVOICE_STATUSES)}")

    owned_businesses = select(Business.id).where(Business.owner_id == user.id)
    result = await db.execute(select(Invoice).where(Invoice.id == invoice_id, Invoice.business_id.in_(owned_businesses)))
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    invoice.status = clean_status
    if clean_status == "PAID":
        invoice.paid_amount = invoice.total_amount

    await sync_invoice_to_unified(
        db,
        invoice,
        notify=(invoice.type == "SALE" and clean_status in ("CONFIRMED", "PAID")),
        event_type="purchase.recorded",
        event_key=f"inv_status:{invoice.id}:{clean_status}",
        commit=False,
    )
    await db.commit()
    refreshed = await db.execute(
        select(Invoice).options(selectinload(Invoice.items)).where(Invoice.id == invoice.id)
    )
    inv_row = refreshed.scalar_one()
    biz_map = await _load_business_map(db, {inv_row.business_id})
    return _serialize_invoice(inv_row, biz_map.get(inv_row.business_id))


@router.get("/dashboard/store")
async def store_dashboard(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    owned_businesses = select(Business.id).where(Business.owner_id == user.id)
    active_sale_statuses = Invoice.status.notin_(["CANCELLED", "DRAFT"])
    total_revenue = await db.execute(
        select(func.coalesce(func.sum(Invoice.paid_amount), 0)).where(
            Invoice.type == "SALE", active_sale_statuses, Invoice.business_id.in_(owned_businesses)
        )
    )
    pending = await db.execute(
        select(func.count()).select_from(Invoice).where(
            Invoice.status == "DRAFT", Invoice.business_id.in_(owned_businesses)
        )
    )
    low_stock = await db.execute(
        select(func.count()).select_from(Product).where(
            Product.stock_qty <= 5, Product.business_id.in_(owned_businesses)
        )
    )
    customers = await db.execute(
        select(func.count()).select_from(Customer).where(
            Customer.business_id.in_(owned_businesses)
        )
    )

    recent_res = await db.execute(
        select(Invoice)
        .where(Invoice.business_id.in_(owned_businesses))
        .order_by(Invoice.created_at.desc())
        .limit(8)
    )
    recent_invoices = list(recent_res.scalars().all())

    top_res = await db.execute(
        select(Product.name, func.coalesce(func.sum(InvoiceItem.line_total), 0).label("sales"))
        .join(InvoiceItem, InvoiceItem.product_id == Product.id)
        .join(Invoice, Invoice.id == InvoiceItem.invoice_id)
        .where(Invoice.type == "SALE", active_sale_statuses, Product.business_id.in_(owned_businesses))
        .group_by(Product.id, Product.name)
        .order_by(func.sum(InvoiceItem.line_total).desc())
        .limit(5)
    )
    top_products = [{"name": row[0], "sales": float(row[1])} for row in top_res.all()]

    discounts_given = await db.execute(
        select(func.coalesce(func.sum(Invoice.discount_amount), 0)).where(
            Invoice.type == "SALE", active_sale_statuses, Invoice.business_id.in_(owned_businesses)
        )
    )

    sale_inv_rows = (
        await db.execute(
            select(Invoice)
            .where(Invoice.type == "SALE", active_sale_statuses, Invoice.business_id.in_(owned_businesses))
            .order_by(Invoice.created_at.asc())
        )
    ).scalars().all()

    method_totals: dict[str, dict] = {}
    daily_series_map: dict[str, dict] = {}
    for inv in sale_inv_rows:
        m_key = (inv.payment_method or "UNPAID").upper()
        if m_key not in method_totals:
            method_totals[m_key] = {"method": m_key, "amount": 0.0, "count": 0}
        amt = float(inv.paid_amount or 0.0) if float(inv.paid_amount or 0.0) > 0 else float(inv.total_amount or 0.0)
        method_totals[m_key]["amount"] = round(method_totals[m_key]["amount"] + amt, 2)
        method_totals[m_key]["count"] += 1

        day_key = inv.created_at.strftime("%Y-%m-%d") if inv.created_at else datetime.now(UTC).strftime("%Y-%m-%d")
        if day_key not in daily_series_map:
            daily_series_map[day_key] = {"date": day_key, "revenue": 0.0, "count": 0}
        daily_series_map[day_key]["revenue"] = round(daily_series_map[day_key]["revenue"] + float(inv.paid_amount or 0.0), 2)
        daily_series_map[day_key]["count"] += 1

    cat_rows = (
        await db.execute(
            select(
                UnifiedTransaction.category,
                func.coalesce(func.sum(UnifiedTransaction.amount), 0.0),
                func.count(UnifiedTransaction.id),
            )
            .where(
                UnifiedTransaction.business_id.in_(owned_businesses),
                UnifiedTransaction.source_type == "store_sale",
                UnifiedTransaction.status.notin_(["CANCELLED", "DRAFT"]),
            )
            .group_by(UnifiedTransaction.category)
            .order_by(func.sum(UnifiedTransaction.amount).desc())
        )
    ).all()
    category_breakdown = [
        {"category": row[0], "amount": round(float(row[1]), 2), "count": int(row[2])}
        for row in cat_rows
    ]

    return {
        "todayRevenue": float(total_revenue.scalar_one()),
        "totalCustomers": int(customers.scalar_one()),
        "lowStockItems": int(low_stock.scalar_one()),
        "pendingInvoices": int(pending.scalar_one()),
        "totalDiscountsGiven": round(float(discounts_given.scalar_one()), 2),
        "paymentBreakdown": sorted(method_totals.values(), key=lambda x: x["amount"], reverse=True),
        "categoryBreakdown": category_breakdown,
        "topProducts": top_products,
        "recentTransactions": [
            {
                "invoice_number": inv.invoice_number,
                "total_amount": float(inv.total_amount),
                "discount_amount": float(inv.discount_amount or 0.0),
                "payment_method": inv.payment_method,
                "status": inv.status,
                "created_at": inv.created_at.isoformat() if inv.created_at else "",
            }
            for inv in recent_invoices
        ],
        "revenueSeries": sorted(daily_series_map.values(), key=lambda d: d["date"])[-14:],
    }


@router.get("/dashboard/customer/me", response_model=SpendingSummary)
async def customer_dashboard_me(
    from_date: date | None = None,
    to_date: date | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    summary = await get_spending_summary(db, user, from_date=from_date, to_date=to_date)
    return SpendingSummary(customer_id=user.id, from_date=from_date, to_date=to_date, summary=summary)


@router.get("/dashboard/customer/{customer_id}", response_model=SpendingSummary)
async def customer_dashboard(
    customer_id: UUID,
    from_date: date | None = None,
    to_date: date | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role == "CUSTOMER" and user.id != customer_id:
        raise HTTPException(status_code=403, detail="Not authorized to view another customer's dashboard")
    if user.id == customer_id:
        summary = await get_spending_summary(db, user, from_date=from_date, to_date=to_date)
        return SpendingSummary(customer_id=customer_id, from_date=from_date, to_date=to_date, summary=summary)

    owned_businesses = select(Business.id).where(Business.owner_id == user.id)
    cust_check = (
        await db.execute(
            select(Customer).where(Customer.id == customer_id, Customer.business_id.in_(owned_businesses))
        )
    ).scalar_one_or_none()
    if cust_check is None:
        raise HTTPException(status_code=403, detail="Not authorized to view this customer")

    rows = (
        await db.execute(
            select(UnifiedTransaction.category, UnifiedTransaction.subcategory, func.coalesce(func.sum(UnifiedTransaction.amount), 0.0))
            .where(
                UnifiedTransaction.customer_id == customer_id,
                UnifiedTransaction.business_id.in_(owned_businesses),
                UnifiedTransaction.status.notin_(["CANCELLED", "DRAFT"]),
            )
            .group_by(UnifiedTransaction.category, UnifiedTransaction.subcategory)
        )
    ).all()
    summary: dict[str, dict[str, float]] = {}
    for cat, subcat, amt in rows:
        summary.setdefault(cat, {})[subcat] = round(float(amt), 2)
    return SpendingSummary(customer_id=customer_id, from_date=from_date, to_date=to_date, summary=summary)


@router.get("/transactions/unified", response_model=UnifiedTransactionFeedResponse)
async def list_unified_transactions(
    view: str = Query(default="all", pattern="^(all|customer|store)$"),
    category: str | None = None,
    subcategory: str | None = None,
    source_type: str | None = None,
    direction: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    search: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    start_dt = datetime.combine(from_date, time.min, tzinfo=UTC) if from_date else None
    end_dt = datetime.combine(to_date, time.max, tzinfo=UTC) if to_date else None
    return await query_unified_transactions(
        db,
        user,
        view=view,
        category=category,
        subcategory=subcategory,
        source_type=source_type,
        direction=direction,
        from_date=start_dt,
        to_date=end_dt,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.patch("/transactions/unified/{transaction_id}/category", response_model=UnifiedTransactionRead)
async def update_unified_transaction_category(
    transaction_id: UUID,
    payload: UnifiedCategoryUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = (
        await db.execute(
            select(UnifiedTransaction).where(
                UnifiedTransaction.id == transaction_id,
                _unified_access_clause(user, view="all"),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Unified transaction not found")

    cat, sub = learn_category_override(row.counterparty, row.narration, payload.category, payload.subcategory)
    row.category = cat
    row.subcategory = sub
    row.classification_source = "user_learned"
    await db.commit()
    await db.refresh(row)

    return UnifiedTransactionRead(
        id=str(row.id),
        source_type=row.source_type,
        source_ref_id=row.source_ref_id,
        invoice_id=str(row.invoice_id) if row.invoice_id else None,
        business_id=str(row.business_id) if row.business_id else None,
        customer_id=str(row.customer_id) if row.customer_id else None,
        direction=row.direction,
        side=row.side,
        amount=round(float(row.amount), 2),
        paid_amount=round(float(row.paid_amount), 2),
        discount_amount=round(float(row.discount_amount), 2),
        tax_amount=round(float(row.tax_amount), 2),
        currency=row.currency,
        status=row.status,
        channel=row.channel,
        app=row.app,
        counterparty=row.counterparty,
        narration=row.narration,
        category=row.category,
        subcategory=row.subcategory,
        classification_source=row.classification_source,
        occurred_at=row.occurred_at.isoformat() if row.occurred_at else "",
    )


@router.get("/portal/notifications", response_model=list[CustomerNotificationRead])
async def get_customer_notifications(
    limit: int = Query(default=30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await list_customer_notifications(db, user, limit=limit)


@router.post("/portal/notifications/read-all")
async def read_all_customer_notifications(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    updated = await mark_notifications_read(db, user, notification_id=None)
    return {"status": "ok", "updated": updated}


@router.post("/portal/notifications/{notification_id}/read")
async def read_customer_notification(
    notification_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    updated = await mark_notifications_read(db, user, notification_id=notification_id)
    return {"status": "ok", "updated": updated}