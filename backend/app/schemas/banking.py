from datetime import datetime

from pydantic import BaseModel, Field


class BankingConsentRequest(BaseModel):
    fip_id: str = Field(
        default="sbi_yono",
        description="Financial Information Provider (FIP) Bank ID, e.g. sbi_yono, hdfc_bank, icici_imobile, axis_bank, phonepe_aa",
    )
    phone: str = Field(
        default="9876543210",
        description="User mobile number linked to bank account for OTP/app authorization",
    )
    vua: str | None = Field(
        default=None,
        description="Virtual User Address handle (e.g. 9876543210@setu or user@phonepe)",
    )
    purpose_code: str = Field(
        default="102",
        description="Sahamati purpose code. 102 = Customer spending patterns, budget or income reporting",
    )
    fetch_type: str = Field(
        default="PERIODIC",
        description="Fetch frequency: ONE_TIME or PERIODIC",
    )
    data_life_months: int = Field(
        default=6,
        ge=1,
        le=36,
        description="Duration for which data can be analyzed (in months)",
    )


class BankingConsentResponse(BaseModel):
    consent_id: str
    fip_id: str
    fip_name: str
    status: str  # PENDING, APPROVED, REJECTED, REVOKED
    redirect_url: str
    purpose_text: str
    masked_acc: str
    fi_types: list[str]
    created_at: datetime
    expires_at: datetime
    security_guarantees: dict[str, str]


class ConsentAuthorizePayload(BaseModel):
    consent_id: str
    approve: bool = True
    fip_id: str | None = None


class IncomeTransactionItem(BaseModel):
    txn_id: str
    timestamp: str
    date: str
    amount: float
    mode: str  # UPI, IMPS, NEFT, RTGS
    type: str = "CREDIT"
    narration: str
    category: str  # Client UPI Receipt, Business Sales Settlement, Direct Deposit, Interest
    payer_identifier: str
    masked_acc: str


class MonthlyIncomePoint(BaseModel):
    month: str
    total_income: float
    transaction_count: int


class IncomeCategoryBreakdown(BaseModel):
    category: str
    total_amount: float
    percentage: float
    count: int


class IncomeStreamResponse(BaseModel):
    is_connected: bool
    active_consent: BankingConsentResponse | None = None
    total_inward_income: float
    total_credits_count: int
    avg_ticket_size: float
    monthly_trend: list[MonthlyIncomePoint]
    category_breakdown: list[IncomeCategoryBreakdown]
    recent_inflows: list[IncomeTransactionItem]
    security_metadata: dict[str, str]


class IncomeGraphNode(BaseModel):
    id: str
    label: str
    type: str  # SOURCE_BANK, AA_TUNNEL, INCOME_HUB, INFLOW_CATEGORY, RECEIPT_NODE
    subtext: str
    volume: float
    count: int = 1


class IncomeGraphEdge(BaseModel):
    from_node: str
    to_node: str
    amount: float
    label: str = "CREDIT"
    status: str = "VERIFIED_CREDIT"


class IncomeGraphResponse(BaseModel):
    nodes: list[IncomeGraphNode]
    edges: list[IncomeGraphEdge]
    total_inward_volume: float
    fip_name: str
    currency: str = "INR"
