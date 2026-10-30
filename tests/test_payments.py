import asyncio
import os
from typing import Any
from uuid import uuid4

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/vyaapardb")
os.environ.setdefault("ENV", "testing")

import httpx
from app.cores.database import engine, get_db
from app.main import app
from app.models.transaction import Invoice
from app.models.user import User
from app.services.auth import get_current_user
from app.services.payment import payment_service
from fastapi.testclient import TestClient


def test_payment_service_create_order_sandbox() -> None:
    order = asyncio.run(payment_service.create_order(amount=500.0, receipt="INV-1001"))
    assert order["order_id"].startswith("order_mock_")
    assert order["amount"] == 500.0
    assert order["currency"] == "INR"
    assert "upi://pay?" in order["upi_intent"]


def test_payment_service_rejects_non_positive_amount() -> None:
    """White-box test: Order creation with zero or negative amount raises ValueError."""
    with pytest.raises(ValueError, match="Order amount must be positive"):
        asyncio.run(payment_service.create_order(amount=0.0, receipt="INV-ZERO"))
    with pytest.raises(ValueError, match="Order amount must be positive"):
        asyncio.run(payment_service.create_order(amount=-150.0, receipt="INV-NEG"))


def test_payment_service_signature_verification() -> None:
    # Valid sandbox signatures in dev/testing mode
    assert payment_service.verify_payment_signature("order_mock_123", "pay_mock_123", "sandbox_valid")
    assert payment_service.verify_payment_signature("order_mock_123", "pay_mock_123", "sandbox_valid_sig")
    # Forged / invalid signatures must be rejected even with order_mock_ prefix
    assert not payment_service.verify_payment_signature("order_mock_123", "pay_mock_123", "forged_bad_sig")
    assert not payment_service.verify_webhook_signature(b'{"status":"test"}', None)
    assert not payment_service.verify_webhook_signature(b'{"status":"test"}', "forged_webhook_sig")
    assert payment_service.verify_webhook_signature(b'{"status":"test"}', "dummy_signature")


def test_payment_service_get_payment_info() -> None:
    info = asyncio.run(payment_service.get_payment_info("pay_12345"))
    assert info["payment_id"] == "pay_12345"
    assert info["status"] == "captured"
    assert info["method"] == "upi"


def test_payment_info_endpoint() -> None:
    mock_user = User(
        id=uuid4(),
        email="testowner@example.com",
        role="STORE_OWNER",
        hashed_password="fake",
        full_name="Test Owner",
    )
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        client = TestClient(app)
        response = client.get(
            "/api/v1/payments/info/pay_sample999",
            headers={"Authorization": "Bearer dummy_token"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["payment_id"] == "pay_sample999"
        assert data["status"] == "captured"
        assert data["method"] == "upi"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.anyio
async def test_payment_webhook_endpoint() -> None:
    await engine.dispose()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        webhook_payload = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": f"pay_test_{uuid4().hex[:8]}",
                        "amount": 25000,
                        "currency": "INR",
                        "status": "captured",
                        "method": "upi",
                        "notes": {"invoice_id": str(uuid4())},
                    }
                }
            },
        }
        # 1. Unsigned webhook must be rejected with 400
        unsigned_res = await client.post("/api/v1/payments/webhook", json=webhook_payload)
        assert unsigned_res.status_code == 400

        # 2. Signed webhook is accepted
        signed_res = await client.post(
            "/api/v1/payments/webhook",
            json=webhook_payload,
            headers={"X-Razorpay-Signature": "sandbox_webhook_sig"},
        )
        assert signed_res.status_code == 200
        assert signed_res.json()["status"] == "success"


class _FakeInvoiceResult:
    def __init__(self, inv: Invoice | None) -> None:
        self._inv = inv

    def scalar_one_or_none(self) -> Invoice | None:
        return self._inv


class _FakePaymentDB:
    def __init__(self, inv: Invoice | None) -> None:
        self.inv = inv

    def add(self, _obj: Any) -> None:
        pass

    async def execute(self, _stmt: Any) -> _FakeInvoiceResult:
        return _FakeInvoiceResult(self.inv)

    async def commit(self) -> None:
        return None

    async def refresh(self, _obj: Any) -> None:
        return None


def test_create_order_cross_business_returns_404() -> None:
    """TC-08: Request a payment order for another business's invoice returns HTTP 404."""
    mock_user = User(id=uuid4(), email="other@example.com", role="STORE_OWNER")
    fake_db = _FakePaymentDB(None)
    app.dependency_overrides[get_current_user] = lambda: mock_user

    async def _override_db():
        yield fake_db

    app.dependency_overrides[get_db] = _override_db
    try:
        client = TestClient(app)
        res = client.post("/api/v1/payments/create-order", json={"invoice_id": str(uuid4())})
        assert res.status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)


def test_create_order_already_paid_returns_400() -> None:
    """TC-09: Request a payment order for an invoice already fully paid returns HTTP 400."""
    mock_user = User(id=uuid4(), email="owner@example.com", role="STORE_OWNER")
    paid_inv = Invoice(
        id=uuid4(),
        invoice_number="INV-PAID-01",
        business_id=uuid4(),
        type="SALE",
        status="PAID",
        total_amount=1000.0,
        paid_amount=1000.0,
    )
    fake_db = _FakePaymentDB(paid_inv)
    app.dependency_overrides[get_current_user] = lambda: mock_user

    async def _override_db():
        yield fake_db

    app.dependency_overrides[get_db] = _override_db
    try:
        client = TestClient(app)
        res = client.post("/api/v1/payments/create-order", json={"invoice_id": str(paid_inv.id)})
        assert res.status_code == 400
        assert "already fully paid" in res.json()["detail"].lower()
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)


def test_partial_payment_webhook_reconciles_amount() -> None:
    """Verifies partial payment via webhook increments paid_amount and keeps status CONFIRMED until full."""
    partial_inv = Invoice(
        id=uuid4(),
        invoice_number="INV-PARTIAL-01",
        business_id=uuid4(),
        type="SALE",
        status="CONFIRMED",
        total_amount=1000.0,
        paid_amount=200.0,
        pending_order_id="order_mock_partial1",
        pending_order_amount=300.0,
    )
    fake_db = _FakePaymentDB(partial_inv)

    async def _override_db():
        yield fake_db

    app.dependency_overrides[get_db] = _override_db
    try:
        client = TestClient(app)
        webhook_payload = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_partial_01",
                        "order_id": "order_mock_partial1",
                        "amount": 30000,
                        "currency": "INR",
                        "status": "captured",
                        "method": "upi",
                        "notes": {"invoice_id": str(partial_inv.id)},
                    }
                }
            },
        }
        res = client.post(
            "/api/v1/payments/webhook",
            json=webhook_payload,
            headers={"X-Razorpay-Signature": "sandbox_webhook_sig"},
        )
        assert res.status_code == 200
        assert partial_inv.paid_amount == 500.0
        assert partial_inv.status == "CONFIRMED"
        assert partial_inv.pending_order_id is None
        assert partial_inv.pending_order_amount is None
    finally:
        app.dependency_overrides.pop(get_db, None)
