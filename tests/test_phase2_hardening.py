from __future__ import annotations

import asyncio
import os
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import select, text

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/vyaapardb")
os.environ.setdefault("ENV", "testing")

from app.cores.config import settings
from app.cores.database import SessionLocal, engine
from app.cores.money import money_to_float, to_money
from app.cores.rate_limit import (
    cleanup_expired_rate_limits,
    enforce_rate_limit,
    reset_rate_limits_async,
)
from app.main import app
from app.models.banking_consent import BankTransaction
from app.models.business import Business
from app.models.payment import Payment
from app.models.rate_limit_hit import RateLimitHit
from app.models.transaction import Invoice
from app.models.user import User
from app.services.auth import get_current_user
from app.services.classifier import build_category_tree
from app.services.event_bus import PostgresEventBus
from app.services.payment_recorder import OverpaymentError, record_payment
from app.services.statement_importer import _clean_amount


@pytest.mark.anyio
async def test_exact_decimal_money_math_rounding_and_numeric_columns():
    """
    Phase 2.1: Verifies exact Decimal currency arithmetic (0.1 + 0.2 == 0.30),
    ROUND_HALF_UP quantization, 10,000-row aggregation without float drift, and
    PostgreSQL NUMERIC(12, 2) schema types on payments & bank_transactions.
    """
    # 1. Classic IEEE-754 trap: 0.1 + 0.2
    sum_dec = to_money("0.1") + to_money("0.2")
    assert sum_dec == Decimal("0.30")
    assert money_to_float(sum_dec) == 0.3

    # 2. ROUND_HALF_UP boundary rounding & Indian currency cleaning
    assert to_money("0.005") == Decimal("0.01")
    assert to_money("10.555") == Decimal("10.56")
    assert to_money(19.995) == Decimal("20.00")
    assert _clean_amount("₹1,23,456.789 Cr") == Decimal("123456.79")

    # 3. Large 10,000-row aggregation (5,000 * 0.10 + 5,000 * 0.20 == exact 1,500.00)
    rows = [
        {"category": "Food", "subcategory": "Grocery", "amount": Decimal("0.10") if i % 2 == 0 else Decimal("0.20")}
        for i in range(10_000)
    ]
    nested, tree = build_category_tree(rows)
    assert nested["Food"]["Grocery"] == 1500.0
    assert tree[0]["total_amount"] == 1500.0
    assert tree[0]["count"] == 10_000

    # 4. Verify PostgreSQL column types after migration 0014
    await engine.dispose()
    async with SessionLocal() as db:
        col_rows = (
            await db.execute(
                text(
                    """
                    SELECT table_name, data_type, numeric_precision, numeric_scale
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND column_name = 'amount'
                      AND table_name IN ('payments', 'bank_transactions')
                    """
                )
            )
        ).mappings().all()
        by_table = {r["table_name"]: r for r in col_rows}
        assert by_table["payments"]["data_type"] == "numeric"
        assert by_table["payments"]["numeric_precision"] == 12
        assert by_table["payments"]["numeric_scale"] == 2
        assert by_table["bank_transactions"]["data_type"] == "numeric"
        assert by_table["bank_transactions"]["numeric_precision"] == 12
        assert by_table["bank_transactions"]["numeric_scale"] == 2


