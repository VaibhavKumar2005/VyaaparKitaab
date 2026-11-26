from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.cores.money import Money


class InvoiceItemCreate(BaseModel):
    product_id: UUID
    quantity: Money
    unit_price: Money
    discount: Money = Decimal("0.00")


class InvoiceCreate(BaseModel):
    invoice_number: str
    business_id: UUID
    customer_id: UUID | None = None
    type: str = "SALE"
    status: str = "DRAFT"
    subtotal: Money = Decimal("0.00")
    tax_amount: Money = Decimal("0.00")
    gst_rate: float | None = Field(default=None, ge=0.0, le=0.28)
    discount_amount: Money = Decimal("0.00")
    total_amount: Money = Decimal("0.00")
    paid_amount: Money = Decimal("0.00")
    payment_method: str | None = None
    items: list[InvoiceItemCreate] = Field(default_factory=list)


class InvoiceItemRead(InvoiceItemCreate):
    id: UUID
    line_total: Money


class InvoiceRead(BaseModel):
    id: UUID
    invoice_number: str
    business_id: UUID
    customer_id: UUID | None
    type: str
    status: str
    subtotal: Money
    tax_amount: Money
    discount_amount: Money
    total_amount: Money
    paid_amount: Money
    payment_method: str | None
    created_at: datetime
    store_name: str | None = None
    store_gstin: str | None = None
    store_address: str | None = None
    store_phone: str | None = None
    store_upi_vpa: str | None = None
    items: list[InvoiceItemRead] = Field(default_factory=list)


class CustomerInvoiceRead(BaseModel):
    """Safe customer-facing invoice: only their retail bills and payment states."""
    id: UUID
    invoice_number: str
    business_id: UUID
    type: str
    status: str
    subtotal: Money
    tax_amount: Money
    discount_amount: Money
    total_amount: Money
    paid_amount: Money
    payment_method: str | None
    created_at: datetime
    store_name: str | None = None
    store_gstin: str | None = None
    store_address: str | None = None
    store_phone: str | None = None
    store_upi_vpa: str | None = None
    items: list[InvoiceItemRead] = Field(default_factory=list)


class SpendingSummary(BaseModel):
    customer_id: UUID
    from_date: date | None = None
    to_date: date | None = None
    summary: dict[str, dict[str, float]]


class CategoryTreeSubItem(BaseModel):
    subcategory: str
    total_amount: float
    count: int
    percentage: float


class CategoryTreeItem(BaseModel):
    category: str
    total_amount: float
    count: int
    percentage: float
    subcategories: list[CategoryTreeSubItem] = Field(default_factory=list)


class UnifiedTransactionRead(BaseModel):
    id: str
    source_type: str
    source_ref_id: str
    invoice_id: str | None = None
    business_id: str | None = None
    customer_id: str | None = None
    direction: str
    side: str
    amount: Money
    paid_amount: Money
    discount_amount: Money
    tax_amount: Money
    currency: str = "INR"
    status: str
    channel: str
    app: str | None = None
    counterparty: str
    narration: str
    category: str
    subcategory: str
    classification_source: str
    occurred_at: str


class UnifiedCategoryUpdate(BaseModel):
    category: str = Field(..., min_length=1, max_length=100)
    subcategory: str | None = Field(default=None, max_length=100)


class UnifiedTransactionFeedResponse(BaseModel):
    total_count: int
    total_amount: Money
    total_discount_saved: Money
    total_debits: Money
    total_credits: Money
    nested_summary: dict[str, dict[str, float]]
    category_tree: list[CategoryTreeItem] = Field(default_factory=list)
    items: list[UnifiedTransactionRead] = Field(default_factory=list)


class CustomerNotificationRead(BaseModel):
    id: str
    event_type: str
    invoice_id: str | None = None
    business_id: str | None = None
    store_name: str
    title: str
    message: str
    amount: Money
    discount_amount: Money
    category: str
    subcategory: str
    payment_channel: str | None = None
    is_read: bool
    created_at: str
