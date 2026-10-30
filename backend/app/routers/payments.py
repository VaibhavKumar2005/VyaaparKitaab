import json
import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cores.database import get_db
from app.models.banking_consent import PaymentWebhookEvent
from app.models.business import Business
from app.models.payment import Payment
from app.models.transaction import Invoice
from app.models.user import User
from app.schemas.payment import (
    PaymentInfoResponse,
    PaymentOrderCreate,
    PaymentOrderResponse,
    PaymentVerifyRequest,
)
from app.services.auth import get_current_user
from app.services.customer_link import invoice_access_clause
from app.services.payment import payment_service
from app.services.payment_recorder import detect_upi_app, record_payment

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/create-order", response_model=PaymentOrderResponse)
async def create_payment_order(
    payload: PaymentOrderCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Verify invoice exists and user has access to it
    res = await db.execute(
        select(Invoice).where(
            Invoice.id == payload.invoice_id,
            invoice_access_clause(user),
        )
    )
    invoice = res.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found or access denied")

    # Determine amount
    amount_to_pay = (
        payload.amount
        if payload.amount is not None
        else float(invoice.total_amount - invoice.paid_amount)
    )
    if amount_to_pay <= 0:
        raise HTTPException(status_code=400, detail="Invoice is already fully paid")

    order = await payment_service.create_order(
        amount=amount_to_pay,
        currency="INR",
        receipt=invoice.invoice_number,
        notes={
            "invoice_id": str(invoice.id),
            "invoice_number": invoice.invoice_number,
            "store_id": str(invoice.business_id),
            "customer_id": str(invoice.customer_id) if invoice.customer_id else "",
        },
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
        raise HTTPException(
            status_code=502, detail=f"Failed to retrieve payment information: {e!s}"
        ) from e


@router.post("/verify")
async def verify_payment(
    payload: PaymentVerifyRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Verifies payment signature from checkout and atomically records the payment.
    Calls record_payment to guarantee single-writer idempotency (no double-count with webhook).
    """
    is_valid = payment_service.verify_payment_signature(
        order_id=payload.order_id,
        payment_id=payload.payment_id,
        signature=payload.signature,
    )
    if not is_valid:
        raise HTTPException(status_code=400, detail="Invalid payment signature")

    order_meta = payment_service.get_order_meta(payload.order_id)
    if (
        order_meta
        and order_meta.get("invoice_id")
        and str(order_meta["invoice_id"]) != str(payload.invoice_id)
    ):
        raise HTTPException(status_code=400, detail="Payment order does not match invoice")

    # Retrieve invoice
    res = await db.execute(
        select(Invoice).where(
            Invoice.id == payload.invoice_id,
            invoice_access_clause(user),
        )
    )
    invoice = res.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.pending_order_id and invoice.pending_order_id != payload.order_id:
        raise HTTPException(
            status_code=400, detail="Payment order does not match invoice pending order"
        )

    # Fetch method & VPA info if available
    vpa = None
    raw_method = "UPI"
    raw_info: dict | None = None
    try:
        payment_info = await payment_service.get_payment_info(payload.payment_id)
        raw_info = payment_info
        raw_method = payment_info.get("method", "UPI").upper()
        vpa = payment_info.get("vpa")
    except (RuntimeError, ValueError, KeyError):
        raw_method = "UPI"

    # Determine exact settled amount
    if invoice.pending_order_amount is not None:
        settled_amount = float(invoice.pending_order_amount)
    elif raw_info and "amount" in raw_info and float(raw_info["amount"]) > 0:
        settled_amount = float(raw_info["amount"])
    elif order_meta and "amount" in order_meta:
        settled_amount = float(order_meta["amount"])
    else:
        settled_amount = float(invoice.total_amount - invoice.paid_amount)

    # Atomically record payment (single writer, ON CONFLICT DO NOTHING)
    record_result = await record_payment(
        db,
        {
            "payment_id": payload.payment_id,
            "order_id": payload.order_id,
            "invoice_id": invoice.id,
            "business_id": invoice.business_id,
            "customer_id": invoice.customer_id,
            "amount": settled_amount,
            "currency": "INR",
            "method": raw_method,
            "vpa": vpa,
            "status": "captured",
            "raw_response": raw_info,
        },
    )

    return {
        "success": True,
        "message": record_result["message"],
        "invoice_id": str(invoice.id),
        "invoice_status": record_result["invoice_status"],
        "paid_amount": record_result["paid_amount"],
        "app": record_result.get("app"),
        "duplicate_prevented": not record_result["inserted"],
    }


@router.post("/webhook")
async def payment_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_razorpay_signature: str | None = Header(default=None),
):
    """
    Server-to-server webhook endpoint for payment gateways (Razorpay).
    Verifies X-Razorpay-Signature HMAC-SHA256, provides idempotency via event_id,
    records payments via record_payment (single-writer model), and broadcasts
    to real-time streams via the event bus.
    """
    body_bytes = await request.body()
    body_text = body_bytes.decode("utf-8", errors="replace")

    if not payment_service.verify_webhook_signature(body_bytes, x_razorpay_signature):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing or invalid webhook signature",
        )

    try:
        data = json.loads(body_text)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    event = data.get("event", "")
    payload_obj = data.get("payload", {})
    payment_obj = (
        payload_obj.get("payment", {}).get("entity", {})
        if isinstance(payload_obj, dict)
        else {}
    )
    order_obj = (
        payload_obj.get("order", {}).get("entity", {})
        if isinstance(payload_obj, dict)
        else {}
    )

    # 1. Extract or determine event ID for idempotency
    event_id = (
        data.get("id")
        or data.get("event_id")
        or request.headers.get("x-razorpay-event-id")
        or (f"evt_{payment_obj.get('id')}_{event}" if payment_obj.get("id") else None)
        or (f"evt_{order_obj.get('id')}_{event}" if order_obj.get("id") else None)
        or f"evt_{uuid.uuid4().hex[:16]}"
    )

    # 2. Check webhook event table idempotency
    existing_res = await db.execute(
        select(PaymentWebhookEvent).where(PaymentWebhookEvent.event_id == event_id)
    )
    existing_evt = existing_res.scalar_one_or_none()
    if isinstance(existing_evt, PaymentWebhookEvent):
        return {
            "status": "skipped",
            "message": f"Duplicate event {event_id} skipped",
            "event_id": event_id,
            "received": True,
        }

    # 3. Extract invoice and order metadata
    notes = payment_obj.get("notes") or order_obj.get("notes") or {}
    invoice_id_str = notes.get("invoice_id")
    order_id = payment_obj.get("order_id") or order_obj.get("id")

    invoice: Invoice | None = None
    if order_id:
        order_meta = payment_service.get_order_meta(order_id)
        if (
            order_meta
            and order_meta.get("invoice_id")
            and invoice_id_str
            and str(order_meta["invoice_id"]) != str(invoice_id_str)
        ):
            raise HTTPException(status_code=400, detail="Order invoice mismatch")

    if invoice_id_str:
        res = await db.execute(select(Invoice).where(Invoice.id == invoice_id_str))
        invoice = res.scalar_one_or_none()

    raw_amount = payment_obj.get("amount") or order_obj.get("amount") or 0
    amount_in_rupees = float(raw_amount) / 100.0 if raw_amount else 0.0

    # 4. Handle events (payment.captured, payment.failed, order.paid)
    if event in ("payment.captured", "order.paid") or data.get("status") == "success":
        if invoice and hasattr(invoice, "total_amount"):
            if (
                order_id
                and getattr(invoice, "pending_order_id", None)
                and invoice.pending_order_id != order_id
            ):
                raise HTTPException(status_code=400, detail="Order invoice mismatch")

            payment_id = payment_obj.get("id") or f"pay_{event_id}"
            vpa = payment_obj.get("vpa")
            method = payment_obj.get("method", "UPI")

            settled = (
                amount_in_rupees
                if amount_in_rupees > 0
                else (
                    float(invoice.pending_order_amount)
                    if getattr(invoice, "pending_order_amount", None) is not None
                    else float(invoice.total_amount) - float(invoice.paid_amount or 0.0)
                )
            )

            # Record payment via unified single-writer
            await record_payment(
                db,
                {
                    "payment_id": payment_id,
                    "order_id": order_id,
                    "invoice_id": invoice.id,
                    "business_id": invoice.business_id,
                    "customer_id": invoice.customer_id,
                    "amount": settled,
                    "currency": payment_obj.get("currency") or "INR",
                    "method": method,
                    "vpa": vpa,
                    "status": "captured",
                    "raw_response": payment_obj,
                },
            )

    elif event == "payment.failed" and invoice and getattr(invoice, "status", None) != "PAID":
        invoice.pending_order_id = None
        invoice.pending_order_amount = None
        await db.commit()

    # 5. Persist webhook event for audit trail
    webhook_record = PaymentWebhookEvent(
        event_id=event_id,
        event_type=event or "unknown",
        payload=body_text,
        status="PROCESSED",
    )
    if hasattr(db, "add"):
        db.add(webhook_record)
    if hasattr(db, "commit"):
        await db.commit()

    logger.info("Webhook processed event_id=%s, amount=%s", event_id, amount_in_rupees)

    return {
        "status": "success",
        "event_id": event_id,
        "event": event,
        "received": True,
    }


@router.get("/summary")
async def get_payments_summary(
    period: str = "30d",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Returns store payment analytics grouped by day and UPI/payment app (Google Pay, PhonePe, Paytm, etc.).
    Scoped to Business.owner_id == user.id.
    """
    owned_businesses = (
        await db.execute(select(Business.id).where(Business.owner_id == user.id))
    ).scalars().all()

    if not owned_businesses:
        return {
            "period": period,
            "total_collected": 0.0,
            "total_transactions": 0,
            "by_app": [],
            "by_method": [],
            "daily_series": [],
            "recent_payments": [],
        }

    now = datetime.now(UTC)
    days = 30
    if period == "7d":
        days = 7
    elif period == "90d":
        days = 90
    elif period == "all":
        days = 3650
    cutoff = now - timedelta(days=days)

    stmt = (
        select(Payment)
        .where(
            Payment.business_id.in_(owned_businesses),
            Payment.status == "captured",
            Payment.created_at >= cutoff,
        )
        .order_by(Payment.created_at.asc())
    )
    res = await db.execute(stmt)
    payments = res.scalars().all()

    total_collected = sum(p.amount for p in payments)
    total_txns = len(payments)

    app_totals: dict[str, dict] = {}
    method_totals: dict[str, dict] = {}
    daily_map: dict[str, dict] = {}

    for p in payments:
        app_name = p.app or detect_upi_app(p.vpa, p.method)
        method_name = p.method or "UPI"
        date_str = p.created_at.strftime("%Y-%m-%d")

        if app_name not in app_totals:
            app_totals[app_name] = {"app": app_name, "amount": 0.0, "count": 0}
        app_totals[app_name]["amount"] += p.amount
        app_totals[app_name]["count"] += 1

        if method_name not in method_totals:
            method_totals[method_name] = {"method": method_name, "amount": 0.0, "count": 0}
        method_totals[method_name]["amount"] += p.amount
        method_totals[method_name]["count"] += 1

        if date_str not in daily_map:
            daily_map[date_str] = {
                "date": date_str,
                "total": 0.0,
                "google_pay": 0.0,
                "phonepe": 0.0,
                "paytm": 0.0,
                "other": 0.0,
                "count": 0,
            }
        daily_map[date_str]["total"] += p.amount
        daily_map[date_str]["count"] += 1
        if app_name == "Google Pay":
            daily_map[date_str]["google_pay"] += p.amount
        elif app_name == "PhonePe":
            daily_map[date_str]["phonepe"] += p.amount
        elif app_name == "Paytm":
            daily_map[date_str]["paytm"] += p.amount
        else:
            daily_map[date_str]["other"] += p.amount

    by_app = [
        {
            "app": k,
            "amount": round(v["amount"], 2),
            "count": v["count"],
            "percentage": round((v["amount"] / total_collected) * 100, 1) if total_collected > 0 else 0.0,
        }
        for k, v in sorted(app_totals.items(), key=lambda item: item[1]["amount"], reverse=True)
    ]

    by_method = [
        {
            "method": k,
            "amount": round(v["amount"], 2),
            "count": v["count"],
            "percentage": round((v["amount"] / total_collected) * 100, 1) if total_collected > 0 else 0.0,
        }
        for k, v in sorted(method_totals.items(), key=lambda item: item[1]["amount"], reverse=True)
    ]

    daily_series = sorted(daily_map.values(), key=lambda d: d["date"])

    recent_stmt = (
        select(Payment)
        .where(Payment.business_id.in_(owned_businesses))
        .order_by(Payment.created_at.desc())
        .limit(10)
    )
    recent_res = await db.execute(recent_stmt)
    recent_payments = [
        {
            "id": str(p.id),
            "payment_id": p.payment_id,
            "amount": p.amount,
            "app": p.app or detect_upi_app(p.vpa, p.method),
            "method": p.method,
            "vpa": p.vpa,
            "invoice_id": str(p.invoice_id),
            "status": p.status,
            "created_at": p.created_at.isoformat(),
        }
        for p in recent_res.scalars().all()
    ]

    return {
        "period": period,
        "total_collected": round(total_collected, 2),
        "total_transactions": total_txns,
        "by_app": by_app,
        "by_method": by_method,
        "daily_series": daily_series,
        "recent_payments": recent_payments,
    }
