from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class InvoiceItemCreate(BaseModel):
    product_id: UUID
    quantity: float
    unit_price: float
    discount: float = 0


class InvoiceCreate(BaseModel):
    invoice_number: str
    business_id: UUID
    customer_id: UUID | None = None
    type: str = "SALE"
    status: str = "DRAFT"
    subtotal: float = 0
    tax_amount: float = 0
    discount_amount: float = 0
    total_amount: float = 0
    paid_amount: float = 0
    payment_method: str | None = None
    items: list[InvoiceItemCreate] = Field(default_factory=list)


class InvoiceItemRead(InvoiceItemCreate):
    id: UUID
    line_total: float


class InvoiceRead(BaseModel):
    id: UUID
    invoice_number: str
    business_id: UUID
    customer_id: UUID | None
    type: str
    status: str
    subtotal: float
    tax_amount: float
    discount_amount: float
    total_amount: float
    paid_amount: float
    payment_method: str | None
    created_at: datetime
    items: list[InvoiceItemRead] = Field(default_factory=list)


class CustomerInvoiceRead(BaseModel):
    """Safe customer-facing invoice: only their retail bills and payment states."""
    id: UUID
    invoice_number: str
    business_id: UUID
    type: str
    status: str
    subtotal: float
    tax_amount: float
    discount_amount: float
    total_amount: float
    paid_amount: float
    payment_method: str | None
    created_at: datetime
    items: list[InvoiceItemRead] = Field(default_factory=list)


class SpendingSummary(BaseModel):
    customer_id: UUID
    from_date: date | None = None
    to_date: date | None = None
    summary: dict[str, dict[str, float]]