import hashlib
import hmac
import json
import os
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/vyaapardb")
os.environ.setdefault("ENV", "testing")

from app.cores.config import settings
from app.cores.database import SessionLocal, engine
from app.main import app
from app.models.business import Business
from app.models.payment import Payment
from app.models.transaction import Invoice
from app.models.user import User
from app.services.auth import get_current_user
from app.services.payment_recorder import detect_upi_app, record_payment


def test_detect_upi_app():
    """Verifies that consumer UPI handles are accurately detected in one place."""
    assert detect_upi_app("sharma@okhdfcbank") == "Google Pay"
    assert detect_upi_app("rahul@okaxis") == "Google Pay"
    assert detect_upi_app("priya@oksbi") == "Google Pay"
    assert detect_upi_app("merchant@okicici") == "Google Pay"
    assert detect_upi_app("anand@ybl") == "PhonePe"
    assert detect_upi_app("user@ibl") == "PhonePe"
    assert detect_upi_app("shop@paytm") == "Paytm"
    assert detect_upi_app("ramesh@ptyes") == "Paytm"
    assert detect_upi_app("user@upi") == "BHIM UPI"
    assert detect_upi_app("contact@waaxis") == "WhatsApp Pay"
    assert detect_upi_app("buyer@apl") == "Amazon Pay"
    assert detect_upi_app("unknown@bank") == "Other UPI"
    assert detect_upi_app(None, "CARD") == "Card"
    assert detect_upi_app(None, "CASH") == "Cash"


@pytest.mark.anyio
async def test_double_count_prevention_verify_then_webhook():
    """
    Core bug fix test:
    Frontend calls /payments/verify, then gateway webhook runs for the same payment.
    Verify that:
    1. Exactly 1 row is written to `payments` table.
    2. Invoice `paid_amount` rises by exact partial amount once (no double counting!).
    3. Google Pay handle (@okhdfcbank) is identified and stored.
    """
    await engine.dispose()
    orig_secret = settings.PAYMENT_WEBHOOK_SECRET
    settings.PAYMENT_WEBHOOK_SECRET = "test_webhook_secret_123"

    test_user_id = uuid4()
    test_user = User(
        id=test_user_id,
        email=f"owner_{uuid4().hex[:6]}@store.in",
        role="STORE_OWNER",
        hashed_password="hash",
    )
    test_business_id = uuid4()
    test_business = Business(
        id=test_business_id,
        name="Double Count Prevention Kirana",
        owner_id=test_user_id,
    )
    test_invoice_id = uuid4()
    test_invoice = Invoice(
        id=test_invoice_id,
        business_id=test_business_id,
        invoice_number=f"INV-TEST-{uuid4().hex[:6]}",
        type="SALE",
        status="CONFIRMED",
        subtotal=4000.0,
        tax_amount=200.0,
        total_amount=4200.0,
        paid_amount=0.0,
    )

    async with SessionLocal() as session:
        session.add(test_user)
        await session.flush()
        session.add(test_business)
        await session.flush()
        session.add(test_invoice)
        await session.commit()

    payment_id = f"pay_gpay_{uuid4().hex[:10]}"
    order_id = f"order_{uuid4().hex[:10]}"
    partial_amount = 1500.0

    # 1. First: Frontend calls record_payment (simulating /verify flow)
    async with SessionLocal() as session:
        record_res = await record_payment(
            session,
            {
                "payment_id": payment_id,
                "order_id": order_id,
                "invoice_id": test_invoice_id,
                "business_id": test_business_id,
                "amount": partial_amount,
                "currency": "INR",
                "method": "UPI",
                "vpa": "customer@okhdfcbank",
                "status": "captured",
            },
        )
        assert record_res["inserted"] is True
        assert record_res["app"] == "Google Pay"
        assert record_res["paid_amount"] == 1500.0
        assert record_res["invoice_status"] == "CONFIRMED"

    # 2. Check DB: exactly 1 payment record and invoice paid_amount == 1500.0
    async with SessionLocal() as session:
        pmts = (await session.execute(select(Payment).where(Payment.payment_id == payment_id))).scalars().all()
        assert len(pmts) == 1
        assert pmts[0].app == "Google Pay"
        assert pmts[0].vpa == "customer@okhdfcbank"

        inv = (await session.execute(select(Invoice).where(Invoice.id == test_invoice_id))).scalar_one()
        assert inv.paid_amount == 1500.0

    # 3. Second: Gateway Webhook fires for the EXACT SAME payment_id (payment.captured)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        webhook_payload = {
            "id": f"evt_{uuid4().hex[:8]}",
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": payment_id,
                        "order_id": order_id,
                        "amount": int(partial_amount * 100),  # in paise
                        "currency": "INR",
                        "status": "captured",
                        "method": "upi",
                        "vpa": "customer@okhdfcbank",
                        "notes": {
                            "invoice_id": str(test_invoice_id),
                            "store_id": str(test_business_id),
                        },
                    }
                }
            },
        }
        body_bytes = json.dumps(webhook_payload).encode("utf-8")
        signature = hmac.new(
            settings.PAYMENT_WEBHOOK_SECRET.encode("utf-8"),
            body_bytes,
            hashlib.sha256,
        ).hexdigest()

        resp = await client.post(
            "/api/v1/payments/webhook",
            content=body_bytes,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": signature,
            },
        )
        assert resp.status_code == 200

    # 4. Check DB: STILL exactly 1 payment record and invoice paid_amount is STILL 1500.0!
    # Double count was prevented!
    async with SessionLocal() as session:
        pmts = (await session.execute(select(Payment).where(Payment.payment_id == payment_id))).scalars().all()
        assert len(pmts) == 1

        inv = (await session.execute(select(Invoice).where(Invoice.id == test_invoice_id))).scalar_one()
        assert inv.paid_amount == 1500.0, f"Expected 1500.0, but got {inv.paid_amount} (Double counted!)"
    settings.PAYMENT_WEBHOOK_SECRET = orig_secret
    await engine.dispose()


