import os
import pytest
from uuid import uuid4

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/vyaapardb")
os.environ.setdefault("ENV", "testing")

from fastapi.testclient import TestClient
from app.main import app
from app.models.user import User
from app.services.payment import payment_service
from app.services.auth import get_current_user


def test_payment_service_create_order_sandbox():
    import asyncio
    order = asyncio.run(payment_service.create_order(amount=500.0, receipt="INV-1001"))
    assert order["order_id"].startswith("order_mock_")
    assert order["amount"] == 500.0
    assert order["currency"] == "INR"
    assert "upi://pay?" in order["upi_intent"]


def test_payment_service_signature_verification():
    # Valid sandbox signatures in dev/testing mode
    assert payment_service.verify_payment_signature("order_mock_123", "pay_mock_123", "sandbox_valid")
    assert payment_service.verify_payment_signature("order_mock_123", "pay_mock_123", "sandbox_valid_sig")
    # Forged / invalid signatures must be rejected even with order_mock_ prefix
    assert not payment_service.verify_payment_signature("order_mock_123", "pay_mock_123", "forged_bad_sig")
    assert not payment_service.verify_webhook_signature(b'{"status":"test"}', None)
    assert not payment_service.verify_webhook_signature(b'{"status":"test"}', "forged_webhook_sig")
    assert payment_service.verify_webhook_signature(b'{"status":"test"}', "dummy_signature")


def test_payment_service_get_payment_info():
    import asyncio
    info = asyncio.run(payment_service.get_payment_info("pay_12345"))
    assert info["payment_id"] == "pay_12345"
    assert info["status"] == "captured"
    assert info["method"] == "upi"


def test_payment_info_endpoint():
    mock_user = User(
        id=uuid4(),
        email="testowner@example.com",
        role="STORE_OWNER",
        hashed_password="fake",
        full_name="Test Owner",
    )
    app.dependency_overrides[get_current_user] = lambda: mock_user
    client = TestClient(app)
    response = client.get(
        "/api/v1/payments/info/pay_sample999",
        headers={"Authorization": "Bearer dummy_token"},
    )
    app.dependency_overrides.pop(get_current_user, None)
    assert response.status_code == 200
    data = response.json()
    assert data["payment_id"] == "pay_sample999"
    assert data["status"] == "captured"
    assert data["method"] == "upi"


def test_payment_webhook_endpoint():
    client = TestClient(app)
    webhook_payload = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_test_webhook_01",
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
    unsigned_res = client.post("/api/v1/payments/webhook", json=webhook_payload)
    assert unsigned_res.status_code == 400

    # 2. Signed webhook is accepted
    signed_res = client.post(
        "/api/v1/payments/webhook",
        json=webhook_payload,
        headers={"X-Razorpay-Signature": "sandbox_webhook_sig"},
    )
    assert signed_res.status_code == 200
    assert signed_res.json()["status"] == "success"
