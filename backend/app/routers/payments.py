import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cores.database import get_db
from app.models.business import Business
from app.models.transaction import Invoice
from app.models.user import User
from app.schemas.payment import (
    PaymentInfoResponse,
    PaymentOrderCreate,
    PaymentOrderResponse,
    PaymentVerifyRequest,
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

    invoice.pending_order_id = order["order_id"]
    invoice.pending_order_amount = amount_to_pay
    await db.commit()

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
    Connects to the payment gateway API to fetch sanitized information
    about a specific transaction (status, payment method, masked VPA/contact).
    """
    from app.services.encryption import mask_email, mask_phone

    try:
        info = await payment_service.get_payment_info(payment_id)
        return PaymentInfoResponse(
            payment_id=info["payment_id"],
            order_id=info.get("order_id"),
            amount=info["amount"],
            currency=info.get("currency", "INR"),
            status=info["status"],
            method=info.get("method"),
            vpa=mask_email(info["vpa"]) if info.get("vpa") else None,
            email=mask_email(info["email"]) if info.get("email") else None,
            contact=mask_phone(info["contact"]) if info.get("contact") else None,
            created_at=info.get("created_at"),
        )
    except (RuntimeError, ValueError, KeyError) as e:
        raise HTTPException(status_code=502, detail=f"Failed to retrieve payment information: {e!s}") from e


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

    order_meta = payment_service.get_order_meta(payload.order_id)
    if order_meta and order_meta.get("invoice_id") and str(order_meta["invoice_id"]) != str(payload.invoice_id):
        raise HTTPException(status_code=400, detail="Payment order does not match invoice")

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

    if invoice.pending_order_id and invoice.pending_order_id != payload.order_id:
        raise HTTPException(status_code=400, detail="Payment order does not match invoice pending order")

    # Fetch method info if available
    try:
        payment_info = await payment_service.get_payment_info(payload.payment_id)
        raw_method = payment_info.get("method", "UPI").upper()
        method_map = {"UPI": "UPI", "CARD": "CARD", "NETBANKING": "CARD", "WALLET": "UPI"}
        invoice.payment_method = method_map.get(raw_method, "UPI")
    except (RuntimeError, ValueError, KeyError):
        invoice.payment_method = "UPI"

    if invoice.pending_order_amount is not None:
        settled_amount = float(invoice.pending_order_amount)
    elif order_meta and "amount" in order_meta:
        settled_amount = float(order_meta["amount"])
    else:
        settled_amount = float(invoice.total_amount - invoice.paid_amount)

    new_paid = min(float(invoice.total_amount), float(invoice.paid_amount) + max(0.0, settled_amount))
    invoice.paid_amount = new_paid
    invoice.pending_order_id = None
    invoice.pending_order_amount = None
    if new_paid >= float(invoice.total_amount):
        invoice.status = "PAID"
    else:
        invoice.status = "CONFIRMED"

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

    if not payment_service.verify_webhook_signature(body_bytes, x_razorpay_signature):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing or invalid webhook signature",
        )

    try:
        data = json.loads(body_bytes.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    event = data.get("event", "")
    # Check for successful capture
    if event in ("payment.captured", "order.paid") or data.get("status") == "success":
        payment_obj = data.get("payload", {}).get("payment", {}).get("entity", {})
        notes = payment_obj.get("notes", {})
        invoice_id_str = notes.get("invoice_id")
        order_id = payment_obj.get("order_id")

        if order_id:
            order_meta = payment_service.get_order_meta(order_id)
            if order_meta and order_meta.get("invoice_id") and str(order_meta["invoice_id"]) != str(invoice_id_str):
                raise HTTPException(status_code=400, detail="Order invoice mismatch")

        if invoice_id_str:
            res = await db.execute(select(Invoice).where(Invoice.id == invoice_id_str))
            invoice = res.scalar_one_or_none()
            if invoice and hasattr(invoice, "total_amount"):
                if order_id and getattr(invoice, "pending_order_id", None) and invoice.pending_order_id != order_id:
                    raise HTTPException(status_code=400, detail="Order invoice mismatch")

                raw_amount_paise = payment_obj.get("amount")
                if getattr(invoice, "pending_order_amount", None) is not None:
                    settled = float(invoice.pending_order_amount)
                elif raw_amount_paise is not None:
                    settled = float(raw_amount_paise) / 100.0
                else:
                    settled = float(invoice.total_amount) - float(getattr(invoice, "paid_amount", 0.0) or 0.0)

                current_paid = float(getattr(invoice, "paid_amount", 0.0) or 0.0)
                new_paid = min(float(invoice.total_amount), current_paid + max(0.0, settled))
                invoice.paid_amount = new_paid
                invoice.status = "PAID" if new_paid >= float(invoice.total_amount) else "CONFIRMED"
                invoice.payment_method = "UPI"
                invoice.pending_order_id = None
                invoice.pending_order_amount = None
                await db.commit()

    return {"status": "success", "received": True}
