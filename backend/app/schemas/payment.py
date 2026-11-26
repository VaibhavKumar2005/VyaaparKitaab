from uuid import UUID

from pydantic import BaseModel

from app.cores.money import Money, OptionalMoney


class PaymentOrderCreate(BaseModel):
    invoice_id: UUID
    amount: OptionalMoney = None


class PaymentOrderResponse(BaseModel):
    order_id: str
    amount: Money
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
    otp_code: str | None = None
    require_otp: bool = False


class PaymentInfoResponse(BaseModel):
    payment_id: str
    order_id: str | None = None
    amount: Money
    currency: str = "INR"
    status: str
    method: str | None = None
    vpa: str | None = None
    email: str | None = None
    contact: str | None = None
    created_at: int | None = None

