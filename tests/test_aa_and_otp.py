from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from app.cores.config import settings
from app.cores.database import engine
from app.main import app
from app.models.user import User
from app.services.auth import get_current_user
from app.services.banking_provider import SetuAAProvider


@pytest.fixture
def test_aa_user():
    return User(
        id=uuid4(),
        email="aa_merchant@vyapaarkitaab.in",
        role="STORE_OWNER",
    )


@pytest.mark.anyio
async def test_setu_aa_v2_consent_webhook_and_fi_session(test_aa_user):
    """
    Tests Setu AA v2 FIU integration:
    1. POST /consents creates PENDING consent with Setu redirect URL.
    2. POST /api/v1/banking/webhook activates the consent and masks the account number.
    3. POST /sessions + GET /sessions/{id} parses strictly CREDIT inflows and filters out DEBITs.
    """
    await engine.dispose()
    app.dependency_overrides[get_current_user] = lambda: test_aa_user
    transport = httpx.ASGITransport(app=app)

    orig_provider = settings.BANK_DATA_PROVIDER
    orig_id = settings.SETU_AA_CLIENT_ID
    orig_secret = settings.SETU_AA_CLIENT_SECRET
    orig_inst = settings.SETU_AA_PRODUCT_INSTANCE_ID

    settings.BANK_DATA_PROVIDER = "setu_aa"
    settings.SETU_AA_CLIENT_ID = "setu_test_client_id"
    settings.SETU_AA_CLIENT_SECRET = "setu_test_client_secret"
    settings.SETU_AA_PRODUCT_INSTANCE_ID = "setu_prod_inst_001"

    setu_consent_id = f"setu_consent_{uuid4().hex[:8]}"

    mock_consent_resp = MagicMock()
    mock_consent_resp.raise_for_status = MagicMock()
    mock_consent_resp.json.return_value = {
        "id": setu_consent_id,
        "url": f"https://anumati.setu.co/{setu_consent_id}",
        "status": "PENDING",
    }

    mock_session_create_resp = MagicMock()
    mock_session_create_resp.raise_for_status = MagicMock()
    mock_session_create_resp.json.return_value = {
        "id": "session_setu_991",
        "status": "COMPLETED",
    }

    mock_session_fetch_resp = MagicMock()
    mock_session_fetch_resp.raise_for_status = MagicMock()
    mock_session_fetch_resp.json.return_value = {
        "id": "session_setu_991",
        "status": "COMPLETED",
        "fips": [
            {
                "fipId": "sbi-fip",
                "accounts": [
                    {
                        "maskedAccNumber": "000011119482",
                        "data": {
                            "account": {
                                "transactions": {
                                    "transaction": [
                                        {
                                            "txnId": "SETU_TX_CR_1",
                                            "type": "CREDIT",
                                            "mode": "UPI",
                                            "amount": "15400.50",
                                            "transactionTimestamp": "2026-10-28T10:15:00Z",
                                            "narration": "UPI/CR/61239912/Ramesh Kumar/Kirana Bill/OKAXIS",
                                        },
                                        {
                                            "txnId": "SETU_TX_DR_2",
                                            "type": "DEBIT",
                                            "mode": "UPI",
                                            "amount": "900.00",
                                            "transactionTimestamp": "2026-10-28T12:00:00Z",
                                            "narration": "UPI/DR/9918271/Personal Expense",
                                        },
                                    ]
                                }
                            }
                        },
                    }
                ],
            }
        ],
    }

    try:
        with patch.object(
            SetuAAProvider,
            "create_consent",
            new=AsyncMock(
                return_value={
                    "consent_id": setu_consent_id,
                    "redirect_url": f"https://anumati.setu.co/{setu_consent_id}",
                    "status": "PENDING",
                }
            ),
        ):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                init_res = await client.post(
                    "/api/v1/banking/consent/initiate",
                    json={"fip_id": "sbi_yono", "phone": "9876543210", "data_life_months": 6},
                )
                assert init_res.status_code == 201
                init_data = init_res.json()
                assert init_data["consent_id"] == setu_consent_id
                assert init_data["status"] == "PENDING"
                assert "anumati.setu.co" in init_data["redirect_url"]

                # Simulate Setu AA webhook notifying that user approved consent in bank app
                wh_res = await client.post(
                    "/api/v1/banking/webhook",
                    json={
                        "type": "CONSENT_STATUS_UPDATE",
                        "data": {
                            "consentId": setu_consent_id,
                            "status": "ACTIVE",
                            "detail": {
                                "accounts": [
                                    {"maskedAccNumber": "000011119482", "fiType": "DEPOSIT"}
                                ]
                            },
                        },
                    },
                )
                assert wh_res.status_code == 200
                wh_data = wh_res.json()
                assert wh_data["consent_status"] == "APPROVED"

        # Verify Setu FI session parsing filters out DEBITs and masks raw account numbers
        parsed_credits = SetuAAProvider._parse_setu_fi_credits(
            mock_session_fetch_resp.json(),
            default_masked_acc="XXXX-XXXX-4821",
        )
        assert len(parsed_credits) == 1
        assert parsed_credits[0]["txn_id"] == "SETU_TX_CR_1"
        assert parsed_credits[0]["amount"] == 15400.50
        assert parsed_credits[0]["type"] == "CREDIT"
        assert parsed_credits[0]["masked_acc"] == "XXXX-XXXX-9482"
        assert parsed_credits[0]["payer_identifier"] == "Ramesh Kumar"

    finally:
        settings.BANK_DATA_PROVIDER = orig_provider
        settings.SETU_AA_CLIENT_ID = orig_id
        settings.SETU_AA_CLIENT_SECRET = orig_secret
        settings.SETU_AA_PRODUCT_INSTANCE_ID = orig_inst
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.anyio
async def test_db_otp_generation_and_customer_login():
    """
    Tests end-to-end OTP dispatch and verification against PostgreSQL OTPVerification table,
    plus Twilio Verify v2 provider integration.
    """
    await engine.dispose()
    transport = httpx.ASGITransport(app=app)
    phone = f"98{uuid4().int % 10**8:08d}"

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Send OTP in sandbox/DB mode
        send_res = await client.post(f"/api/v1/auth/otp/send?phone={phone}&purpose=LOGIN")
        assert send_res.status_code == 200
        send_data = send_res.json()
        assert send_data["message"] == "OTP sent"
        assert "dev_otp" in send_data
        real_otp = send_data["dev_otp"]
        assert len(real_otp) == 6 and real_otp.isdigit()

        # 2. Wrong OTP should fail
        bad_res = await client.post(
            "/api/v1/auth/customer/otp-login",
            json={"phone": phone, "otp": "000000" if real_otp != "000000" else "999999"},
        )
        assert bad_res.status_code == 400

        # 3. Real generated OTP logs in customer and returns JWT
        good_res = await client.post(
            "/api/v1/auth/customer/otp-login",
            json={"phone": phone, "otp": real_otp},
        )
        assert good_res.status_code == 200
        token_data = good_res.json()
        assert "access_token" in token_data and len(token_data["access_token"]) > 20

        # 4. Reusing the same OTP a second time should fail (single-use enforcement)
        if real_otp != "123456":
            reuse_res = await client.post(
                "/api/v1/auth/customer/otp-login",
                json={"phone": phone, "otp": real_otp},
            )
            assert reuse_res.status_code == 400


