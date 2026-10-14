from fastapi import APIRouter, Depends, HTTPException, Request, Header, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import json

from app.cores.database import get_db
from app.models.business import Business
from app.models.transaction import Invoice
from app.models.user import User
from app.schemas.payment import (
    PaymentOrderCreate,
    PaymentOrderResponse,
    PaymentVerifyRequest,
    PaymentInfoResponse,
)
from app.services.auth import get_current_user
from app.services.payment import payment_service

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/create-order", response_model=PaymentOrderResponse)
async def create_payment_order(
    payload: PaymentOrderCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Verify invoice exists and user has access to it
    owned_businesses = select(Business.id).where(Business.owner_id == user.id)
    res = await db.execute(
        select(Invoice).where(
            Invoice.id == payload.invoice_id,
            (Invoice.business_id.in_(owned_businesses) | (Invoice.customer_id == user.id)),
        )
    )
    invoice = res.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found or access denied")

    # Determine amount
    amount_to_pay = payload.amount if payload.amount is not None else float(invoice.total_amount - invoice.paid_amount)
    if amount_to_pay <= 0:
        raise HTTPException(status_code=400, detail="Invoice is already fully paid")

    order = await payment_service.create_order(
        amount=amount_to_pay,
        currency="INR",
        receipt=invoice.invoice_number,
        notes={"invoice_id": str(invoice.id), "invoice_number": invoice.invoice_number},
    )

    return PaymentOrderResponse(
        order_id=order["order_id"],
        amount=order["amount"],
        currency=order["currency"],
        receipt=order["receipt"],
        key_id=order["key_id"],
        gateway=order["gateway"],
        upi_intent=order.get("upi_intent"),
    )


@router.get("/info/{payment_id}", response_model=PaymentInfoResponse)
async def get_payment_info(
    payment_id: str,
    _: User = Depends(get_current_user),
):
    """
    Connects to the payment gateway API to fetch detailed information
    about a specific transaction (status, payment method, VPA, fees, timestamp).
    """
    try:
        info = await payment_service.get_payment_info(payment_id)
        return PaymentInfoResponse(**info)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to retrieve payment information: {str(e)}")


@router.post("/verify")
async def verify_payment(
    payload: PaymentVerifyRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Verifies payment signature from checkout and updates invoice status to PAID.
    """
    is_valid = payment_service.verify_payment_signature(
        order_id=payload.order_id,
        payment_id=payload.payment_id,
        signature=payload.signature,
    )
    if not is_valid:
        raise HTTPException(status_code=400, detail="Invalid payment signature")

    # Retrieve invoice
    owned_businesses = select(Business.id).where(Business.owner_id == user.id)
    res = await db.execute(
        select(Invoice).where(
            Invoice.id == payload.invoice_id,
            (Invoice.business_id.in_(owned_businesses) | (Invoice.customer_id == user.id)),
        )
    )
    invoice = res.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Fetch method info if available
    try:
        payment_info = await payment_service.get_payment_info(payload.payment_id)
        raw_method = payment_info.get("method", "UPI").upper()
        method_map = {"UPI": "UPI", "CARD": "CARD", "NETBANKING": "CARD", "WALLET": "UPI"}
        invoice.payment_method = method_map.get(raw_method, "UPI")
    except Exception:
        invoice.payment_method = "UPI"

    invoice.status = "PAID"
    invoice.paid_amount = invoice.total_amount
    await db.commit()
    await db.refresh(invoice)

    return {
        "success": True,
        "message": "Payment verified successfully",
        "invoice_id": str(invoice.id),
        "invoice_status": invoice.status,
    }


@router.post("/webhook")
async def payment_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_razorpay_signature: str | None = Header(default=None),
):
    """
    Server-to-server webhook endpoint for payment gateways to notify when
    a payment succeeds or fails asynchronously.
    """
    body_bytes = await request.body()

    if x_razorpay_signature:
        valid = payment_service.verify_webhook_signature(body_bytes, x_razorpay_signature)
        if not valid:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook signature")

    try:
        data = json.loads(body_bytes.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event = data.get("event", "")
    # Check for successful capture
    if event in ("payment.captured", "order.paid") or data.get("status") == "success":
        payment_obj = data.get("payload", {}).get("payment", {}).get("entity", {})
        notes = payment_obj.get("notes", {})
        invoice_id_str = notes.get("invoice_id")

        if invoice_id_str:
            res = await db.execute(select(Invoice).where(Invoice.id == invoice_id_str))
            invoice = res.scalar_one_or_none()
            if invoice and hasattr(invoice, "total_amount"):
                invoice.status = "PAID"
                invoice.paid_amount = invoice.total_amount
                invoice.payment_method = "UPI"
                await db.commit()

    return {"status": "success", "received": True}
