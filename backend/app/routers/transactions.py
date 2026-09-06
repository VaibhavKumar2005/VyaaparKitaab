from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cores.database import get_db
from app.models.business import Customer, Product
from app.models.transaction import Invoice, InvoiceItem
from app.schemas.transaction import InvoiceCreate, InvoiceRead, SpendingSummary
from app.services.auth import get_current_user
from app.services.spending import classify_transaction

router = APIRouter(tags=["transactions"])


@router.post("/invoices", response_model=InvoiceRead)
async def create_invoice(payload: InvoiceCreate, db: AsyncSession = Depends(get_db), _: object = Depends(get_current_user)):
    invoice = Invoice(**payload.model_dump(exclude={"items"}))
    db.add(invoice)
    await db.flush()
    item_models = []
    for item in payload.items:
      line_total = (item.quantity * item.unit_price) - item.discount
      item_model = InvoiceItem(invoice_id=invoice.id, line_total=line_total, **item.model_dump())
      db.add(item_model)
      item_models.append(item_model)
    await db.commit()
    await db.refresh(invoice)
    invoice.items = item_models
    return invoice


@router.get("/invoices", response_model=list[InvoiceRead])
async def list_invoices(db: AsyncSession = Depends(get_db), _: object = Depends(get_current_user)):
    result = await db.execute(select(Invoice))
    return list(result.scalars().all())


@router.get("/invoices/{invoice_id}", response_model=InvoiceRead)
async def get_invoice(invoice_id: str, db: AsyncSession = Depends(get_db), _: object = Depends(get_current_user)):
    result = await db.execute(select(Invoice).where(Invoice.id == invoice_id))
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


@router.patch("/invoices/{invoice_id}/status", response_model=InvoiceRead)
async def update_invoice_status(invoice_id: str, status: str, db: AsyncSession = Depends(get_db), _: object = Depends(get_current_user)):
    result = await db.execute(select(Invoice).where(Invoice.id == invoice_id))
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    invoice.status = status
    await db.commit()
    await db.refresh(invoice)
    return invoice


@router.get("/dashboard/store")
async def store_dashboard(db: AsyncSession = Depends(get_db), _: object = Depends(get_current_user)):
    total_revenue = await db.execute(select(func.coalesce(func.sum(Invoice.total_amount), 0)).where(Invoice.type == "SALE"))
    pending = await db.execute(select(func.count()).select_from(Invoice).where(Invoice.status == "DRAFT"))
    low_stock = await db.execute(select(func.count()).select_from(Product).where(Product.stock_qty <= 5))
    customers = await db.execute(select(func.count()).select_from(Customer))
    return {
        "todayRevenue": float(total_revenue.scalar_one()),
        "totalCustomers": int(customers.scalar_one()),
        "lowStockItems": int(low_stock.scalar_one()),
        "pendingInvoices": int(pending.scalar_one()),
        "topProducts": [],
        "recentTransactions": [],
        "revenueSeries": [],
    }


@router.get("/dashboard/customer/{customer_id}", response_model=SpendingSummary)
async def customer_dashboard(customer_id: str, db: AsyncSession = Depends(get_db), _: object = Depends(get_current_user)):
    return SpendingSummary(customer_id=customer_id, summary={classify_transaction(Invoice(invoice_number="general")): {"general": 0.0}})