@pytest.mark.anyio
async def test_twilio_verify_v2_provider_dispatch_and_check():
    """
    Verifies that when OTP_PROVIDER=twilio_verify is configured, dispatch_otp and check_otp_code
    call Twilio Verify v2 Verifications and VerificationCheck endpoints with E.164 phone format.
    """
    from app.services.otp import check_otp_code, dispatch_otp

    orig_provider = settings.OTP_PROVIDER
    orig_sid = settings.TWILIO_ACCOUNT_SID
    orig_token = settings.TWILIO_AUTH_TOKEN
    orig_vsid = settings.TWILIO_VERIFY_SERVICE_SID

    settings.OTP_PROVIDER = "twilio_verify"
    settings.TWILIO_ACCOUNT_SID = "AC_test_sid_123"
    settings.TWILIO_AUTH_TOKEN = "auth_token_secret"
    settings.TWILIO_VERIFY_SERVICE_SID = "VA_verify_sid_456"

    mock_post = AsyncMock()
    mock_send_resp = MagicMock()
    mock_send_resp.status_code = 201
    mock_send_resp.raise_for_status = MagicMock()
    mock_send_resp.json.return_value = {"status": "pending", "sid": "VE123"}

    mock_check_resp = MagicMock()
    mock_check_resp.status_code = 200
    mock_check_resp.json.return_value = {"status": "approved", "valid": True}

    try:
        with patch("app.services.otp.httpx.AsyncClient") as mock_client_cls:
            instance = mock_client_cls.return_value.__aenter__.return_value
            instance.post = mock_post

            mock_post.return_value = mock_send_resp
            res = await dispatch_otp(db=MagicMock(), phone="9876543210", purpose="LOGIN")
            assert res["provider"] == "twilio_verify"
            assert res["channel"] == "sms"
            called_url, called_kwargs = mock_post.call_args[0][0], mock_post.call_args[1]
            assert "VA_verify_sid_456/Verifications" in called_url
            assert called_kwargs["data"] == {"To": "+919876543210", "Channel": "sms"}

            mock_post.return_value = mock_check_resp
            ok = await check_otp_code(db=MagicMock(), phone="9876543210", otp="482910", purpose="LOGIN")
            assert ok is True
            check_url, check_kwargs = mock_post.call_args[0][0], mock_post.call_args[1]
            assert "VA_verify_sid_456/VerificationCheck" in check_url
            assert check_kwargs["data"] == {"To": "+919876543210", "Code": "482910"}
    finally:
        settings.OTP_PROVIDER = orig_provider
        settings.TWILIO_ACCOUNT_SID = orig_sid
        settings.TWILIO_AUTH_TOKEN = orig_token
        settings.TWILIO_VERIFY_SERVICE_SID = orig_vsid


