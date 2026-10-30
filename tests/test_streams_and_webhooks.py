import asyncio
import hashlib
import hmac
import json
import os
from uuid import UUID, uuid4

import httpx
import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/vyaapardb")
os.environ.setdefault("ENV", "testing")

from app.cores.config import settings
from app.cores.database import engine
from app.main import app
from app.models.user import User
from app.services.auth import get_current_user
from app.services.banking_provider import MockProvider, SetuAAProvider, get_bank_data_provider
from app.services.event_bus import event_bus, publish_event


@pytest.mark.anyio
async def test_webhook_signature_acceptance_and_rejection():
    """
    Verifies that:
    1. Valid HMAC-SHA256 signature calculated with webhook secret is accepted (200).
    2. Tampered or invalid signature is rejected with 400.
    3. Missing signature header is rejected with 400.
    """
    await engine.dispose()
    original_secret = settings.PAYMENT_WEBHOOK_SECRET
    settings.PAYMENT_WEBHOOK_SECRET = "secret_whk_key_999888"

    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            payload = {
                "id": f"evt_sig_test_{uuid4().hex[:8]}",
                "event": "payment.captured",
                "payload": {
                    "payment": {
                        "entity": {
                            "id": f"pay_{uuid4().hex[:8]}",
                            "amount": 150000,
                            "currency": "INR",
                            "status": "captured",
                        }
                    }
                },
            }
            body_bytes = json.dumps(payload).encode("utf-8")

            # 1. Missing signature header -> 400 Bad Request
            res_missing = await client.post(
                "/api/v1/payments/webhook",
                content=body_bytes,
                headers={"Content-Type": "application/json"},
            )
            assert res_missing.status_code == 400
            assert "signature" in res_missing.json()["detail"].lower()

            # 2. Forged signature -> 400 Bad Request
            res_invalid = await client.post(
                "/api/v1/payments/webhook",
                content=body_bytes,
                headers={
                    "Content-Type": "application/json",
                    "X-Razorpay-Signature": "forged_bad_signature_hexdigest",
                },
            )
            assert res_invalid.status_code == 400

            # 3. Valid HMAC-SHA256 signature -> 200 OK
            valid_sig = hmac.new(
                settings.PAYMENT_WEBHOOK_SECRET.encode("utf-8"),
                body_bytes,
                hashlib.sha256,
            ).hexdigest()

            res_valid = await client.post(
                "/api/v1/payments/webhook",
                content=body_bytes,
                headers={
                    "Content-Type": "application/json",
                    "X-Razorpay-Signature": valid_sig,
                },
            )
            assert res_valid.status_code == 200
            data = res_valid.json()
            assert data["status"] == "success"
            assert data["event_id"] == payload["id"]
    finally:
        settings.PAYMENT_WEBHOOK_SECRET = original_secret


@pytest.mark.anyio
async def test_webhook_idempotency_on_duplicate_event_id():
    """
    Verifies that incoming webhook events are idempotent:
    First event is processed and stored; identical subsequent event ID is skipped.
    """
    await engine.dispose()
    event_id = f"evt_idemp_{uuid4().hex[:12]}"
    payload = {
        "id": event_id,
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": f"pay_{uuid4().hex[:8]}",
                    "amount": 85000,
                    "currency": "INR",
                    "status": "captured",
                }
            }
        },
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # First request: processed
        res1 = await client.post(
            "/api/v1/payments/webhook",
            content=body_bytes,
            headers={"X-Razorpay-Signature": "sandbox_webhook_sig", "Content-Type": "application/json"},
        )
        assert res1.status_code == 200
        assert res1.json()["status"] == "success"
        assert res1.json()["event_id"] == event_id

        # Second request with duplicate event_id: safely skipped
        res2 = await client.post(
            "/api/v1/payments/webhook",
            content=body_bytes,
            headers={"X-Razorpay-Signature": "sandbox_webhook_sig", "Content-Type": "application/json"},
        )
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["status"] == "skipped"
        assert "Duplicate event" in data2["message"]
        assert data2["event_id"] == event_id