@pytest.mark.anyio
async def test_double_count_prevention_webhook_then_verify():
    """
    Webhook runs first, then frontend calls /verify.
    Verify that /verify does not increment paid_amount again.
    """
    await engine.dispose()
    orig_secret = settings.PAYMENT_WEBHOOK_SECRET
    settings.PAYMENT_WEBHOOK_SECRET = "test_webhook_secret_123"

    test_user_id = uuid4()
    test_user = User(
        id=test_user_id,
        email=f"owner_{uuid4().hex[:6]}@store.in",
        role="STORE_OWNER",
        hashed_password="hash",
    )
    test_business_id = uuid4()
    test_business = Business(
        id=test_business_id,
        name="Webhook First Kirana",
        owner_id=test_user_id,
    )
    test_invoice_id = uuid4()
    test_invoice = Invoice(
        id=test_invoice_id,
        business_id=test_business_id,
        invoice_number=f"INV-TEST-{uuid4().hex[:6]}",
        type="SALE",
        status="CONFIRMED",
        subtotal=2000.0,
        tax_amount=0.0,
        total_amount=2000.0,
        paid_amount=0.0,
    )

    async with SessionLocal() as session:
        session.add(test_user)
        await session.flush()
        session.add(test_business)
        await session.flush()
        session.add(test_invoice)
        await session.commit()

    payment_id = f"pay_phonepe_{uuid4().hex[:10]}"
    order_id = f"order_mock_{uuid4().hex[:10]}"
    amount = 2000.0

    # 1. Webhook runs first
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        webhook_payload = {
            "id": f"evt_{uuid4().hex[:8]}",
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": payment_id,
                        "order_id": order_id,
                        "amount": int(amount * 100),
                        "currency": "INR",
                        "status": "captured",
                        "method": "upi",
                        "vpa": "user@ybl",
                        "notes": {
                            "invoice_id": str(test_invoice_id),
                            "store_id": str(test_business_id),
                        },
                    }
                }
            },
        }
        body_bytes = json.dumps(webhook_payload).encode("utf-8")
        signature = hmac.new(
            settings.PAYMENT_WEBHOOK_SECRET.encode("utf-8"),
            body_bytes,
            hashlib.sha256,
        ).hexdigest()

        resp = await client.post(
            "/api/v1/payments/webhook",
            content=body_bytes,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": signature,
            },
        )
        assert resp.status_code == 200

    # DB check: invoice is paid and exactly 1 payment row exists
    async with SessionLocal() as session:
        inv = (await session.execute(select(Invoice).where(Invoice.id == test_invoice_id))).scalar_one()
        assert inv.paid_amount == 2000.0
        assert inv.status == "PAID"

    # 2. Frontend /verify runs next
    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp_verify = await client.post(
                "/api/v1/payments/verify",
                json={
                    "order_id": order_id,
                    "payment_id": payment_id,
                    "signature": "sandbox_valid",
                    "invoice_id": str(test_invoice_id),
                },
            )
            assert resp_verify.status_code == 200
            data = resp_verify.json()
            assert data["duplicate_prevented"] is True
            assert data["paid_amount"] == 2000.0
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    # 3. DB check: Still only 1 row in payments, invoice is still 2000.0
    async with SessionLocal() as session:
        pmts = (await session.execute(select(Payment).where(Payment.payment_id == payment_id))).scalars().all()
        assert len(pmts) == 1
        assert pmts[0].app == "PhonePe"

        inv = (await session.execute(select(Invoice).where(Invoice.id == test_invoice_id))).scalar_one()
        assert inv.paid_amount == 2000.0
    settings.PAYMENT_WEBHOOK_SECRET = orig_secret
    await engine.dispose()


