import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.cores.config import settings
from app.cores.database import get_db
from app.cores.money import CENT, HUNDRED, ZERO, money_to_float, to_money
from app.models.banking_consent import BankTransaction, PaymentWebhookEvent
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
from app.services.auth import get_current_user, require_store_owner
from app.services.customer_link import invoice_access_clause
from app.services.otp import check_otp_code
from app.services.payment import payment_service
from app.services.payment_recorder import OverpaymentError, detect_upi_app, record_payment
from app.services.unified_ledger import sync_bank_rows_to_unified

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

    # Determine exact Decimal amount
    due_dec = to_money(invoice.total_amount) - to_money(invoice.paid_amount or ZERO)
    if due_dec <= ZERO:
        raise HTTPException(status_code=400, detail="Invoice is already fully paid")

    amount_to_pay = to_money(payload.amount) if payload.amount is not None else due_dec
    if amount_to_pay <= ZERO:
        raise HTTPException(status_code=400, detail="Payment order amount must be positive")
    if amount_to_pay > due_dec:
        raise HTTPException(status_code=400, detail="Order amount exceeds invoice balance due")

    biz = (await db.execute(select(Business).where(Business.id == invoice.business_id))).scalar_one_or_none()
    order = await payment_service.create_order(
        amount=amount_to_pay,
        currency="INR",
        receipt=invoice.invoice_number,
        payee_vpa=biz.upi_vpa if biz else None,
        payee_name=biz.name if biz else None,
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

    if payload.require_otp or (payload.otp_code is not None and payload.otp_code.strip() != ""):
        if not payload.otp_code or not payload.otp_code.strip():
            raise HTTPException(
                status_code=400, detail="Transaction OTP authorization code is required"
            )
        otp_identifier = (
            user.phone
            if getattr(user, "phone", None) and getattr(user, "phone_verified", False)
            else user.email
        )
        otp_valid = False
        if otp_identifier:
            otp_valid = await check_otp_code(
                db, otp_identifier, payload.otp_code.strip(), purpose="TRANSACTION"
            )
        if not otp_valid and getattr(user, "phone", None):
            otp_valid = await check_otp_code(
                db, user.phone, payload.otp_code.strip(), purpose="TRANSACTION"
            )
        if not otp_valid:
            raise HTTPException(
                status_code=400, detail="Invalid or expired transaction authorization OTP"
            )

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

    other_inv = (
        await db.execute(
            select(Invoice.id).where(
                Invoice.pending_order_id == payload.order_id,
                Invoice.id != invoice.id,
            )
        )
    ).scalar_one_or_none()
    if other_inv is not None:
        raise HTTPException(status_code=400, detail="Payment order belongs to another invoice")

    # Fetch & verify payment state from gateway
    vpa = None
    raw_method = "UPI"
    raw_info: dict | None = None
    live_gateway = (
        settings.PAYMENT_GATEWAY.strip().lower() == "razorpay"
        or settings.ENV.lower() not in ("development", "testing")
    )
    try:
        payment_info = await payment_service.get_payment_info(payload.payment_id)
        raw_info = {k: v for k, v in payment_info.items() if k != "raw"}
        raw_method = str(payment_info.get("method") or "UPI").upper()
        vpa = payment_info.get("vpa")
    except (RuntimeError, ValueError, KeyError, httpx.HTTPError) as exc:
        if live_gateway:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Unable to verify payment status with payment gateway",
            ) from exc
        raw_method = "UPI"
        payment_info = None

    if live_gateway:
        if not payment_info or str(payment_info.get("status") or "").lower() != "captured":
            raise HTTPException(status_code=400, detail="Payment is not captured at gateway")
        if str(payment_info.get("order_id") or "") != payload.order_id:
            raise HTTPException(status_code=400, detail="Gateway payment order ID mismatch")
        gw_currency = str(payment_info.get("currency") or "").upper()
        gw_amount = to_money(payment_info.get("amount") or ZERO)
        if gw_currency != "INR" or gw_amount <= ZERO:
            raise HTTPException(status_code=400, detail="Invalid gateway payment currency or amount")
        if (
            invoice.pending_order_amount is not None
            and abs(gw_amount - to_money(invoice.pending_order_amount)) > CENT
        ):
            raise HTTPException(
                status_code=400,
                detail="Gateway captured amount does not match invoice pending order amount",
            )
        settled_amount = gw_amount
    elif invoice.pending_order_amount is not None:
        settled_amount = to_money(invoice.pending_order_amount)
    elif raw_info and "amount" in raw_info and to_money(raw_info["amount"]) > ZERO:
        settled_amount = to_money(raw_info["amount"])
    elif order_meta and "amount" in order_meta:
        settled_amount = to_money(order_meta["amount"])
    else:
        settled_amount = to_money(invoice.total_amount) - to_money(invoice.paid_amount or ZERO)

    # Atomically record payment (single writer, ON CONFLICT DO NOTHING, FOR UPDATE lock)
    try:
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
    except (OverpaymentError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

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
    amount_in_rupees = (
        (Decimal(str(raw_amount)) / HUNDRED).quantize(CENT, rounding=ROUND_HALF_UP)
        if raw_amount
        else ZERO
    )

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
                if amount_in_rupees > ZERO
                else (
                    to_money(invoice.pending_order_amount)
                    if getattr(invoice, "pending_order_amount", None) is not None
                    else to_money(invoice.total_amount) - to_money(invoice.paid_amount or ZERO)
                )
            )

            # Record payment via unified single-writer
            try:
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
            except (OverpaymentError, ValueError) as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

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

    total_collected = sum((to_money(p.amount) for p in payments), ZERO)
    total_txns = len(payments)

    app_totals: dict[str, dict] = {}
    method_totals: dict[str, dict] = {}
    daily_map: dict[str, dict] = {}

    for p in payments:
        amt_dec = to_money(p.amount)
        app_name = p.app or detect_upi_app(p.vpa, p.method)
        method_name = p.method or "UPI"
        date_str = p.created_at.strftime("%Y-%m-%d")

        if app_name not in app_totals:
            app_totals[app_name] = {"app": app_name, "amount": ZERO, "count": 0}
        app_totals[app_name]["amount"] += amt_dec
        app_totals[app_name]["count"] += 1

        if method_name not in method_totals:
            method_totals[method_name] = {"method": method_name, "amount": ZERO, "count": 0}
        method_totals[method_name]["amount"] += amt_dec
        method_totals[method_name]["count"] += 1

        if date_str not in daily_map:
            daily_map[date_str] = {
                "date": date_str,
                "total": ZERO,
                "google_pay": ZERO,
                "phonepe": ZERO,
                "paytm": ZERO,
                "other": ZERO,
                "count": 0,
            }
        daily_map[date_str]["total"] += amt_dec
        daily_map[date_str]["count"] += 1
        if app_name == "Google Pay":
            daily_map[date_str]["google_pay"] += amt_dec
        elif app_name == "PhonePe":
            daily_map[date_str]["phonepe"] += amt_dec
        elif app_name == "Paytm":
            daily_map[date_str]["paytm"] += amt_dec
        else:
            daily_map[date_str]["other"] += amt_dec

    by_app = [
        {
            "app": k,
            "amount": money_to_float(v["amount"]),
            "count": v["count"],
            "percentage": round(float((v["amount"] / total_collected) * HUNDRED), 1)
            if total_collected > ZERO
            else 0.0,
        }
        for k, v in sorted(app_totals.items(), key=lambda item: item[1]["amount"], reverse=True)
    ]

    by_method = [
        {
            "method": k,
            "amount": money_to_float(v["amount"]),
            "count": v["count"],
            "percentage": round(float((v["amount"] / total_collected) * HUNDRED), 1)
            if total_collected > ZERO
            else 0.0,
        }
        for k, v in sorted(method_totals.items(), key=lambda item: item[1]["amount"], reverse=True)
    ]

    daily_series = [
        {
            "date": d["date"],
            "total": money_to_float(d["total"]),
            "google_pay": money_to_float(d["google_pay"]),
            "phonepe": money_to_float(d["phonepe"]),
            "paytm": money_to_float(d["paytm"]),
            "other": money_to_float(d["other"]),
            "count": d["count"],
        }
        for d in sorted(daily_map.values(), key=lambda d: d["date"])
    ]

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
            "amount": money_to_float(p.amount),
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
        "total_collected": money_to_float(total_collected),
        "total_transactions": total_txns,
        "by_app": by_app,
        "by_method": by_method,
        "daily_series": daily_series,
        "recent_payments": recent_payments,
    }


