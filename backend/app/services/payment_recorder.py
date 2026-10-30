import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import Payment
from app.models.transaction import Invoice
from app.services.event_bus import publish_event

logger = logging.getLogger(__name__)


def detect_upi_app(vpa: str | None, method: str | None = None) -> str:
    """
    Identifies consumer UPI app from VPA handle in one centralized place.
    Recognizes Google Pay (@okhdfcbank, @okaxis, @oksbi, @okicici),
    PhonePe (@ybl, @ibl, @axl), Paytm (@paytm, @ptyes, @pthdfc), etc.
    """
    if not vpa:
        if method and method.upper() == "CARD":
            return "Card"
        if method and method.upper() == "CASH":
            return "Cash"
        if method and method.upper() == "NETBANKING":
            return "NetBanking"
        return "UPI"

    handle = vpa.strip().lower()
    # Google Pay VPA handles
    if any(handle.endswith(suffix) for suffix in ("@okhdfcbank", "@okaxis", "@oksbi", "@okicici")):
        return "Google Pay"
    # PhonePe VPA handles
    if any(handle.endswith(suffix) for suffix in ("@ybl", "@ibl", "@axl")):
        return "PhonePe"
    # Paytm VPA handles
    if any(handle.endswith(suffix) for suffix in ("@paytm", "@ptyes", "@pthdfc", "@ptaxis")):
        return "Paytm"
    # BHIM UPI
    if handle.endswith("@upi"):
        return "BHIM UPI"
    # WhatsApp Pay
    if any(handle.endswith(suffix) for suffix in ("@waaxis", "@wahdfcbank", "@waicici", "@wasbi")):
        return "WhatsApp Pay"
    # Amazon Pay
    if any(handle.endswith(suffix) for suffix in ("@apl", "@rapl")):
        return "Amazon Pay"

    return "Other UPI"


async def record_payment(
    db: AsyncSession,
    payment_data: dict[str, Any],
) -> dict[str, Any]:
    """
    Single, unified writer for payments.
    Inserts a row with ON CONFLICT (payment_id) DO NOTHING, and updates the invoice
    ONLY when a new row was inserted. This prevents the double-count bug between
    checkout verify and webhooks, and makes webhook replays completely harmless.
    """
    payment_id = payment_data.get("payment_id")
    if not payment_id:
        raise ValueError("payment_id is required to record a payment")

    invoice_id = payment_data.get("invoice_id")
    if not invoice_id:
        raise ValueError("invoice_id is required to record a payment")

    order_id = payment_data.get("order_id")
    raw_amount = payment_data.get("amount", 0.0)
    amount = float(raw_amount)
    currency = payment_data.get("currency", "INR")
    method = (payment_data.get("method") or "UPI").upper()
    vpa = payment_data.get("vpa")
    status = payment_data.get("status", "captured")
    raw_response = payment_data.get("raw_response")

    app = detect_upi_app(vpa, method)

    # 1. Fetch target invoice
    res = await db.execute(select(Invoice).where(Invoice.id == invoice_id))
    invoice = res.scalar_one_or_none()
    if not invoice:
        raise ValueError(f"Invoice not found: {invoice_id}")

    business_id = payment_data.get("business_id") or invoice.business_id
    customer_id = payment_data.get("customer_id") or invoice.customer_id

    raw_text = (
        json.dumps(raw_response)
        if isinstance(raw_response, dict)
        else (str(raw_response) if raw_response else None)
    )

    # 2. Atomic upsert with ON CONFLICT DO NOTHING
    stmt = (
        insert(Payment)
        .values(
            payment_id=payment_id,
            order_id=order_id,
            business_id=UUID(str(business_id)) if isinstance(business_id, str) else business_id,
            invoice_id=invoice.id,
            customer_id=UUID(str(customer_id)) if isinstance(customer_id, str) and customer_id else customer_id,
            amount=amount,
            currency=currency,
            method=method,
            vpa=vpa,
            app=app,
            status=status,
            raw_response=raw_text,
        )
        .on_conflict_do_nothing(index_elements=[Payment.payment_id])
        .returning(Payment.id)
    )

    res = await db.execute(stmt)
    inserted_id = res.scalar_one_or_none()

    # 3. If no row was inserted, payment was ALREADY recorded (duplicate or verify-webhook race)
    if inserted_id is None:
        logger.info(
            "Payment %s already recorded in payments table, skipping invoice paid_amount update",
            payment_id,
        )
        return {
            "inserted": False,
            "payment_id": payment_id,
            "invoice_id": str(invoice.id),
            "paid_amount": float(invoice.paid_amount or 0.0),
            "invoice_status": invoice.status,
            "app": app,
            "message": "Payment already recorded (duplicate skipped)",
        }

    # 4. If row was inserted, update invoice paid_amount
    current_paid = float(invoice.paid_amount or 0.0)
    new_paid = min(float(invoice.total_amount), current_paid + max(0.0, amount))
    invoice.paid_amount = new_paid

    if new_paid >= float(invoice.total_amount):
        invoice.status = "PAID"
    else:
        invoice.status = "CONFIRMED"

    invoice.payment_method = method if method in ("UPI", "CARD", "CASH") else "UPI"
    invoice.pending_order_id = None
    invoice.pending_order_amount = None

    await db.commit()
    await db.refresh(invoice)

    # 5. Broadcast to real-time SSE event bus
    event_payload = {
        "event": "payment.captured",
        "payment_id": payment_id,
        "order_id": order_id,
        "invoice_id": str(invoice.id),
        "amount": amount,
        "currency": currency,
        "method": method,
        "vpa": vpa,
        "app": app,
        "store_id": str(business_id),
        "customer_id": str(customer_id) if customer_id else None,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    await publish_event(
        event_type="payment.captured",
        data=event_payload,
        store_id=str(business_id),
        customer_id=str(customer_id) if customer_id else None,
        event_id=f"evt_{payment_id}",
    )

    logger.info(
        "Recorded payment %s: amount=%.2f, app=%s, invoice_id=%s, new_paid=%.2f",
        payment_id,
        amount,
        app,
        invoice.id,
        new_paid,
    )

    return {
        "inserted": True,
        "payment_record_id": str(inserted_id),
        "payment_id": payment_id,
        "invoice_id": str(invoice.id),
        "paid_amount": new_paid,
        "invoice_status": invoice.status,
        "app": app,
        "message": "Payment recorded successfully",
    }

