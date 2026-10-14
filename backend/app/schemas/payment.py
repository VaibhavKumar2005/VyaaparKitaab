from uuid import UUID
from typing import Any
from pydantic import BaseModel, Field


class PaymentOrderCreate(BaseModel):
    invoice_id: UUID
    amount: float | None = None


class PaymentOrderResponse(BaseModel):
    order_id: str
    amount: float
    currency: str
    receipt: str
    key_id: str
    gateway: str
    upi_intent: str | None = None


class PaymentVerifyRequest(BaseModel):
    invoice_id: UUID
    order_id: str
    payment_id: str
    signature: str


class PaymentInfoResponse(BaseModel):
    payment_id: str
    order_id: str | None = None
    amount: float
    currency: str = "INR"
    status: str
    method: str | None = None
    vpa: str | None = None
    email: str | None = None
    contact: str | None = None
    created_at: int | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

