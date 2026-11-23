import asyncio
import base64
import json
import os
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

os.environ.setdefault("DATABASE_URL", "postgresql://postgres@localhost:5432/vyaapardb")
os.environ.setdefault("ENV", "testing")

from app.cores.database import SessionLocal, engine, get_db
from app.main import app
from app.models.banking_consent import BankTransaction, PaymentWebhookEvent
from app.models.user import User
from app.services.auth import get_current_user
from app.services.statement_importer import parse_statement_bytes
from app.services.upi_bridge import (
    build_automation_templates,
    mint_scoped_ingest_token,
    parse_upi_alert_payload,
    scrub_sensitive_text,
    verify_bridge_token,
    verify_scoped_ingest_token_signature,
)


def test_scoped_ingest_token_sign_verify_and_tamper_rejection():
    uid = uuid4()
    token, jti = mint_scoped_ingest_token(uid)
    assert token.startswith("vk_upi_")

    parsed = verify_scoped_ingest_token_signature(token)
    assert parsed == (uid, jti)

    tampered = token[:-1] + ("0" if token[-1] != "0" else "1")
    assert verify_scoped_ingest_token_signature(tampered) is None
    assert verify_scoped_ingest_token_signature("invalid_token") is None


def test_parse_upi_alert_rejects_otp_pin_and_promo_spam():
    otp_res = parse_upi_alert_payload(
        app_package="com.android.mms",
        title="HDFC Bank",
        message="849201 is your OTP for Rs 5,000 txn. Do not share this code.",
    )
    assert otp_res["accepted"] is False
    assert otp_res["reason"] == "otp_or_security_message_ignored"

    pin_res = parse_upi_alert_payload(
        message="Enter your UPI PIN 445566 to authorize Rs 200 payment",
    )
    assert pin_res["accepted"] is False

    promo_res = parse_upi_alert_payload(
        message="Win up to ₹500 cashback on your next scratch card!",
    )
    assert promo_res["accepted"] is False


def test_scrub_sensitive_text_masks_accounts_cards_and_secrets():
    raw = "Debited Rs 450 from Account No 9182736455123456 paid to Swiggy. password=topsecret UTR 431789123456"
    scrubbed, masked_acc = scrub_sensitive_text(raw)
    assert "9182736455123456" not in scrubbed
    assert "topsecret" not in scrubbed
    assert masked_acc == "XXXX-XXXX-3456"
    assert "431789123456" in scrubbed


def test_parse_gpay_and_paytm_notifications_cleanly():
    gpay = parse_upi_alert_payload(
        app_package="com.google.android.apps.nbu.paisa.user",
        title="Paid ₹450.00 to Blue Tokai Coffee",
        message="Paid using HDFC Bank A/C 1122334455667788. UPI Ref: 431789123456",
        source_channel="android_notification",
    )
    assert gpay["accepted"] is True
    txn = gpay["transaction"]
    assert txn["app"] == "Google Pay"
    assert txn["type"] == "DEBIT"
    assert txn["amount"] == 450.0
    assert txn["category"] == "Food & Dining"
    assert txn["counterparty"] == "Blue Tokai Coffee"
    assert txn["txn_id"] == "431789123456"
    assert txn["masked_acc"] == "XXXX-XXXX-7788"
    assert "1122334455667788" not in txn["narration"]

    paytm = parse_upi_alert_payload(
        app_package="net.one97.paytm",
        title="Money Received! ₹1,250.00 credited",
        message="Received from Rahul Sharma (rahul@paytm) via Paytm UPI Ref 431711223344",
    )
    assert paytm["accepted"] is True
    ptxn = paytm["transaction"]
    assert ptxn["app"] == "Paytm"
    assert ptxn["type"] == "CREDIT"
    assert ptxn["amount"] == 1250.0
    assert ptxn["vpa"] == "rahul@paytm"
    assert ptxn["txn_id"] == "431711223344"