@pytest.mark.anyio
async def test_payments_summary_endpoint():
    """
    Verifies that GET /api/v1/payments/summary?period=30d:
    1. Returns store totals grouped by app (Google Pay, PhonePe, Paytm, etc.).
    2. Scopes strictly to the authenticated store owner.
    3. Returns daily series for charts.
    """
    await engine.dispose()
    test_user_id = uuid4()
    test_user = User(
        id=test_user_id,
        email=f"owner_{uuid4().hex[:6]}@store.in",
        role="STORE_OWNER",
        hashed_password="hash",
    )
    test_business_id = uuid4()
    test_business = Business(
        id=test_business_id,
        name="Summary Kirana Store",
        owner_id=test_user_id,
    )
    test_invoice_id = uuid4()
    test_invoice = Invoice(
        id=test_invoice_id,
        business_id=test_business_id,
        invoice_number=f"INV-TEST-{uuid4().hex[:6]}",
        type="SALE",
        status="CONFIRMED",
        subtotal=10000.0,
        tax_amount=0.0,
        total_amount=10000.0,
        paid_amount=0.0,
    )

    async with SessionLocal() as session:
        session.add(test_user)
        await session.flush()
        session.add(test_business)
        await session.flush()
        session.add(test_invoice)
        await session.commit()

        # Add Google Pay payment
        await record_payment(
            session,
            {
                "payment_id": f"pay_gpay_{uuid4().hex[:8]}",
                "order_id": f"order_{uuid4().hex[:8]}",
                "invoice_id": test_invoice_id,
                "business_id": test_business_id,
                "amount": 3500.0,
                "currency": "INR",
                "method": "UPI",
                "vpa": "customer@okhdfcbank",
            },
        )
        # Add PhonePe payment
        await record_payment(
            session,
            {
                "payment_id": f"pay_phonepe_{uuid4().hex[:8]}",
                "order_id": f"order_{uuid4().hex[:8]}",
                "invoice_id": test_invoice_id,
                "business_id": test_business_id,
                "amount": 1500.0,
                "currency": "INR",
                "method": "UPI",
                "vpa": "buyer@ybl",
            },
        )

    transport = httpx.ASGITransport(app=app)
    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/payments/summary?period=30d")
            assert resp.status_code == 200
            data = resp.json()

            assert data["total_collected"] == 5000.0
            assert data["total_transactions"] == 2

            app_names = [a["app"] for a in data["by_app"]]
            assert "Google Pay" in app_names
            assert "PhonePe" in app_names

            gpay_entry = next(a for a in data["by_app"] if a["app"] == "Google Pay")
            assert gpay_entry["amount"] == 3500.0
            assert gpay_entry["percentage"] == 70.0

            assert len(data["daily_series"]) >= 1
            assert len(data["recent_payments"]) == 2
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    await engine.dispose()
