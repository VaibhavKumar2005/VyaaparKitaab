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
    gst_rate: float | None = Field(default=None, ge=0.0, le=0.28)
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
    subtotal: float
    tax_amount: float
    discount_amount: float
    total_amount: float
    paid_amount: float
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
    amount: float
    paid_amount: float
    discount_amount: float
    tax_amount: float
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
    total_amount: float
    total_discount_saved: float
    total_debits: float
    total_credits: float
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
    amount: float
    discount_amount: float
    category: str
    subcategory: str
    payment_channel: str | None = None
    is_read: bool
    created_at: str