def test_parse_google_takeout_gpay_html():
    sample_html = """<!doctype html>
    <html><body>
      <div class="outer-cell">
        <div class="content-cell">
          Paid ₹450.00 to Blue Tokai Coffee using Bank Account XXXXXXXX4821<br>
          Nov 12, 2026, 2:14:05 PM IST
        </div>
        <div class="content-cell">
          <b>Details:</b> Completed · Transaction ID CICAgK123456
        </div>
      </div>
      <div class="outer-cell">
        <div class="content-cell">
          Received ₹1,200.00 from Ananya Verma<br>
          11 Nov 2026, 6:30:00 PM GMT+05:30
        </div>
        <div class="content-cell">
          <b>Details:</b> Completed · Transaction ID CICAgK998877
        </div>
      </div>
      <div class="outer-cell">
        <div class="content-cell">
          Paid ₹99.00 to Test FailedTxn<br>
          Nov 10, 2026, 1:00:00 PM IST
        </div>
        <div class="content-cell">
          <b>Details:</b> Failed · Transaction ID CICAgK000000
        </div>
      </div>
    </body></html>"""

    rows = parse_statement_bytes(sample_html.encode("utf-8"), filename="My Activity.html")
    assert len(rows) == 2
    assert rows[0]["type"] == "DEBIT"
    assert rows[0]["amount"] == 450.0
    assert rows[0]["app"] == "Google Pay"
    assert rows[0]["counterparty"] == "Blue Tokai Coffee"
    assert rows[0]["txn_id"] == "CICAgK123456"
    assert rows[0]["date"] == "2026-11-12"
    assert rows[1]["type"] == "CREDIT"
    assert rows[1]["amount"] == 1200.0
    assert rows[1]["date"] == "2026-11-11"


def test_build_automation_templates_exposes_header_and_apps_script():
    tpl = build_automation_templates("vk_upi_test.sig", "http://localhost:8000")
    assert tpl["header_name"] == "X-Ingest-Token"
    assert "com.google.android.apps.nbu.paisa.user (Google Pay)" in tpl["supported_packages"]
    assert "net.one97.paytm (Paytm)" in tpl["supported_packages"]
    assert "UrlFetchApp.fetch" in tpl["gmail_apps_script"]
    assert "X-Ingest-Token" in tpl["gmail_apps_script"]


class _FakeScalarResult:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class _FakeAsyncDB:
    def __init__(self, active_jti: str | None = None):
        self.active_jti = active_jti

    async def execute(self, *_args, **_kwargs):
        if self.active_jti is None:
            return _FakeScalarResult(None)
        rec = PaymentWebhookEvent(
            event_id="upi_bridge_cfg:fake",
            event_type="upi_bridge_config",
            payload=json.dumps({"active_jti": self.active_jti, "status": "ACTIVE"}),
            status="ACTIVE",
        )
        return _FakeScalarResult(rec)


def test_verify_bridge_token_checks_rotation_state():
    async def _run():
        uid = uuid4()
        old_token, old_jti = mint_scoped_ingest_token(uid)
        new_token, new_jti = mint_scoped_ingest_token(uid)

        db_with_new = _FakeAsyncDB(active_jti=new_jti)
        assert await verify_bridge_token(db_with_new, new_token) == uid
        assert await verify_bridge_token(db_with_new, old_token) is None
        assert old_jti != new_jti

    asyncio.run(_run())


def test_ingest_endpoint_rejects_query_token_and_missing_header():
    async def _override_db():
        yield _FakeAsyncDB(active_jti=None)

    async def _run():
        prev = app.dependency_overrides.copy()
        app.dependency_overrides[get_db] = _override_db
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
            ) as client:
                r_query = await client.post(
                    "/api/v1/banking/upi-bridge/ingest?token=vk_upi_leak",
                    json={"title": "Paid ₹10", "message": "Paid ₹10 to Tea"},
                )
                assert r_query.status_code == 400

                r_missing = await client.post(
                    "/api/v1/banking/upi-bridge/ingest",
                    json={"title": "Paid ₹10", "message": "Paid ₹10 to Tea"},
                )
                assert r_missing.status_code == 401

                r_bad = await client.post(
                    "/api/v1/banking/upi-bridge/ingest",
                    headers={"X-Ingest-Token": "vk_upi_forged.0000"},
                    json={"title": "Paid ₹10", "message": "Paid ₹10 to Tea"},
                )
                assert r_bad.status_code == 401

                r_oversized = await client.post(
                    "/api/v1/banking/upi-bridge/ingest",
                    headers={"X-Ingest-Token": "vk_upi_forged.0000"},
                    json={"title": "Paid ₹10", "message": "x" * 20000},
                )
                assert r_oversized.status_code == 422
        finally:
            app.dependency_overrides = prev

    asyncio.run(_run())