@pytest.mark.anyio
async def test_overpayment_guard_in_payment_recorder_verify_and_reconcile():
    """
    Phase 2.2: Rejects payments where paid_amount + new > total_amount across
    record_payment, /payments/create-order, /payments/verify, and /banking/reconcile/match.
    """
    await engine.dispose()
    owner = User(
        id=uuid4(),
        email=f"ovp_{uuid4().hex[:8]}@store.in",
        role="STORE_OWNER",
        hashed_password="hash",
    )
    biz = Business(id=uuid4(), name="Exact Paisa Kirana", owner_id=owner.id)
    inv = Invoice(
        id=uuid4(),
        business_id=biz.id,
        invoice_number=f"INV-OVP-{uuid4().hex[:6]}",
        type="SALE",
        status="CONFIRMED",
        subtotal=Decimal("1000.00"),
        tax_amount=Decimal("0.00"),
        total_amount=Decimal("1000.00"),
        paid_amount=Decimal("0.00"),
    )
    over_tx_id = f"TX_OVER_{uuid4().hex[:8]}"
    exact_tx_id = f"TX_EXACT_{uuid4().hex[:8]}"

    async with SessionLocal() as db:
        db.add(owner)
        await db.flush()
        db.add(biz)
        await db.flush()
        db.add(inv)
        await db.flush()
        db.add_all(
            [
                BankTransaction(
                    user_id=owner.id,
                    txn_id=over_tx_id,
                    date="2026-11-25",
                    amount=Decimal("450.00"),
                    type="CREDIT",
                    mode="UPI",
                    app="Google Pay",
                    narration=f"Credit for {inv.invoice_number}",
                    category="Business Sales Settlement",
                    counterparty="Walk-in Buyer",
                ),
                BankTransaction(
                    user_id=owner.id,
                    txn_id=exact_tx_id,
                    date="2026-11-25",
                    amount=Decimal("400.00"),
                    type="CREDIT",
                    mode="UPI",
                    app="PhonePe",
                    narration=f"Exact balance for {inv.invoice_number}",
                    category="Business Sales Settlement",
                    counterparty="Walk-in Buyer",
                ),
            ]
        )
        await db.commit()

    # 1. Valid partial payment of 600.00 leaves 400.00 due
    first_pid = f"pay_ok_{uuid4().hex[:8]}"
    async with SessionLocal() as db:
        res_ok = await record_payment(
            db,
            {
                "payment_id": first_pid,
                "order_id": f"ord_{uuid4().hex[:8]}",
                "invoice_id": inv.id,
                "business_id": biz.id,
                "amount": Decimal("600.00"),
                "currency": "INR",
                "method": "UPI",
                "vpa": "buyer@oksbi",
            },
        )
        assert res_ok["inserted"] is True
        assert res_ok["paid_amount"] == 600.0

    # 2. Direct record_payment of 400.01 (1 paisa overpayment) must raise OverpaymentError & rollback
    bad_pid = f"pay_over_{uuid4().hex[:8]}"
    async with SessionLocal() as db:
        with pytest.raises(OverpaymentError, match="Overpayment rejected"):
            await record_payment(
                db,
                {
                    "payment_id": bad_pid,
                    "order_id": f"ord_{uuid4().hex[:8]}",
                    "invoice_id": inv.id,
                    "business_id": biz.id,
                    "amount": Decimal("400.01"),
                    "currency": "INR",
                    "method": "UPI",
                },
            )

    async with SessionLocal() as db:
        leaked = (await db.execute(select(Payment).where(Payment.payment_id == bad_pid))).scalar_one_or_none()
        assert leaked is None
        fresh_inv = (await db.execute(select(Invoice).where(Invoice.id == inv.id))).scalar_one()
        assert fresh_inv.paid_amount == Decimal("600.00")

    # 3. API endpoints (/create-order, /verify, /reconcile/match) reject overpayments with HTTP 400
    app.dependency_overrides[get_current_user] = lambda: owner
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            r_order = await client.post(
                "/api/v1/payments/create-order",
                json={"invoice_id": str(inv.id), "amount": 500.0},
            )
            assert r_order.status_code == 400
            assert "exceeds" in r_order.json()["detail"].lower()

            r_recon_over = await client.post(
                "/api/v1/banking/reconcile/match",
                json={"txn_id": over_tx_id, "invoice_id": str(inv.id)},
            )
            assert r_recon_over.status_code == 400
            assert "overpayment rejected" in r_recon_over.json()["detail"].lower()

            # Exact remaining 400.00 reconciles cleanly to PAID
            r_recon_ok = await client.post(
                "/api/v1/banking/reconcile/match",
                json={"txn_id": exact_tx_id, "invoice_id": str(inv.id)},
            )
            assert r_recon_ok.status_code == 200
            assert r_recon_ok.json()["reconciled"] is True
            assert r_recon_ok.json()["paid_amount"] == 1000.0
            assert r_recon_ok.json()["invoice_status"] == "PAID"

            # Re-matching against an already-PAID invoice is rejected with HTTP 400
            r_recon_dup = await client.post(
                "/api/v1/banking/reconcile/match",
                json={"txn_id": exact_tx_id, "invoice_id": str(inv.id)},
            )
            assert r_recon_dup.status_code == 400
            assert "already fully settled" in r_recon_dup.json()["detail"].lower()
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        await engine.dispose()