@router.get("/gateway-status")
async def get_payment_gateway_status(
    _: User = Depends(get_current_user),
):
    """
    Reports whether Razorpay (Live or Test keys) or local sandbox mode is active,
    along with whether Account Aggregator is in sandbox mode.
    """
    gateway = (settings.PAYMENT_GATEWAY or "sandbox").strip().lower()
    key_id = (settings.PAYMENT_KEY_ID or "").strip()
    key_secret = (settings.PAYMENT_KEY_SECRET or "").strip()
    razorpay_configured = gateway == "razorpay" and bool(key_id and key_secret)
    is_live_mode = razorpay_configured and key_id.startswith("rzp_live_")
    is_test_mode = razorpay_configured and not is_live_mode
    aa_provider = (settings.BANK_DATA_PROVIDER or "mock").strip().lower()

    return {
        "gateway": gateway,
        "razorpay_configured": razorpay_configured,
        "is_live_mode": is_live_mode,
        "is_test_mode": is_test_mode,
        "webhook_secret_configured": bool((settings.PAYMENT_WEBHOOK_SECRET or "").strip()),
        "webhook_endpoint": "/api/v1/payments/webhook",
        "bank_data_provider": aa_provider,
        "is_aa_sandbox": aa_provider != "setu_aa",
    }


