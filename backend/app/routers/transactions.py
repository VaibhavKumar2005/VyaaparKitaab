from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from uuid import UUID

from app.cores.database import get_db
from app.models.business import Business, Customer, Product
from app.models.transaction import Invoice, InvoiceItem
from app.schemas.transaction import CustomerInvoiceRead, InvoiceCreate, InvoiceRead, SpendingSummary
from app.services.auth import get_current_user
from app.services.spending import classify_transaction
from app.models.user import User

router = APIRouter(tags=["transactions"])

VALID_INVOICE_TYPES = {"SALE", "PURCHASE"}
VALID_INVOICE_STATUSES = {"DRAFT", "CONFIRMED", "PAID", "CANCELLED"}
DEFAULT_GST_RATE = 0.05


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

    # Compute line totals and subtotal strictly server-side
    computed_subtotal = 0.0
    validated_items: list[tuple[Product | None, float, float, float, float]] = []

    for item in payload.items:
        if item.quantity <= 0 or item.unit_price < 0 or item.discount < 0:
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

        line_total = round(max((float(item.quantity) * float(item.unit_price)) - float(item.discount), 0.0), 2)
        computed_subtotal += line_total
        validated_items.append((product, float(item.quantity), float(item.unit_price), float(item.discount), line_total))

    computed_subtotal = round(computed_subtotal, 2)
    invoice_discount = round(max(float(payload.discount_amount or 0.0), 0.0), 2)
    taxable_amount = max(computed_subtotal - invoice_discount, 0.0)
    computed_tax = round(taxable_amount * DEFAULT_GST_RATE, 2) if payload.tax_amount is None or payload.tax_amount > 0 else 0.0
    computed_total = round(taxable_amount + computed_tax, 2)

    initial_paid = computed_total if inv_status == "PAID" else min(max(float(payload.paid_amount or 0.0), 0.0), computed_total)

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
                product.stock_qty = max(0.0, float(product.stock_qty) - qty)
            elif inv_type == "PURCHASE":
                product.stock_qty = float(product.stock_qty) + qty

    await db.commit()
    await db.refresh(invoice)
    invoice.items = item_models
    return invoice


@router.get("/invoices", response_model=list[InvoiceRead])
async def list_invoices(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    owned_businesses = select(Business.id).where(Business.owner_id == user.id)
    result = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.items))
        .where(Invoice.business_id.in_(owned_businesses))
    )
    return list(result.scalars().all())


@router.get("/portal/my-bills", response_model=list[CustomerInvoiceRead])
async def list_customer_bills(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Strictly isolated customer endpoint: returns only SALE invoices belonging to the customer."""
    customer_ids = select(Customer.id).where(
        (Customer.phone == user.phone) | (Customer.email == user.email)
    )
    result = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.items))
        .where(
            Invoice.type == "SALE",
            (Invoice.customer_id == user.id) | (Invoice.customer_id.in_(customer_ids)),
        )
    )
    return list(result.scalars().all())


@router.get("/invoices/{invoice_id}", response_model=InvoiceRead)
async def get_invoice(invoice_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    owned_businesses = select(Business.id).where(Business.owner_id == user.id)
    result = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.items))
        .where(Invoice.id == invoice_id, Invoice.business_id.in_(owned_businesses))
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


@router.patch("/invoices/{invoice_id}/status", response_model=InvoiceRead)
async def update_invoice_status(
    invoice_id: str,
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
    await db.commit()
    await db.refresh(invoice)
    return invoice


@router.get("/dashboard/store")
async def store_dashboard(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    owned_businesses = select(Business.id).where(Business.owner_id == user.id)
    total_revenue = await db.execute(
        select(func.coalesce(func.sum(Invoice.paid_amount), 0)).where(
            Invoice.type == "SALE", Invoice.business_id.in_(owned_businesses)
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
        .where(Invoice.type == "SALE", Product.business_id.in_(owned_businesses))
        .group_by(Product.id, Product.name)
        .order_by(func.sum(InvoiceItem.line_total).desc())
        .limit(5)
    )
    top_products = [{"name": row[0], "sales": float(row[1])} for row in top_res.all()]

    return {
        "todayRevenue": float(total_revenue.scalar_one()),
        "totalCustomers": int(customers.scalar_one()),
        "lowStockItems": int(low_stock.scalar_one()),
        "pendingInvoices": int(pending.scalar_one()),
        "topProducts": top_products,
        "recentTransactions": [
            {
                "invoice_number": inv.invoice_number,
                "total_amount": float(inv.total_amount),
                "status": inv.status,
                "created_at": inv.created_at.isoformat() if inv.created_at else "",
            }
            for inv in recent_invoices
        ],
        "revenueSeries": [],
    }


@router.get("/dashboard/customer/me", response_model=SpendingSummary)
async def customer_dashboard_me(user: User = Depends(get_current_user)):
    return SpendingSummary(customer_id=user.id, summary={})


@router.get("/dashboard/customer/{customer_id}", response_model=SpendingSummary)
async def customer_dashboard(customer_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role == "CUSTOMER" and user.id != customer_id:
        raise HTTPException(status_code=403, detail="Not authorized to view another customer's dashboard")
    return SpendingSummary(customer_id=customer_id, summary={classify_transaction(Invoice(invoice_number="general")): {"general": 0.0}})