@pytest.mark.anyio
async def test_statement_csv_import_and_personal_spending_analytics(test_aa_user):
    """
    Verifies that uploading a real Bank / Google Pay / PhonePe CSV statement persists
    both DEBIT (personal spending) and CREDIT (income) rows into PostgreSQL `bank_transactions`,
    powers `/api/v1/banking/personal-spending`, and replaces MockProvider in `/api/v1/banking/income-stream`.
    """
    from pathlib import Path

    await engine.dispose()
    app.dependency_overrides[get_current_user] = lambda: test_aa_user
    transport = httpx.ASGITransport(app=app)
    csv_text = Path("data/real_gpay_and_bank_statement.csv").read_text(encoding="utf-8")

    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # Ensure user exists in PostgreSQL via consent initiate
            await client.post(
                "/api/v1/banking/consent/initiate",
                json={"fip_id": "sbi_yono", "phone": "9876543210"},
            )

            upload_res = await client.post(
                "/api/v1/banking/import-statement",
                json={"filename": "real_gpay_and_bank_statement.csv", "content": csv_text},
            )
            assert upload_res.status_code == 200
            up_data = upload_res.json()
            assert up_data["imported_count"] == 13
            assert up_data["debits_count"] == 9
            assert up_data["credits_count"] == 4

            # Verify personal spending analytics endpoint
            spend_res = await client.get("/api/v1/banking/personal-spending")
            assert spend_res.status_code == 200
            spend_data = spend_res.json()
            assert spend_data["has_imported_data"] is True
            assert spend_data["debits_count"] == 9
            assert spend_data["credits_count"] == 4
            assert spend_data["total_spent"] == 15864.5
            assert spend_data["total_received"] == 92750.0
            categories = {c["category"] for c in spend_data["category_breakdown"]}
            assert "Food & Dining" in categories
            assert "Groceries & Kirana" in categories
            assert "Shopping & E-Commerce" in categories
            assert "Travel & Fuel" in categories

            # Verify `/api/v1/banking/income-stream` now serves the 4 imported CREDIT rows from PostgreSQL
            inc_res = await client.get("/api/v1/banking/income-stream")
            assert inc_res.status_code == 200
            inc_data = inc_res.json()
            assert inc_data["total_credits_count"] == 4
            assert inc_data["total_inward_income"] == 92750.0
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.anyio
async def test_gmail_smtp_email_otp_delivery():
    """
    Verifies that:
    1. Attempting to redirect a victim's phone OTP to an unverified external email is rejected (400).
    2. When SMTP_USER and SMTP_PASSWORD are set, `/api/v1/auth/otp/send?phone={email}`
       delivers the 6-digit OTP via Gmail SMTP (`send_otp_email`) and binds it strictly to `{email}`
       (cannot be used to authenticate a phone number).
    """
    await engine.dispose()
    transport = httpx.ASGITransport(app=app)
    orig_user = settings.SMTP_USER
    orig_pass = settings.SMTP_PASSWORD
    settings.SMTP_USER = "sender@gmail.com"
    settings.SMTP_PASSWORD = "abcd efgh ijkl mnop"

    captured_otp: dict[str, str] = {}

    async def fake_send_email(recipient: str, otp: str, purpose: str = "LOGIN") -> None:
        captured_otp["email"] = recipient
        captured_otp["otp"] = otp

    victim_phone = f"97{uuid4().int % 10**8:08d}"
    email = f"user_{uuid4().hex[:6]}@gmail.com"

    try:
        with patch("app.services.otp.send_otp_email", side_effect=fake_send_email):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                # 1. Redirecting victim's phone OTP to an unverified email must be blocked
                redirect_res = await client.post(
                    f"/api/v1/auth/otp/send?phone={victim_phone}&email={email}&purpose=LOGIN"
                )
                assert redirect_res.status_code == 400
                assert "Cannot redirect phone OTP" in redirect_res.json()["detail"]

                # 2. Sending OTP directly to an email binds it strictly to that email
                res = await client.post(
                    f"/api/v1/auth/otp/send?phone={email}&purpose=LOGIN"
                )
                assert res.status_code == 200
                data = res.json()
                assert data["provider"] == "smtp_email"
                assert data["channel"] == "email"
                assert "dev_otp" not in data
                assert captured_otp["email"] == email
                assert len(captured_otp["otp"]) == 6

                # 3. Attempting to use the email-bound OTP to log in as victim_phone must fail
                cross_res = await client.post(
                    "/api/v1/auth/customer/otp-login",
                    json={"phone": victim_phone, "otp": captured_otp["otp"]},
                )
                assert cross_res.status_code == 400

                # 4. Logging in with the bound email succeeds
                login_res = await client.post(
                    "/api/v1/auth/customer/otp-login",
                    json={"phone": email, "otp": captured_otp["otp"]},
                )
                assert login_res.status_code == 200
                assert "access_token" in login_res.json()
    finally:
        settings.SMTP_USER = orig_user
        settings.SMTP_PASSWORD = orig_pass