@pytest.mark.anyio
async def test_sse_scope_isolation_customer():
    """
    Verifies customer scope isolation on the SSE event bus:
    Customer A must only receive events matching customer A's ID, and never
    events intended for Customer B.
    """
    customer_a_id = str(uuid4())
    customer_b_id = str(uuid4())

    sub_a_iter = event_bus.subscribe(customer_id=customer_a_id)
    # Start consumer task so it registers in event_bus active subscribers
    recv_task = asyncio.create_task(anext(sub_a_iter))
    await asyncio.sleep(0.02)

    # Publish event for customer B
    await publish_event(
        event_type="payment.captured",
        data={"amount": 500.0, "note": "Customer B payment"},
        customer_id=customer_b_id,
        event_id=f"evt_b_{uuid4().hex[:6]}",
    )

    # Publish event for customer A
    evt_a_id = f"evt_a_{uuid4().hex[:6]}"
    await publish_event(
        event_type="payment.captured",
        data={"amount": 1200.0, "note": "Customer A payment"},
        customer_id=customer_a_id,
        event_id=evt_a_id,
    )

    # Subscriber A must receive Customer A's event, ignoring Customer B's event
    received_event = await asyncio.wait_for(recv_task, timeout=2.0)
    assert received_event.id == evt_a_id
    assert received_event.customer_id == customer_a_id
    assert received_event.data["amount"] == 1200.0


@pytest.mark.anyio
async def test_sse_scope_isolation_store_owner():
    """
    Verifies store owner scope isolation on the SSE event bus:
    Store Owner A must only receive events for store A and never store B.
    """
    store_a_id = str(uuid4())
    store_b_id = str(uuid4())

    sub_store_a = event_bus.subscribe(store_id=store_a_id)
    recv_task = asyncio.create_task(anext(sub_store_a))
    await asyncio.sleep(0.02)

    # Event for Store B
    await publish_event(
        event_type="order.paid",
        data={"amount": 450.0, "store": "Store B"},
        store_id=store_b_id,
        event_id=f"evt_store_b_{uuid4().hex[:6]}",
    )

    # Event for Store A
    evt_a_id = f"evt_store_a_{uuid4().hex[:6]}"
    await publish_event(
        event_type="order.paid",
        data={"amount": 999.0, "store": "Store A"},
        store_id=store_a_id,
        event_id=evt_a_id,
    )

    received_event = await asyncio.wait_for(recv_task, timeout=2.0)
    assert received_event.id == evt_a_id
    assert received_event.store_id == store_a_id
    assert received_event.data["amount"] == 999.0


@pytest.mark.anyio
async def test_sse_store_endpoint_forbidden_for_non_owner():
    """
    Verifies that GET /api/v1/streams/store/{store_id} returns 403 Forbidden
    if the requesting user does not own the store.
    """
    await engine.dispose()
    attacker = User(id=uuid4(), email="attacker@example.com", role="STORE_OWNER")
    foreign_store_id = uuid4()

    app.dependency_overrides[get_current_user] = lambda: attacker
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get(f"/api/v1/streams/store/{foreign_store_id}")
            assert res.status_code == 403
            assert "do not have access" in res.json()["detail"].lower()
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.anyio
async def test_sse_reconnect_with_last_event_id():
    """
    Verifies that when a client reconnects providing `Last-Event-ID`,
    the event bus replays missed historical events from the buffer.
    """
    store_id = str(uuid4())

    # Publish historical events 100, 101, 102
    await publish_event(
        event_type="payment.captured",
        data={"seq": 100},
        store_id=store_id,
        event_id="100",
    )
    await publish_event(
        event_type="payment.captured",
        data={"seq": 101},
        store_id=store_id,
        event_id="101",
    )
    await publish_event(
        event_type="payment.captured",
        data={"seq": 102},
        store_id=store_id,
        event_id="102",
    )

    # Reconnect with Last-Event-ID: 100
    replay_sub = event_bus.subscribe(store_id=store_id, last_event_id="100")

    evt1 = await asyncio.wait_for(anext(replay_sub), timeout=2.0)
    assert evt1.id == "101"
    assert evt1.data["seq"] == 101

    evt2 = await asyncio.wait_for(anext(replay_sub), timeout=2.0)
    assert evt2.id == "102"
    assert evt2.data["seq"] == 102