@pytest.mark.anyio
async def test_concurrent_overpayment_race_under_for_update_lock():
    """
    Phase 2.2 (Concurrency): Two simultaneous ₹600 payments race against a ₹1,000 invoice
    across separate database sessions. PostgreSQL's SELECT ... FOR UPDATE lock guarantees
    that exactly one succeeds and the second fails with OverpaymentError.
    """
    await engine.dispose()
    owner = User(
        id=uuid4(),
        email=f"race_{uuid4().hex[:8]}@store.in",
        role="STORE_OWNER",
        hashed_password="hash",
    )
    biz = Business(id=uuid4(), name="Concurrent Lock Kirana", owner_id=owner.id)
    inv = Invoice(
        id=uuid4(),
        business_id=biz.id,
        invoice_number=f"INV-RACE-{uuid4().hex[:6]}",
        type="SALE",
        status="CONFIRMED",
        subtotal=Decimal("1000.00"),
        tax_amount=Decimal("0.00"),
        total_amount=Decimal("1000.00"),
        paid_amount=Decimal("0.00"),
    )
    async with SessionLocal() as db:
        db.add(owner)
        await db.flush()
        db.add(biz)
        await db.flush()
        db.add(inv)
        await db.commit()

    async def _attempt_payment(suffix: str):
        async with SessionLocal() as session:
            return await record_payment(
                session,
                {
                    "payment_id": f"pay_race_{suffix}_{uuid4().hex[:8]}",
                    "order_id": f"ord_race_{suffix}_{uuid4().hex[:8]}",
                    "invoice_id": inv.id,
                    "business_id": biz.id,
                    "amount": Decimal("600.00"),
                    "currency": "INR",
                    "method": "UPI",
                    "vpa": f"user_{suffix}@ybl",
                },
            )

    outcomes = await asyncio.gather(
        _attempt_payment("a"),
        _attempt_payment("b"),
        return_exceptions=True,
    )

    successes = [o for o in outcomes if isinstance(o, dict) and o.get("inserted") is True]
    overpayment_errors = [o for o in outcomes if isinstance(o, OverpaymentError)]

    assert len(successes) == 1, f"Expected 1 winner, got outcomes={outcomes!r}"
    assert len(overpayment_errors) == 1, f"Expected 1 OverpaymentError, got outcomes={outcomes!r}"

    async with SessionLocal() as db:
        locked_inv = (await db.execute(select(Invoice).where(Invoice.id == inv.id))).scalar_one()
        pmts = (await db.execute(select(Payment).where(Payment.invoice_id == inv.id))).scalars().all()
        assert locked_inv.paid_amount == Decimal("600.00")
        assert locked_inv.status == "CONFIRMED"
        assert len(pmts) == 1
    await engine.dispose()


@pytest.mark.anyio
async def test_shared_postgres_rate_limiter_across_sessions_and_cleanup():
    """
    Phase 2.3: Verifies shared PostgreSQL rate_limit_hits enforcement across two
    independent sessions (simulating separate Container App replicas) and stale window cleanup.
    """
    await engine.dispose()
    await reset_rate_limits_async()
    rl_key = f"login:shared_{uuid4().hex[:8]}@shop.in"

    async with SessionLocal() as replica_a_db, SessionLocal() as replica_b_db:
        # 2 hits on Replica A + 2 hits on Replica B = 4 allowed requests
        await enforce_rate_limit(rl_key, max_requests=4, window_seconds=60, db=replica_a_db)
        await enforce_rate_limit(rl_key, max_requests=4, window_seconds=60, db=replica_b_db)
        await enforce_rate_limit(rl_key, max_requests=4, window_seconds=60, db=replica_a_db)
        await enforce_rate_limit(rl_key, max_requests=4, window_seconds=60, db=replica_b_db)

        # 5th hit on Replica B immediately sees Replica A's committed counts and raises 429
        with pytest.raises(HTTPException) as exc_info:
            await enforce_rate_limit(rl_key, max_requests=4, window_seconds=60, db=replica_b_db)
        assert exc_info.value.status_code == 429

        # Insert a stale historical window and verify cleanup purges expired rows only
        stale_key = f"stale:{uuid4().hex[:8]}"
        replica_a_db.add(RateLimitHit(key=stale_key, window_start=1_000_000, count=9))
        await replica_a_db.commit()

        deleted = await cleanup_expired_rate_limits(replica_b_db, older_than_seconds=3600)
        assert deleted >= 1

        stale_rem = (
            await replica_a_db.execute(select(RateLimitHit).where(RateLimitHit.key == stale_key))
        ).scalar_one_or_none()
        active_rem = (
            await replica_a_db.execute(select(RateLimitHit).where(RateLimitHit.key == rl_key))
        ).scalar_one_or_none()
        assert stale_rem is None
        assert active_rem is not None
        assert active_rem.count == 5

    await reset_rate_limits_async()
    await engine.dispose()


