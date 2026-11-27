from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select, text

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/vyaapardb")
os.environ.setdefault("ENV", "testing")

from app.cores.database import SessionLocal, engine
from app.cores.rate_limit import reset_rate_limits_async
from app.main import app
from app.models.banking_consent import BankTransaction
from app.models.purchase import PersonalPurchase
from app.models.user import User
from app.services.auth import get_current_user
from app.services.upi_bridge import parse_upi_alert_payload, scrub_sensitive_text


def test_real_indian_bank_sms_parser_zero_cred_leaks_and_dates():
    """
    Verifies real Indian bank DLT SMS parsing (HDFC, SBI, ICICI, Axis, Kotak),
    historical date extraction for time-series alignment, failed/collect/promo blocking,
    and zero-leak scrubbing of PAN, Aadhaar, URLs, API tokens, and Avl Bal.
    """
    # 1. HDFC Bank UPI Debit with Avl Bal (must extract 485.50 and strip 45,200.00 balance)
    hdfc = parse_upi_alert_payload(
        sender_id="AD-HDFCBK-S",
        message="Sent Rs.485.50 From HDFC Bank A/C *4821 To SWIGGY On 22/11/26 Ref 432610011223. Avl Bal: Rs 45,200.00",
        source_channel="android_sms",
    )
    assert hdfc["accepted"] is True
    t = hdfc["transaction"]
    assert t["type"] == "DEBIT"
    assert t["amount"] == 485.5
    assert t["date"] == "2026-11-22"
    assert t["txn_id"] == "432610011223"
    assert "45,200" not in t["narration"]

    # 2. SBI UPI bare numeric debit ("debited by 450.0 on date 26Nov26")
    sbi = parse_upi_alert_payload(
        sender_id="VM-SBIUPI",
        message="Dear UPI user A/C X3421 debited by 450.0 on date 26Nov26 trf to ZOMATO Refno 432710022334",
        source_channel="android_sms",
    )
    assert sbi["accepted"] is True
    assert sbi["transaction"]["type"] == "DEBIT"
    assert sbi["transaction"]["amount"] == 450.0
    assert sbi["transaction"]["date"] == "2026-11-26"
    assert sbi["transaction"]["txn_id"] == "432710022334"

    # 3. ICICI Bank ("Acct debited ...; BLINKIT credited" MUST be DEBIT, not CREDIT)
    icici = parse_upi_alert_payload(
        sender_id="JX-ICICIB",
        message="ICICI Bank Acct XX1029 debited for Rs 840.00 on 24-Nov-26; BLINKIT credited. UPI:432810033445. Avl Bal: INR 18,900.00",
        source_channel="android_sms",
    )
    assert icici["accepted"] is True
    assert icici["transaction"]["type"] == "DEBIT"
    assert icici["transaction"]["amount"] == 840.0
    assert icici["transaction"]["date"] == "2026-11-24"
    assert "18,900" not in icici["transaction"]["narration"]

    # 4. Kotak Bank (bare amount before Avl Bal: INR — MUST extract 350.00, NOT 1200.50!)
    kotak = parse_upi_alert_payload(
        sender_id="JD-KOTAKB",
        message="A/C XX4421 debited by 350.00 on 12-06-26 via UPI Ref 6163920199. Avl Bal: INR 1,200.50",
        source_channel="android_sms",
    )
    assert kotak["accepted"] is True
    assert kotak["transaction"]["type"] == "DEBIT"
    assert kotak["transaction"]["amount"] == 350.0
    assert kotak["transaction"]["date"] == "2026-06-12"
    assert "1,200.50" not in kotak["transaction"]["narration"]

    # 5. Axis Bank Credit
    axis = parse_upi_alert_payload(
        sender_id="AX-AXISBK",
        message="INR 3,450.00 credited to A/c no. XX9912 on 25-Nov-26. Info- UPI/CR/432910044556/RAHUL SHARMA",
        source_channel="android_sms",
    )
    assert axis["accepted"] is True
    assert axis["transaction"]["type"] == "CREDIT"
    assert axis["transaction"]["amount"] == 3450.0
    assert axis["transaction"]["date"] == "2026-11-25"

    # 6. Strict blockers: promotional DLT -P, failed txn, collect request, mandate reminder
    assert parse_upi_alert_payload(sender_id="AD-LOANAD-P", message="Debited Rs 500 offer")["accepted"] is False
    assert parse_upi_alert_payload(message="Your UPI payment of Rs 500 to Swiggy FAILED due to insufficient balance")["accepted"] is False
    assert parse_upi_alert_payload(message="Rahul has requested Rs 500 on Google Pay. Pay now.")["accepted"] is False
    assert parse_upi_alert_payload(message="UPI AutoPay mandate created for Rs 999. Will be auto-debited on 01-Dec-26.")["accepted"] is False

    # 7. Zero-leak scrubber: PAN, spaced Aadhaar, URLs, tokens, secrets, Avl Bal
    dirty = (
        "Paid Rs 500 via A/C 9988776655443322 PAN ABCDE1234F ID 1234 5678 9012 "
        "token=mysecret https://evil.link/claim vk_upi_abc.def Avl Bal: Rs 9,99,999.00"
    )
    clean, masked = scrub_sensitive_text(dirty)
    for forbidden in ("9988776655443322", "ABCDE1234F", "1234 5678 9012", "mysecret", "evil.link", "vk_upi_abc", "9,99,999"):
        assert forbidden not in clean
    assert masked == "XXXX-XXXX-3322"