@pytest.mark.anyio
async def test_consent_persistence_across_simulated_restart():
    """
    Verifies consent persistence in the database:
    1. Consent initiated via API is stored in PostgreSQL table `banking_consents`.
    2. Across a simulated server restart (new client, disposed engine), active consent
       is retrieved directly from PostgreSQL.
    3. Revocation updates the status to REVOKED in the database.
    """
    await engine.dispose()
    test_user_id = UUID("77777777-8888-9999-aaaa-bbbbccccdddd")
    user = User(id=test_user_id, email="restart_msme@example.com", role="STORE_OWNER")

    app.dependency_overrides[get_current_user] = lambda: user
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Initiate and persist consent
            init_res = await client.post(
                "/api/v1/banking/consent/initiate",
                json={"fip_id": "hdfc_bank", "data_life_months": 12},
            )
            assert init_res.status_code == 201
            consent_id = init_res.json()["consent_id"]

        # --- SIMULATE PROCESS RESTART ---
        await engine.dispose()

        async with httpx.AsyncClient(transport=transport, base_url="http://test") as restarted_client:
            # 2. Query income stream after restart
            stream_res = await restarted_client.get("/api/v1/banking/income-stream")
            assert stream_res.status_code == 200
            stream_data = stream_res.json()
            assert stream_data["is_connected"] is True
            assert stream_data["active_consent"]["consent_id"] == consent_id
            assert stream_data["active_consent"]["fip_id"] == "hdfc_bank"
            assert stream_data["active_consent"]["masked_acc"] == "XXXX-XXXX-8914"

            # 3. Revoke consent
            revoke_res = await restarted_client.post("/api/v1/banking/consent/revoke")
            assert revoke_res.status_code == 200
            assert revoke_res.json()["status"] == "REVOKED"

        # --- SIMULATE SECOND RESTART ---
        await engine.dispose()

        from app.cores.database import SessionLocal
        from app.models.banking_consent import BankingConsent
        from sqlalchemy import select

        async with SessionLocal() as db:
            res = await db.execute(
                select(BankingConsent).where(BankingConsent.consent_id == consent_id)
            )
            db_consent = res.scalar_one_or_none()
            assert db_consent is not None
            assert db_consent.status == "REVOKED"
            assert db_consent.revoked_at is not None
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_bank_data_provider_interface_and_selection():
    """
    Verifies that:
    1. Default provider is MockProvider.
    2. SetuAAProvider raises NotImplementedError when invoked.
    3. get_bank_data_provider selects provider based on config.
    """
    default_provider = get_bank_data_provider()
    assert isinstance(default_provider, MockProvider)

    setu_provider = SetuAAProvider()
    with pytest.raises(NotImplementedError, match="Setu AA live provider requires"):
        asyncio.run(setu_provider.fetch_inward_credits("sbi_yono", "XXXX-XXXX-4821", "user_123"))

    orig_provider_cfg = settings.BANK_DATA_PROVIDER
    try:
        settings.BANK_DATA_PROVIDER = "setu_aa"
        assert isinstance(get_bank_data_provider(), SetuAAProvider)
        settings.BANK_DATA_PROVIDER = "mock"
        assert isinstance(get_bank_data_provider(), MockProvider)
    finally:
        settings.BANK_DATA_PROVIDER = orig_provider_cfg