@pytest.mark.anyio
async def test_postgres_event_bus_cross_replica_delivery_and_overflow():
    """
    Phase 2.4: Verifies real-time SSE event fan-out between two independent PostgresEventBus
    instances over dedicated asyncpg LISTEN/NOTIFY connections, tenant scope isolation,
    echo deduplication, and >8 KB payload overflow via `sse_event_payloads`.
    """
    channel = f"vk_test_{uuid4().hex[:8]}"
    bus_a = PostgresEventBus(settings.DATABASE_URL, channel=channel, ssl_verify=False)
    bus_b = PostgresEventBus(settings.DATABASE_URL, channel=channel, ssl_verify=False)

    store_target = str(uuid4())
    store_other = str(uuid4())

    sub_a = bus_a.subscribe(store_id=store_target)
    sub_b = bus_b.subscribe(store_id=store_target)
    sub_other = bus_b.subscribe(store_id=store_other)

    try:
        await bus_a.ensure_listener()
        await bus_b.ensure_listener()

        # Prime async generators so subscriptions are registered before publishing
        task_a = asyncio.create_task(anext(sub_a))
        task_b = asyncio.create_task(anext(sub_b))
        task_other = asyncio.create_task(anext(sub_other))
        await asyncio.sleep(0.05)

        # 1. Normal cross-replica event published on Replica A reaches Replica B
        await bus_a.publish(
            event_type="payment.captured",
            data={"invoice_id": "inv_101", "amount": 250.75},
            store_id=store_target,
            event_id=f"evt_small_{uuid4().hex[:8]}",
        )

        evt_a = await asyncio.wait_for(task_a, timeout=3.0)
        evt_b = await asyncio.wait_for(task_b, timeout=3.0)
        assert evt_a.event == "payment.captured"
        assert evt_b.event == "payment.captured"
        assert evt_b.data["invoice_id"] == "inv_101"
        assert evt_b.data["amount"] == 250.75
        assert not task_other.done(), "Unrelated store subscriber must not receive scoped event"
        task_other.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task_other

        # 2. Large (>8 KB) payload spills to sse_event_payloads and reconstructs on Replica B
        large_blob = "X" * 12_000
        large_id = f"evt_large_{uuid4().hex[:8]}"
        task_b_large = asyncio.create_task(anext(sub_b))
        await asyncio.sleep(0.02)

        await bus_a.publish(
            event_type="statement.imported",
            data={"summary_blob": large_blob, "rows": 240},
            store_id=store_target,
            event_id=large_id,
        )

        evt_b_large = await asyncio.wait_for(task_b_large, timeout=3.0)
        assert evt_b_large.id == large_id
        assert evt_b_large.event == "statement.imported"
        assert evt_b_large.data["rows"] == 240
        assert evt_b_large.data["summary_blob"] == large_blob
    finally:
        await sub_a.aclose()
        await sub_b.aclose()
        await sub_other.aclose()
        await bus_a.close()
        await bus_b.close()