@pytest.mark.anyio
async def test_batch_sms_import_dry_run_dedup_and_cashflow_timeseries():
    """
    End-to-end beta flow:
    1. Dry-run SMS batch preview scrubs & parses 10 multi-day bank SMS alerts + blocks OTP/failed/dup without writing DB.
    2. Real commit ingests them into `bank_transactions` + `unified_transactions`.
    3. `GET /api/v1/ai/cashflow-timeseries` returns exact historical daily series, 14-day multi-model
       forecast with 80% confidence intervals, weekday seasonality, and spike anomaly detection.
    """
    await engine.dispose()
    user = User(
        id=uuid4(),
        email=f"ts_sms_{uuid4().hex[:8]}@beta.in",
        role="STORE_OWNER",
        hashed_password="hash",
    )
    async with SessionLocal() as db:
        db.add(user)
        await db.commit()

    today = datetime.now(UTC).date()
    lines: list[str] = []
    # Build 10 multi-day real-format bank SMS alerts + 1 huge spike day + 1 OTP + 1 failed + 1 dup UTR
    for offset in range(1, 11):
        d = (today - timedelta(days=offset)).strftime("%d-%b-%y")
        utr_cr = f"4390{offset:02d}112233"
        utr_dr = f"4391{offset:02d}445566"
        cr_amt = 2000 + offset * 150
        dr_amt = 14000 if offset == 2 else (400 + offset * 40)
        lines.append(f"AX-AXISBK: INR {cr_amt:.2f} credited to A/c no. XX9912 on {d}. Info- UPI/CR/{utr_cr}/CUSTOMER {offset}")
        lines.append(f"AD-HDFCBK: Sent Rs.{dr_amt:.2f} From HDFC Bank A/C *4821 To SWIGGY On {d} Ref {utr_dr}. Avl Bal: Rs 50,000.00")
    # Duplicate UTR + OTP + Failed txn (must all be skipped/blocked)
    lines.append(f"AD-HDFCBK: Sent Rs.440.00 From HDFC Bank A/C *4821 To SWIGGY On {(today - timedelta(days=1)).strftime('%d-%b-%y')} Ref 439101445566")
    lines.append("AD-HDFCBK: 739104 is your OTP for Rs 9,000. Do not share OTP.")
    lines.append("VM-SBIUPI: Payment of Rs 1,200 to Zomato FAILED due to insufficient balance.")
    raw_batch = "\n\n".join(lines)

    app.dependency_overrides[get_current_user] = lambda: user
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            # 1. Dry run previews without persisting
            dry = await client.post(
                "/api/v1/banking/sms-import",
                json={"raw_text": raw_batch, "dry_run": True},
            )
            assert dry.status_code == 200, dry.text
            d = dry.json()
            assert d["status"] == "preview"
            assert d["imported_count"] == 20
            assert d["credits_count"] == 10
            assert d["debits_count"] == 10
            assert d["ignored_count"] == 2
            assert d["duplicates_skipped"] == 1
            for tx in d["transactions"]:
                assert "50,000" not in tx["narration"]

            async with SessionLocal() as db:
                count_after_dry = len((await db.execute(select(BankTransaction).where(BankTransaction.user_id == user.id))).scalars().all())
                assert count_after_dry == 0

            # 2. Commit batch into PostgreSQL
            live = await client.post(
                "/api/v1/banking/sms-import",
                json={"raw_text": raw_batch, "dry_run": False},
            )
            assert live.status_code == 200
            assert live.json()["status"] == "ingested"
            assert live.json()["imported_count"] == 20

            # 3. Query unified cashflow time-series & multi-model forecast
            ts_res = await client.get(
                "/api/v1/ai/cashflow-timeseries?lookback_days=30&horizon_days=14&granularity=daily&view=all"
            )
            assert ts_res.status_code == 200, ts_res.text
            ts = ts_res.json()
            assert len(ts["historical"]) == 30
            assert len(ts["forecast"]) == 14
            assert len(ts["seasonality"]) == 7
            assert ts["summary"]["total_transactions"] == 20
            assert ts["summary"]["total_inflow"] > 20_000
            assert ts["summary"]["total_outflow"] > 14_000
            assert ts["summary"]["anomaly_count"] >= 1
            assert ts["models"]["inflow_selected"] in ("SMA-7", "Holt-Linear", "RidgeRegression", "RandomForestRegressor")
            assert ts["forecast"][0]["inflow_lower"] <= ts["forecast"][0]["projected_inflow"] <= ts["forecast"][0]["inflow_upper"]
            assert any(s["source"] == "sms_upi" for s in ts["sources"])
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        await engine.dispose()


