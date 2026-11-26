import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.cores.money import ZERO, money_to_float, to_money
from app.models.payment import Payment
from app.models.transaction import Invoice
from app.services.event_bus import publish_event
from app.services.notifications import resolve_linked_customer_user
from app.services.unified_ledger import sync_invoice_to_unified

logger = logging.getLogger(__name__)


class OverpaymentError(ValueError):
    """Raised when a payment would push an invoice's paid_amount above total_amount."""


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
    amount_dec = to_money(payment_data.get("amount", ZERO))
    if amount_dec <= ZERO:
        raise ValueError("Payment amount must be positive")
    currency = payment_data.get("currency", "INR")
    method = (payment_data.get("method") or "UPI").upper()
    vpa = payment_data.get("vpa")
    status = payment_data.get("status", "captured")
    raw_response = payment_data.get("raw_response")

    app = detect_upi_app(vpa, method)

    # 1. Acquire exclusive row lock on target invoice (prevents concurrent overpayment races)
    inv_stmt = (
        select(Invoice)
        .where(Invoice.id == invoice_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    res = await db.execute(inv_stmt)
    invoice = res.scalar_one_or_none()
    if not invoice:
        raise ValueError(f"Invoice not found: {invoice_id}")

    business_id = payment_data.get("business_id") or invoice.business_id
    customer_id = payment_data.get("customer_id") or invoice.customer_id

    raw_text = (
        json.dumps(raw_response, default=str)
        if isinstance(raw_response, dict)
        else (str(raw_response) if raw_response else None)
    )

    # 2. Atomic upsert with ON CONFLICT DO NOTHING (idempotent replay detection)
    stmt = (
        insert(Payment)
        .values(
            payment_id=payment_id,
            order_id=order_id,
            business_id=UUID(str(business_id)) if isinstance(business_id, str) else business_id,
            invoice_id=invoice.id,
            customer_id=UUID(str(customer_id)) if isinstance(customer_id, str) and customer_id else customer_id,
            amount=amount_dec,
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
            "paid_amount": money_to_float(invoice.paid_amount or ZERO),
            "invoice_status": invoice.status,
            "app": app,
            "message": "Payment already recorded (duplicate skipped)",
        }

    # 4. Enforce exact Decimal overpayment guard while holding the FOR UPDATE lock
    current_paid = to_money(invoice.paid_amount or ZERO)
    total_dec = to_money(invoice.total_amount or ZERO)
    new_paid = current_paid + amount_dec
    if new_paid > total_dec:
        if hasattr(db, "rollback"):
            await db.rollback()
        raise OverpaymentError(
            f"Overpayment rejected: {new_paid} exceeds invoice total {total_dec}"
        )

    invoice.paid_amount = new_paid

    if new_paid >= total_dec:
        invoice.status = "PAID"
    else:
        invoice.status = "CONFIRMED"

    invoice.payment_method = method if method in ("UPI", "CARD", "CASH") else "UPI"
    invoice.pending_order_id = None
    invoice.pending_order_amount = None

    # 4b. Sync canonical unified ledger + persist customer purchase notification
    sse_customer_id = str(customer_id) if customer_id else None
    if isinstance(db, AsyncSession):
        await sync_invoice_to_unified(
            db,
            invoice,
            app_name=app,
            notify=True,
            event_type="purchase.recorded",
            event_key=f"pay:{payment_id}",
            commit=False,
        )
        linked_user = await resolve_linked_customer_user(
            db, UUID(str(customer_id)) if isinstance(customer_id, str) and customer_id else customer_id
        )
        if linked_user is not None:
            sse_customer_id = str(linked_user.id)

    await db.commit()
    await db.refresh(invoice)

    amount_num = money_to_float(amount_dec)
    new_paid_num = money_to_float(new_paid)

    # 5. Broadcast to real-time SSE event bus
    event_payload = {
        "event": "payment.captured",
        "payment_id": payment_id,
        "order_id": order_id,
        "invoice_id": str(invoice.id),
        "amount": amount_num,
        "currency": currency,
        "method": method,
        "vpa": vpa,
        "app": app,
        "store_id": str(business_id),
        "customer_id": sse_customer_id,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    await publish_event(
        event_type="payment.captured",
        data=event_payload,
        store_id=str(business_id),
        customer_id=sse_customer_id,
        event_id=f"evt_{payment_id}",
    )

    logger.info(
        "Recorded payment %s: amount=%s, app=%s, invoice_id=%s, new_paid=%s",
        payment_id,
        amount_dec,
        app,
        invoice.id,
        new_paid,
    )

    return {
        "inserted": True,
        "payment_record_id": str(inserted_id),
        "payment_id": payment_id,
        "invoice_id": str(invoice.id),
        "paid_amount": new_paid_num,
        "invoice_status": invoice.status,
        "app": app,
        "message": "Payment recorded successfully",
    }

