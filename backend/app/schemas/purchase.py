from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PurchaseCreate(BaseModel):
    marketplace: str = Field(..., min_length=1, max_length=100, description="Marketplace name, e.g. Amazon, Flipkart")
    category: str = Field(default="Shopping", max_length=100)
    amount: float = Field(..., gt=0, description="Total cost incurred in INR")
    currency: str = Field(default="INR", max_length=10)
    purchased_at: datetime = Field(default_factory=datetime.utcnow)
    order_id: str = Field(..., min_length=1, max_length=255, description="Marketplace Order ID, encrypted at rest")
    items_note: str | None = Field(default=None, max_length=1024, description="Purchased items note, encrypted at rest")
    payment_method: str | None = Field(default="UPI (Google Pay)", max_length=50)


class PurchaseRead(BaseModel):
    id: UUID
    marketplace: str
    category: str
    amount: float
    currency: str
    purchased_at: datetime
    order_id: str
    items_note: str | None = None
    payment_method: str | None = None
    created_at: datetime
    is_encrypted: bool = True

    model_config = {"from_attributes": True}


class DailySpendingItem(BaseModel):
    date: str
    total_cost: float
    order_count: int
    marketplaces: list[str]


class MarketplaceBreakdownItem(BaseModel):
    marketplace: str
    total_cost: float
    percentage: float
    order_count: int


class CategoryBreakdownItem(BaseModel):
    category: str
    total_cost: float
    percentage: float


class PersonalSpendingAnalytics(BaseModel):
    today_cost: float
    week_cost: float
    month_cost: float
    total_orders: int
    daily_trend: list[DailySpendingItem]
    marketplace_breakdown: list[MarketplaceBreakdownItem]
    category_breakdown: list[CategoryBreakdownItem]
    recent_purchases: list[PurchaseRead]


class ParseInvoiceTextRequest(BaseModel):
    invoice_text: str = Field(..., min_length=5, description="Raw text copied from Amazon/Flipkart invoice or order email")


class ParsedInvoiceResponse(BaseModel):
    marketplace: str
    order_id: str | None = None
    amount: float | None = None
    purchased_at: datetime | None = None
    items_summary: str | None = None
    confidence: str = "HIGH"


class TransactionGraphNode(BaseModel):
    id: str
    label: str
    type: str  # "SOURCE", "GATEWAY", "MERCHANT"
    subtext: str
    total_volume: float = 0.0
    order_count: int = 0


class TransactionGraphEdge(BaseModel):
    from_node: str
    to_node: str
    amount: float
    order_count: int = 1
    status: str = "CONFIRMED"


class TransactionGraphResponse(BaseModel):
    nodes: list[TransactionGraphNode]
    edges: list[TransactionGraphEdge]
    total_routed_volume: float
    currency: str = "INR"


class PayeeSummaryItem(BaseModel):
    payee_name: str
    payee_type: str
    total_paid: float
    share_percentage: float
    payment_count: int
    avg_payment: float
    last_paid_at: str
    primary_channel: str
    recency_days: float
    ml_cluster_label: str = "Regular Payee"
    pca_x: float = 0.0
    pca_y: float = 0.0


class PaymentChannelSummaryItem(BaseModel):
    channel: str
    total_paid: float
    percentage: float
    transaction_count: int


class PaymentAnomalyItem(BaseModel):
    payee_name: str
    amount: float
    paid_at: str
    channel: str
    note: str


class OutgoingPaymentsSummaryResponse(BaseModel):
    total_paid_to_others: float
    total_transactions: int
    unique_payees_count: int
    top_payee_name: str
    top_payee_amount: float
    predicted_7d_outflow: float
    predicted_30d_outflow: float
    ai_summary_text: str
    ml_models_used: dict[str, object]
    payee_summary: list[PayeeSummaryItem]
    payment_app_summary: list[PaymentChannelSummaryItem]
    anomalies: list[PaymentAnomalyItem]


class StoreOptionItem(BaseModel):
    store_name: str
    store_type: str
    total_spent: float
    transaction_count: int
    last_tx_at: str


class StoreTransactionPoint(BaseModel):
    id: str
    date: str
    paid_at: str
    amount: float
    cumulative_amount: float
    order_id: str
    items_note: str
    payment_method: str
    category: str


class StoreMethodSplitItem(BaseModel):
    method: str
    amount: float
    percentage: float
    count: int


class StoreCategorySplitItem(BaseModel):
    category: str
    amount: float
    percentage: float
    count: int


class StoreDrilldownResponse(BaseModel):
    selected_store: str
    store_type: str
    total_spent: float
    share_of_wallet_pct: float
    transaction_count: int
    avg_order_value: float
    max_order_value: float
    min_order_value: float
    predicted_next_order: float
    available_stores: list[StoreOptionItem]
    transactions_timeline: list[StoreTransactionPoint]
    payment_method_split: list[StoreMethodSplitItem]
    category_split: list[StoreCategorySplitItem]
    store_flow_nodes: list[TransactionGraphNode]
    store_flow_edges: list[TransactionGraphEdge]