@pytest.mark.anyio
async def test_postgresql_force_rls_enforces_tenant_isolation_without_where():
    """
    Proves migration 0015's FORCE ROW LEVEL SECURITY actually enforces user isolation
    inside PostgreSQL itself under a non-superuser role, even on a bare `SELECT *`
    with NO `WHERE` clause.
    """
    await engine.dispose()
    user_a = User(id=uuid4(), email=f"rls_a_{uuid4().hex[:8]}@beta.in", role="STORE_OWNER", hashed_password="x")
    user_b = User(id=uuid4(), email=f"rls_b_{uuid4().hex[:8]}@beta.in", role="STORE_OWNER", hashed_password="x")

    async with SessionLocal() as db:
        db.add_all([user_a, user_b])
        await db.flush()
        db.add_all(
            [
                BankTransaction(
                    user_id=user_a.id,
                    txn_id=f"RLS_A_{uuid4().hex[:8]}",
                    date="2026-11-26",
                    amount=Decimal("999.00"),
                    type="DEBIT",
                    narration="Private User A Txn",
                    category="Food",
                    counterparty="Secret A",
                ),
                BankTransaction(
                    user_id=user_b.id,
                    txn_id=f"RLS_B_{uuid4().hex[:8]}",
                    date="2026-11-26",
                    amount=Decimal("111.00"),
                    type="DEBIT",
                    narration="Private User B Txn",
                    category="Food",
                    counterparty="Secret B",
                ),
                PersonalPurchase(
                    user_id=user_a.id,
                    marketplace="Amazon",
                    category="Shopping",
                    amount=Decimal("550.00"),
                    purchased_at=datetime.now(UTC),
                    order_id=f"ORD-A-{uuid4().hex[:6]}",
                    order_id_bidx=uuid4().hex,
                    payment_method="UPI",
                ),
            ]
        )
        # Ensure non-superuser role exists with SELECT permission for RLS verification
        await db.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'vk_rls_app_role') THEN
                        CREATE ROLE vk_rls_app_role NOLOGIN NOBYPASSRLS;
                    END IF;
                END
                $$;
                """
            )
        )
        await db.execute(text("GRANT USAGE ON SCHEMA public TO vk_rls_app_role"))
        await db.execute(text("GRANT SELECT ON bank_transactions, personal_purchases, unified_transactions, businesses TO vk_rls_app_role"))
        await db.commit()

    # 1. Under vk_rls_app_role with app.current_user_id = user_b, bare SELECT * sees ONLY user_b
    async with SessionLocal() as db:
        await db.execute(text("SET LOCAL ROLE vk_rls_app_role"))
        await db.execute(text("SELECT set_config('app.rls_strict', 'on', true)"))
        await db.execute(text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": str(user_b.id)})

        bt_user_ids = (await db.execute(text("SELECT DISTINCT user_id FROM bank_transactions"))).scalars().all()
        pp_rows = (await db.execute(text("SELECT id FROM personal_purchases"))).scalars().all()
        assert bt_user_ids == [user_b.id], f"RLS leaked foreign rows: {bt_user_ids}"
        assert pp_rows == [], "RLS leaked User A personal_purchases to User B"
        await db.rollback()

    # 2. Under app.rls_strict='on' with unset app.current_user_id, Postgres fails closed (0 rows)
    async with SessionLocal() as db:
        await db.execute(text("SET LOCAL ROLE vk_rls_app_role"))
        await db.execute(text("SELECT set_config('app.rls_strict', 'on', true)"))
        await db.execute(text("SELECT set_config('app.current_user_id', '', true)"))
        strict_count = (await db.execute(text("SELECT COUNT(*) FROM bank_transactions"))).scalar_one()
        assert strict_count == 0
        await db.rollback()

    await engine.dispose()


@pytest.mark.anyio
async def test_otp_json_body_endpoints_avoid_query_string_leak():
    """Verifies /auth/otp/send and /auth/otp/verify work cleanly with JSON POST bodies (no URL query params)."""
    await engine.dispose()
    await reset_rate_limits_async()
    phone = f"94{uuid4().int % 10**8:08d}"

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        send_res = await client.post(
            "/api/v1/auth/otp/send",
            json={"phone": phone, "purpose": "TRANSACTION"},
        )
        assert send_res.status_code == 200, send_res.text
        code = send_res.json().get("dev_otp")
        assert code and len(code) == 6

        ver_res = await client.post(
            "/api/v1/auth/otp/verify",
            json={"phone": phone, "otp": code, "purpose": "TRANSACTION"},
        )
        assert ver_res.status_code == 200, ver_res.text
        assert ver_res.json()["verified"] is True
    await engine.dispose()


def test_redos_adversarial_inputs_finish_in_linear_time():
    """Ensures CodeQL-remediated regexes and PDF/SMS parsers never exhibit polynomial backtracking."""
    import time

    from app.services.statement_importer import (
        _clean_col_key,
        _iter_pdf_raw_streams,
        _parse_multiline_bank_pdf_rows,
        _parse_phonepe_paytm_pdf_blocks,
    )
    from app.services.upi_bridge import is_security_or_otp_message

    t0 = time.perf_counter()
    assert _clean_col_key("(" * 25_000) == ""
    assert _iter_pdf_raw_streams(b"stream\n" * 5_000) == []
    assert is_security_or_otp_message("has requested" + " " * 25_000 + "!") is False
    clean_bal, _ = scrub_sensitive_text("Avl Bal" + " " * 25_000 + "!")
    assert "Avl" in clean_bal
    clean_acc, _ = scrub_sensitive_text("A/C" + " " * 25_000 + "!")
    assert "A/C" in clean_acc
    assert _parse_phonepe_paytm_pdf_blocks(["2026-11-15 Paid to Swiggy ₹100.00 UTR" + " " * 25_000 + "!"]) is not None
    assert _parse_multiline_bank_pdf_rows(["2026-11-15 " + "1" * 25_000 + "!"]) == []
    elapsed = time.perf_counter() - t0
    assert elapsed < 1.5, f"Potential ReDoS regression: adversarial batch took {elapsed:.2f}s"