@pytest.mark.anyio
async def test_upi_bridge_end_to_end_real_postgres():
    """
    Full real-PostgreSQL lifecycle for zero-credential UPI Auto-Sync Bridge:
    1. Issue scoped vk_upi_... token via GET /upi-bridge/config.
    2. Ingest GPay Debit + Paytm Credit via X-Ingest-Token (no user JWT/password).
    3. Verify OTP blocker + raw 16-digit account masking + UTR deduplication in Postgres.
    4. Verify ingested txns appear in /personal-spending and /income-stream.
    5. Rotate token -> verify old token returns 401 and new token returns 200 in Postgres.
    6. Import real sample PDF & Google Takeout HTML via /import-statement into Postgres.
    """
    await engine.dispose()
    uid = uuid4()
    test_user = User(
        id=uid,
        email=f"upi_bridge_e2e_{uid.hex[:8]}@vyapaarkitaab.in",
        hashed_password="test_hashed_password_123",
        full_name="UPI Bridge Tester",
        role="STORE_OWNER",
        is_active=True,
    )
    async with SessionLocal() as session:
        session.add(test_user)
        await session.commit()

    prev = app.dependency_overrides.copy()
    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            # 1. Fetch bridge config & templates
            cfg_res = await client.get("/api/v1/banking/upi-bridge/config")
            assert cfg_res.status_code == 200
            cfg = cfg_res.json()
            assert cfg["status"] == "ACTIVE"
            token_v1 = cfg["ingest_token"]
            assert token_v1.startswith("vk_upi_")
            assert "UrlFetchApp.fetch" in cfg["templates"]["gmail_apps_script"]

            # 2. Simulate real webhook push WITHOUT user JWT (only X-Ingest-Token)
            app.dependency_overrides.pop(get_current_user, None)
            gpay_res = await client.post(
                "/api/v1/banking/upi-bridge/ingest",
                headers={"X-Ingest-Token": token_v1},
                json={
                    "source_channel": "android_notification",
                    "app_package": "com.google.android.apps.nbu.paisa.user",
                    "title": "Paid ₹450.00 to Blue Tokai Coffee",
                    "message": "Paid via HDFC Bank A/C 9988776655443322. UPI Ref: 431789123456",
                },
            )
            assert gpay_res.status_code == 200
            assert gpay_res.json()["status"] == "ingested"

            paytm_res = await client.post(
                "/api/v1/banking/upi-bridge/ingest",
                headers={"X-Ingest-Token": token_v1},
                json={
                    "source_channel": "android_notification",
                    "app_package": "net.one97.paytm",
                    "title": "Money Received! ₹1,250.00 credited",
                    "message": "Received from Rahul Sharma (rahul@paytm) via Paytm UPI Ref 431711223344",
                },
            )
            assert paytm_res.status_code == 200
            assert paytm_res.json()["transaction"]["type"] == "CREDIT"

            otp_res = await client.post(
                "/api/v1/banking/upi-bridge/ingest",
                headers={"X-Ingest-Token": token_v1},
                json={
                    "source_channel": "android_sms",
                    "title": "HDFC Bank",
                    "message": "912844 is your OTP for Rs 4,500 transaction. Do not share OTP.",
                },
            )
            assert otp_res.status_code == 200
            assert otp_res.json()["status"] == "ignored"
            assert otp_res.json()["imported_count"] == 0

            # Duplicate UTR replay must remain idempotent (still 2 DB rows, not 3)
            dup_res = await client.post(
                "/api/v1/banking/upi-bridge/ingest",
                headers={"X-Ingest-Token": token_v1},
                json={
                    "source_channel": "gmail_apps_script",
                    "app_package": "gmail_apps_script",
                    "title": "Paid ₹450.00 to Blue Tokai Coffee",
                    "message": "Paid via HDFC Bank. UPI Ref: 431789123456",
                },
            )
            assert dup_res.status_code == 200

            async with SessionLocal() as verify_sess:
                db_txns = (
                    await verify_sess.execute(select(BankTransaction).where(BankTransaction.user_id == uid))
                ).scalars().all()
                assert len(db_txns) == 2
                for row in db_txns:
                    assert "9988776655443322" not in row.narration
                    assert "OTP" not in row.narration.upper()

            # 3. Verify analytics & rotate token under authenticated user
            app.dependency_overrides[get_current_user] = lambda: test_user
            spending_res = await client.get("/api/v1/banking/personal-spending")
            assert spending_res.status_code == 200
            spending = spending_res.json()
            assert spending["credits_count"] >= 1
            assert spending["debits_count"] >= 1
            assert spending["total_spent"] >= 450.0
            assert spending["total_received"] >= 1250.0

            income_res = await client.get("/api/v1/banking/income-stream")
            assert income_res.status_code == 200

            rot_res = await client.post("/api/v1/banking/upi-bridge/rotate-token")
            assert rot_res.status_code == 200
            token_v2 = rot_res.json()["ingest_token"]
            assert token_v2 != token_v1

            app.dependency_overrides.pop(get_current_user, None)
            old_try = await client.post(
                "/api/v1/banking/upi-bridge/ingest",
                headers={"X-Ingest-Token": token_v1},
                json={"title": "Paid ₹99 to Chai", "message": "Paid ₹99 to Chai"},
            )
            assert old_try.status_code == 401

            new_try = await client.post(
                "/api/v1/banking/upi-bridge/ingest",
                headers={"X-Ingest-Token": token_v2},
                json={"title": "Paid ₹99 to Chai Point", "message": "Paid via PhonePe UPI Ref 431755667788"},
            )
            assert new_try.status_code == 200
            assert new_try.json()["status"] == "ingested"

            # 4. Real Sample PDF download + upload import into Postgres
            app.dependency_overrides[get_current_user] = lambda: test_user
            pdf_dl = await client.get("/api/v1/banking/sample-statement.pdf")
            assert pdf_dl.status_code == 200
            assert pdf_dl.content.startswith(b"%PDF-1.4")

            pdf_import = await client.post(
                "/api/v1/banking/import-statement",
                json={
                    "filename": "realistic_upi_bank_statement.pdf",
                    "content_base64": base64.b64encode(pdf_dl.content).decode("ascii"),
                },
            )
            assert pdf_import.status_code == 200
            assert pdf_import.json()["imported_count"] >= 10

            # 5. Real Google Takeout HTML upload into Postgres
            takeout_html = (
                "<!doctype html><html><body>"
                "<div>Paid ₹720.00 to Zomato using Bank Account XXXXXXXX4821<br>"
                "Nov 13, 2026, 1:15:00 PM IST<br>Details: Completed · Transaction ID TAKEOUT720</div>"
                "<div>Paid ₹10.00 to Failed Test<br>Nov 13, 2026<br>Details: Failed · Transaction ID FAIL10</div>"
                "</body></html>"
            )
            html_import = await client.post(
                "/api/v1/banking/import-statement",
                json={"filename": "My Activity.html", "content": takeout_html},
            )
            assert html_import.status_code == 200
            assert html_import.json()["imported_count"] == 1

            clr_res = await client.delete("/api/v1/banking/transactions")
            assert clr_res.status_code == 200
    finally:
        app.dependency_overrides = prev
        await engine.dispose()