@router.post("/sync-history")
async def sync_razorpay_payment_history(
    count: int = Query(default=25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_store_owner),
):
    """
    Pulls recent captured Razorpay payments via REST API (`GET /v1/payments`),
    idempotently settles matching store invoices via `record_payment`, and logs all
    captured Razorpay inflows (including QR / Payment Links) into the unified ledger.
    """
    gateway = (settings.PAYMENT_GATEWAY or "sandbox").strip().lower()
    key_id = (settings.PAYMENT_KEY_ID or "").strip()
    key_secret = (settings.PAYMENT_KEY_SECRET or "").strip()
    if gateway != "razorpay" or not (key_id and key_secret):
        return {
            "status": "sandbox_not_configured",
            "gateway": gateway,
            "fetched_count": 0,
            "invoices_settled": 0,
            "ledger_synced": 0,
            "message": "Set PAYMENT_GATEWAY=razorpay with your Razorpay Test or Live keys in .env to pull live Razorpay payments automatically.",
        }

    try:
        captured_items = await payment_service.list_captured_payments(count=count)
    except (RuntimeError, ValueError, httpx.HTTPError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch Razorpay payment history: {exc!s}",
        ) from exc

    owned_businesses = (
        await db.execute(select(Business.id).where(Business.owner_id == user.id))
    ).scalars().all()

    invoices_settled = 0
    ledger_rows: list[dict] = []

    for item in captured_items:
        pid = item.get("payment_id")
        if not pid:
            continue
        amt_dec = to_money(item["amount"])
        order_id = item.get("order_id")
        notes = item.get("notes") or {}
        method = str(item.get("method") or "UPI").upper()
        vpa = item.get("vpa")
        app_name = detect_upi_app(vpa, method)
        created_ts = item.get("created_at")
        occurred_at = (
            datetime.fromtimestamp(int(created_ts), tz=UTC)
            if isinstance(created_ts, (int, float)) and created_ts > 0
            else datetime.now(UTC)
        )

        # 1. Try settling a matching owned invoice (by notes.invoice_id or pending_order_id)
        matched_invoice: Invoice | None = None
        if owned_businesses:
            note_inv_id = notes.get("invoice_id")
            if note_inv_id:
                try:
                    inv_uuid = uuid.UUID(str(note_inv_id))
                    matched_invoice = (
                        await db.execute(
                            select(Invoice).where(
                                Invoice.id == inv_uuid,
                                Invoice.business_id.in_(owned_businesses),
                            )
                        )
                    ).scalar_one_or_none()
                except ValueError:
                    matched_invoice = None
            if matched_invoice is None and order_id:
                matched_invoice = (
                    await db.execute(
                        select(Invoice).where(
                            Invoice.pending_order_id == order_id,
                            Invoice.business_id.in_(owned_businesses),
                        )
                    )
                ).scalar_one_or_none()

        if matched_invoice is not None:
            try:
                rec = await record_payment(
                    db,
                    {
                        "payment_id": pid,
                        "order_id": order_id,
                        "invoice_id": matched_invoice.id,
                        "business_id": matched_invoice.business_id,
                        "customer_id": matched_invoice.customer_id,
                        "amount": amt_dec,
                        "currency": item.get("currency", "INR"),
                        "method": method,
                        "vpa": vpa,
                        "status": "captured",
                        "raw_response": {"source": "razorpay_sync", "order_id": order_id},
                    },
                )
                if rec.get("inserted"):
                    invoices_settled += 1
            except (OverpaymentError, ValueError):
                logger.info("Skipped invoice auto-settlement for Razorpay payment %s (already paid or mismatch)", pid)

        # 2. Idempotently persist every captured Razorpay inflow into bank_transactions + unified ledger
        txn_id = f"rzp:{pid}"[:120]
        counterparty = str(vpa or item.get("email") or item.get("contact") or "Razorpay Customer")[:150]
        narration = (
            item.get("description")
            or f"Razorpay {method} collection ({pid})"
        )
        stmt = (
            pg_insert(BankTransaction)
            .values(
                id=uuid.uuid4(),
                user_id=user.id,
                txn_id=txn_id,
                timestamp=occurred_at,
                date=occurred_at.date().isoformat(),
                amount=amt_dec,
                type="CREDIT",
                mode=method[:30],
                app=app_name[:50],
                vpa=vpa[:150] if vpa else None,
                narration=narration,
                category="Business Sales Settlement",
                counterparty=counterparty,
                masked_acc="Razorpay Merchant",
                source="razorpay_sync",
                created_at=datetime.now(UTC),
            )
            .on_conflict_do_nothing(constraint="uq_bank_transactions_user_txn")
        )
        await db.execute(stmt)
        ledger_rows.append(
            {
                "txn_id": txn_id,
                "timestamp": occurred_at,
                "amount": amt_dec,
                "type": "CREDIT",
                "mode": method,
                "app": app_name,
                "narration": narration,
                "category": "Business & MSME",
                "subcategory": "Retail Store Sale",
                "counterparty": counterparty,
                "source": "razorpay_sync",
            }
        )

    if ledger_rows:
        await sync_bank_rows_to_unified(db, user.id, ledger_rows, commit=False)
        await db.commit()

    return {
        "status": "synced",
        "gateway": gateway,
        "fetched_count": len(captured_items),
        "invoices_settled": invoices_settled,
        "ledger_synced": len(ledger_rows),
        "message": f"Synced {len(captured_items)} captured Razorpay payment(s) ({invoices_settled} invoice(s) settled).",
    }