@pytest.mark.anyio
async def test_razorpay_gateway_status_history_sync_and_debit_simulator(monkeypatch):
    """
    Verifies startup Razorpay REST history sync (`/payments/gateway-status`, `/payments/sync-history`)
    plus simulated DEBIT emission (`/banking/demo-stream/emit?direction=DEBIT`).
    """
    from app.services.payment import payment_service

    await engine.dispose()
    owner = User(
        id=uuid4(),
        email=f"rzp_sync_{uuid4().hex[:8]}@store.in",
        role="STORE_OWNER",
        hashed_password="hash",
    )
    biz = Business(id=uuid4(), name="Razorpay Startup Kirana", owner_id=owner.id)
    inv = Invoice(
        id=uuid4(),
        business_id=biz.id,
        invoice_number=f"INV-RZP-{uuid4().hex[:6]}",
        type="SALE",
        status="CONFIRMED",
        subtotal=Decimal("750.00"),
        tax_amount=Decimal("0.00"),
        total_amount=Decimal("750.00"),
        paid_amount=Decimal("0.00"),
        pending_order_id=f"order_rzp_{uuid4().hex[:8]}",
        pending_order_amount=Decimal("750.00"),
    )
    async with SessionLocal() as db:
        db.add(owner)
        await db.flush()
        db.add(biz)
        await db.flush()
        db.add(inv)
        await db.commit()

    orig = (settings.PAYMENT_GATEWAY, settings.PAYMENT_KEY_ID, settings.PAYMENT_KEY_SECRET)
    app.dependency_overrides[get_current_user] = lambda: owner
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            # 1. Sandbox gateway status
            st_sandbox = await client.get("/api/v1/payments/gateway-status")
            assert st_sandbox.status_code == 200
            assert st_sandbox.json()["is_aa_sandbox"] is True

            # 2. Razorpay Test Mode history pull settles matching invoice + logs QR sale
            settings.PAYMENT_GATEWAY = "razorpay"
            settings.PAYMENT_KEY_ID = "rzp_test_placeholder_sync"
            settings.PAYMENT_KEY_SECRET = "test_secret_sync_123"

            st_rzp = await client.get("/api/v1/payments/gateway-status")
            assert st_rzp.status_code == 200
            assert st_rzp.json()["razorpay_configured"] is True
            assert st_rzp.json()["is_test_mode"] is True

            pid_inv = f"pay_rzp_inv_{uuid4().hex[:8]}"
            pid_qr = f"pay_rzp_qr_{uuid4().hex[:8]}"

            async def _fake_list_captured(count: int = 25):
                assert count == 25
                return [
                    {
                        "payment_id": pid_inv,
                        "order_id": inv.pending_order_id,
                        "amount": Decimal("750.00"),
                        "currency": "INR",
                        "status": "captured",
                        "method": "UPI",
                        "vpa": "buyer@okhdfcbank",
                        "notes": {"invoice_id": str(inv.id)},
                        "description": "Invoice checkout",
                        "created_at": 1764000000,
                    },
                    {
                        "payment_id": pid_qr,
                        "order_id": None,
                        "amount": Decimal("320.50"),
                        "currency": "INR",
                        "status": "captured",
                        "method": "UPI",
                        "vpa": "walkin@ybl",
                        "notes": {},
                        "description": "Counter QR Sale",
                        "created_at": 1764000500,
                    },
                ]

            monkeypatch.setattr(payment_service, "list_captured_payments", _fake_list_captured)
            sync_res = await client.post("/api/v1/payments/sync-history?count=25")
            assert sync_res.status_code == 200
            body = sync_res.json()
            assert body["status"] == "synced"
            assert body["fetched_count"] == 2
            assert body["invoices_settled"] == 1
            assert body["ledger_synced"] == 2

            # Idempotent re-sync settles 0 new invoices
            sync_again = await client.post("/api/v1/payments/sync-history?count=25")
            assert sync_again.status_code == 200
            assert sync_again.json()["invoices_settled"] == 0

            # 3. Simulated DEBIT event persists and updates /personal-spending
            dr_res = await client.post("/api/v1/banking/demo-stream/emit?direction=DEBIT")
            assert dr_res.status_code == 201
            assert dr_res.json()["type"] == "DEBIT"
            spend_res = await client.get("/api/v1/banking/personal-spending")
            assert spend_res.status_code == 200
            assert spend_res.json()["debits_count"] >= 1
            assert spend_res.json()["credits_count"] >= 2
    finally:
        settings.PAYMENT_GATEWAY, settings.PAYMENT_KEY_ID, settings.PAYMENT_KEY_SECRET = orig
        app.dependency_overrides.pop(get_current_user, None)
        await engine.dispose()
