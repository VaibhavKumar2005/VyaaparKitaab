from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from app.cores.config import settings
from app.cores.database import SessionLocal, engine
from app.main import app
from app.models.banking_consent import BankTransaction
from app.models.business import Business, Customer, Product
from app.models.user import User
from app.services.auth import get_current_user
from app.services.banking_provider import SetuAAProvider
from sqlalchemy import select


@pytest.mark.anyio
async def test_multi_tenant_invoice_business_details_and_upi_vpa():
    await engine.dispose()
    owner_id = uuid4()
    customer_user_id = uuid4()
    owner = User(
        id=owner_id,
        email=f"nisha_{uuid4().hex[:6]}@elec.in",
        hashed_password="test_hash_value_123",
        role="STORE_OWNER",
        full_name="Nisha Gupta",
    )
    customer_phone = f"91{uuid4().int % 10**8:08d}"
    customer_user = User(
        id=customer_user_id,
        email=f"cust_{uuid4().hex[:6]}@gmail.com",
        phone=customer_phone,
        phone_verified=True,
        hashed_password="test_hash_value_123",
        role="CUSTOMER",
    )
    async with SessionLocal() as db:
        db.add(owner)
        db.add(customer_user)
        await db.flush()
        biz = Business(
            name="Nisha Electronics",
            owner_id=owner.id,
            gstin="27AABCN1234E1Z5",
            address="MG Road, Pune",
            phone="9988776655",
            upi_vpa="nisha.pay@okaxis",
        )
        db.add(biz)
        await db.flush()
        cust = Customer(name="Rohan Verma", phone=customer_phone, business_id=biz.id)
        prod = Product(name="LED Bulb 9W", selling_price=120.0, stock_qty=20, business_id=biz.id)
        db.add(cust)
        db.add(prod)
        await db.commit()
        await db.refresh(biz)
        await db.refresh(cust)
        await db.refresh(prod)

    transport = httpx.ASGITransport(app=app)
    app.dependency_overrides[get_current_user] = lambda: owner
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            inv_num = f"INV-NISHA-{uuid4().hex[:5]}"
            create_res = await client.post(
                "/api/v1/invoices",
                json={
                    "invoice_number": inv_num,
                    "business_id": str(biz.id),
                    "customer_id": str(cust.id),
                    "type": "SALE",
                    "status": "CONFIRMED",
                    "payment_method": "UPI",
                    "items": [{"product_id": str(prod.id), "quantity": 2, "unit_price": 120.0, "discount": 0.0}],
                },
            )
            assert create_res.status_code == 200
            inv_data = create_res.json()
            assert inv_data["store_name"] == "Nisha Electronics"
            assert inv_data["store_gstin"] == "27AABCN1234E1Z5"
            assert inv_data["store_upi_vpa"] == "nisha.pay@okaxis"

            order_res = await client.post(
                "/api/v1/payments/create-order",
                json={"invoice_id": inv_data["id"]},
            )
            assert order_res.status_code == 200
            order_data = order_res.json()
            assert "pa=nisha.pay%40okaxis" in (order_data["upi_intent"] or "")
            assert "pn=Nisha%20Electronics" in (order_data["upi_intent"] or "")

            upd_res = await client.put(
                f"/api/v1/businesses/{biz.id}",
                json={"upi_vpa": "nisha.store@ybl"},
            )
            assert upd_res.status_code == 200
            assert upd_res.json()["upi_vpa"] == "nisha.store@ybl"

            # Verify CSP permits Razorpay Checkout widget
            assert "https://checkout.razorpay.com" in order_res.headers.get("content-security-policy", "")

        # Customer portal sees real store identity on their bill
        app.dependency_overrides[get_current_user] = lambda: customer_user
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c_client:
            bills_res = await c_client.get("/api/v1/portal/my-bills")
            assert bills_res.status_code == 200
            bills = bills_res.json()
            matching = [b for b in bills if b["id"] == inv_data["id"]]
            assert len(matching) == 1
            assert matching[0]["store_name"] == "Nisha Electronics"
            assert matching[0]["store_upi_vpa"] == "nisha.store@ybl"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.anyio
async def test_honest_aa_disconnected_state_and_setu_polling():
    await engine.dispose()
    fresh_user = User(id=uuid4(), email=f"fresh_{uuid4().hex[:6]}@shop.in", role="STORE_OWNER")
    app.dependency_overrides[get_current_user] = lambda: fresh_user
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            inc_res = await client.get("/api/v1/banking/income-stream")
            assert inc_res.status_code == 200
            inc = inc_res.json()
            assert inc["is_connected"] is False
            assert inc["active_consent"] is None
            assert inc["total_credits_count"] == 0
            assert inc["security_metadata"]["active_fip"] == "Not connected yet"
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    # Setu AA requires real phone/vua and polls pending FI sessions cleanly
    orig_id = settings.SETU_AA_CLIENT_ID
    orig_secret = settings.SETU_AA_CLIENT_SECRET
    settings.SETU_AA_CLIENT_ID = "setu_id"
    settings.SETU_AA_CLIENT_SECRET = "setu_secret"
    try:
        provider = SetuAAProvider()
        with pytest.raises(ValueError):
            await provider.create_consent(phone="", vua=None)

        post_resp = MagicMock()
        post_resp.raise_for_status = MagicMock()
        post_resp.json.return_value = {"id": "sess_poll_1", "status": "PENDING"}

        pending_resp = MagicMock()
        pending_resp.raise_for_status = MagicMock()
        pending_resp.json.return_value = {"id": "sess_poll_1", "status": "PENDING"}

        done_resp = MagicMock()
        done_resp.raise_for_status = MagicMock()
        done_resp.json.return_value = {
            "id": "sess_poll_1",
            "status": "COMPLETED",
            "fips": [
                {
                    "accounts": [
                        {
                            "maskedAccNumber": "998877661234",
                            "data": {
                                "account": {
                                    "transactions": {
                                        "transaction": [
                                            {
                                                "txnId": "POLL_CR_1",
                                                "type": "CREDIT",
                                                "mode": "UPI",
                                                "amount": "550.00",
                                                "transactionTimestamp": "2026-11-10T10:00:00Z",
                                                "narration": "UPI/CR/551122/Aman/Payment/OKAXIS",
                                            }
                                        ]
                                    }
                                }
                            },
                        }
                    ]
                }
            ],
        }
        with patch("app.services.banking_provider.httpx.AsyncClient") as mock_cls, patch(
            "app.services.banking_provider.asyncio.sleep", new=AsyncMock()
        ):
            inst = mock_cls.return_value.__aenter__.return_value
            inst.post = AsyncMock(return_value=post_resp)
            inst.get = AsyncMock(side_effect=[pending_resp, done_resp])
            credits = await provider.create_and_fetch_session("c_1")
            assert len(credits) == 1
            assert credits[0]["txn_id"] == "POLL_CR_1"
            assert credits[0]["masked_acc"] == "XXXX-XXXX-1234"
    finally:
        settings.SETU_AA_CLIENT_ID = orig_id
        settings.SETU_AA_CLIENT_SECRET = orig_secret


@pytest.mark.anyio
async def test_csv_preamble_hardening_and_invoice_reconciliation():
    await engine.dispose()
    merchant = User(
        id=uuid4(),
        email=f"recon_{uuid4().hex[:6]}@shop.in",
        hashed_password="test_hash_value_123",
        role="STORE_OWNER",
    )
    async with SessionLocal() as db:
        db.add(merchant)
        await db.flush()
        biz = Business(name="Kaveri Mart", owner_id=merchant.id)
        db.add(biz)
        await db.flush()
        cust = Customer(name="Suresh Mehta", business_id=biz.id)
        prod = Product(name="Organic Honey", selling_price=500.0, stock_qty=10, business_id=biz.id)
        db.add(cust)
        db.add(prod)
        await db.commit()
        await db.refresh(biz)
        await db.refresh(cust)
        await db.refresh(prod)

    csv_with_preamble = (
        "HDFC Bank Statement Export\n"
        "Statement Date: 01-11-2026 to 18-11-2026\n"
        "Customer Description: Kaveri Mart Current Account\n\n"
        "Txn Date,Narration,Debit,Credit\n"
        "2026-11-15,UPI/CR/445566778899/Suresh Mehta/Bill 105/OKAXIS,,1050.00\n"
        "2026-11-16,UPI/DR/112233445566/Swiggy Order/OKICICI,320.00,"
    )

    transport = httpx.ASGITransport(app=app)
    app.dependency_overrides[get_current_user] = lambda: merchant
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            inv_res = await client.post(
                "/api/v1/invoices",
                json={
                    "invoice_number": f"INV-RECON-{uuid4().hex[:4]}",
                    "business_id": str(biz.id),
                    "customer_id": str(cust.id),
                    "type": "SALE",
                    "status": "CONFIRMED",
                    "tax_amount": 50.0,
                    "payment_method": "CREDIT",
                    "items": [{"product_id": str(prod.id), "quantity": 2, "unit_price": 500.0, "discount": 0.0}],
                },
            )
            assert inv_res.status_code == 200
            inv = inv_res.json()
            assert inv["total_amount"] == 1050.0
            assert inv["status"] == "CONFIRMED"

            up_res = await client.post(
                "/api/v1/banking/import-statement",
                json={"filename": "hdfc_real.csv", "content": csv_with_preamble},
            )
            assert up_res.status_code == 200
            assert up_res.json()["imported_count"] == 2
            assert up_res.json()["credits_count"] == 1
            assert up_res.json()["debits_count"] == 1

            spend_res = await client.get("/api/v1/banking/personal-spending")
            assert spend_res.status_code == 200
            for tx in spend_res.json()["transactions"]:
                assert tx["masked_acc"] != "XXXX-XXXX-4821"

            sug_res = await client.get("/api/v1/banking/reconcile/suggestions")
            assert sug_res.status_code == 200
            suggestions = sug_res.json()["suggestions"]
            assert len(suggestions) == 1
            assert suggestions[0]["invoice_id"] == inv["id"]
            assert suggestions[0]["confidence"] == "HIGH"

            match_res = await client.post(
                "/api/v1/banking/reconcile/match",
                json={"txn_id": suggestions[0]["txn_id"], "invoice_id": inv["id"]},
            )
            assert match_res.status_code == 200
            assert match_res.json()["reconciled"] is True
            assert match_res.json()["invoice_status"] == "PAID"

            # Reconciled transaction drops out of suggestions and stays idempotent
            sug_after = await client.get("/api/v1/banking/reconcile/suggestions")
            assert sug_after.status_code == 200
            assert sug_after.json()["count"] == 0

            # Force bank timestamp check works when DB row exists cleanly
            async with SessionLocal() as db:
                rows = (
                    await db.execute(select(BankTransaction).where(BankTransaction.user_id == merchant.id))
                ).scalars().all()
                assert len(rows) == 2
                assert all(isinstance(r.timestamp, datetime) for r in rows)
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.anyio
async def test_live_setu_consent_without_phone_returns_400_not_500():
    """Live Setu mode must reject a consent request lacking phone/VUA with a clear 400."""
    await engine.dispose()
    user = User(id=uuid4(), email=f"nophone_{uuid4().hex[:6]}@shop.in", role="STORE_OWNER")
    app.dependency_overrides[get_current_user] = lambda: user
    orig = (settings.BANK_DATA_PROVIDER, settings.SETU_AA_CLIENT_ID, settings.SETU_AA_CLIENT_SECRET)
    settings.BANK_DATA_PROVIDER = "setu_aa"
    settings.SETU_AA_CLIENT_ID = "setu_id"
    settings.SETU_AA_CLIENT_SECRET = "setu_secret"
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            res = await client.post("/api/v1/banking/consent/initiate", json={"fip_id": "sbi_yono", "phone": ""})
            assert res.status_code == 400
            assert "mobile number" in res.json()["detail"].lower()
    finally:
        settings.BANK_DATA_PROVIDER, settings.SETU_AA_CLIENT_ID, settings.SETU_AA_CLIENT_SECRET = orig
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.anyio
async def test_custom_gst_slabs_and_gstr1_json_export():
    """Verifies 0%/18% server-side GST slab calculation and GSTR-1 JSON export excluding drafts."""
    await engine.dispose()
    merchant = User(
        id=uuid4(),
        email=f"gst_{uuid4().hex[:6]}@shop.in",
        hashed_password="test_hash_value_123",
        role="STORE_OWNER",
    )
    async with SessionLocal() as db:
        db.add(merchant)
        await db.flush()
        biz = Business(name="Apex Hardware", owner_id=merchant.id, gstin="27AABCA9876E1Z2")
        db.add(biz)
        await db.flush()
        prod = Product(name="Drill Machine", selling_price=1000.0, stock_qty=10, business_id=biz.id)
        db.add(prod)
        await db.commit()
        await db.refresh(biz)
        await db.refresh(prod)

    app.dependency_overrides[get_current_user] = lambda: merchant
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            r18 = await client.post(
                "/api/v1/invoices",
                json={
                    "invoice_number": f"INV-18-{uuid4().hex[:4]}",
                    "business_id": str(biz.id),
                    "type": "SALE",
                    "status": "PAID",
                    "gst_rate": 0.18,
                    "payment_method": "UPI",
                    "items": [{"product_id": str(prod.id), "quantity": 1, "unit_price": 1000.0, "discount": 0.0}],
                },
            )
            assert r18.status_code == 200
            assert r18.json()["tax_amount"] == 180.0
            assert r18.json()["total_amount"] == 1180.0

            r0 = await client.post(
                "/api/v1/invoices",
                json={
                    "invoice_number": f"INV-0-{uuid4().hex[:4]}",
                    "business_id": str(biz.id),
                    "type": "SALE",
                    "status": "CONFIRMED",
                    "gst_rate": 0.0,
                    "payment_method": "CASH",
                    "items": [{"product_id": str(prod.id), "quantity": 1, "unit_price": 1000.0, "discount": 0.0}],
                },
            )
            assert r0.status_code == 200
            assert r0.json()["tax_amount"] == 0.0
            assert r0.json()["total_amount"] == 1000.0

            # Draft invoice must be excluded from GSTR-1 export
            await client.post(
                "/api/v1/invoices",
                json={
                    "invoice_number": f"INV-DR-{uuid4().hex[:4]}",
                    "business_id": str(biz.id),
                    "type": "SALE",
                    "status": "DRAFT",
                    "gst_rate": 0.18,
                    "items": [{"product_id": str(prod.id), "quantity": 1, "unit_price": 500.0, "discount": 0.0}],
                },
            )

            gstr = await client.get("/api/v1/invoices/export/gstr1")
            assert gstr.status_code == 200
            data = gstr.json()
            assert data["gstin"] == "27AABCA9876E1Z2"
            assert data["store_name"] == "Apex Hardware"
            assert data["summary"]["total_invoices"] == 2
            assert data["summary"]["taxable_value"] == 2000.0
            assert data["summary"]["total_tax"] == 180.0
            assert data["summary"]["cgst"] == 90.0
            assert data["summary"]["sgst"] == 90.0
            assert data["summary"]["invoice_value"] == 2180.0
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def _encrypt_pdf_with_gs(raw_pdf: bytes, user_password: str, owner_password: str) -> bytes | None:
    import shutil
    import subprocess
    import tempfile
    from pathlib import Path

    gs_bin = shutil.which("gs")
    if not gs_bin:
        return None
    with tempfile.TemporaryDirectory() as td:
        in_path = Path(td) / "plain.pdf"
        out_path = Path(td) / "locked.pdf"
        in_path.write_bytes(raw_pdf)
        proc = subprocess.run(
            [
                gs_bin,
                "-q",
                "-dNOPAUSE",
                "-dBATCH",
                "-sDEVICE=pdfwrite",
                f"-sUserPassword={user_password}",
                f"-sOwnerPassword={owner_password}",
                f"-sOutputFile={out_path}",
                str(in_path),
            ],
            capture_output=True,
            check=False,
        )
        assert proc.returncode == 0
        return out_path.read_bytes()


def test_real_indian_bank_csv_tsv_formats():
    """Verifies real-world HDFC (2-digit year + summary rows), ICICI ((INR) headers), and SBI TSV exports."""
    from app.services.statement_importer import parse_statement_bytes

    # 1. HDFC Bank CSV with preamble, 2-digit year DD/MM/YY, Withdrawal Amt./Deposit Amt., and summary rows
    hdfc_csv = (
        b"HDFC BANK LIMITED\n"
        b"Account Statement for 50100XXXX1234\n"
        b"Date,Narration,Chq./Ref.No.,Value Dt,Withdrawal Amt.,Deposit Amt.,Closing Balance\n"
        b"01/11/26,Opening Balance,,,, ,45000.00\n"
        b"02/11/26,UPI-SWIGGY-SWIGGY@AXISBANK-430612345678,0000430612345678,02/11/26,485.50,,44514.50\n"
        b"03/11/26,UPI-RAHUL VERMA-RAHUL@OKSBI-430798765432,0000430798765432,03/11/26,,2500.00,47014.50\n"
        b"30/11/26,Closing Balance,,,, ,47014.50\n"
    )
    hdfc_rows = parse_statement_bytes(hdfc_csv, "hdfc_nov26.csv")
    assert len(hdfc_rows) == 2
    assert hdfc_rows[0]["type"] == "DEBIT"
    assert hdfc_rows[0]["amount"] == 485.5
    assert hdfc_rows[0]["timestamp"].year == 2026
    assert hdfc_rows[0]["timestamp"].month == 11
    assert hdfc_rows[0]["timestamp"].day == 2
    assert hdfc_rows[1]["type"] == "CREDIT"
    assert hdfc_rows[1]["amount"] == 2500.0

    # 2. ICICI Bank CSV with "(INR )" parenthetical header suffixes
    icici_csv = (
        b"S No.,Value Date,Transaction Date,Cheque Number,Transaction Remarks,Withdrawal Amount (INR ),Deposit Amount (INR ),Balance (INR )\n"
        b"1,10/11/2026,10/11/2026,-,UPI/431400112233/METRO WHOLESALE/metrow@okicici,12400.00,0.00,87600.00\n"
        b"2,11/11/2026,11/11/2026,-,UPI/431500998877/SUNITA DEVI/sunita@ybl,0.00,3200.00,90800.00\n"
    )
    icici_rows = parse_statement_bytes(icici_csv, "icici_stmt.csv")
    assert len(icici_rows) == 2
    assert icici_rows[0]["type"] == "DEBIT" and icici_rows[0]["amount"] == 12400.0
    assert icici_rows[1]["type"] == "CREDIT" and icici_rows[1]["amount"] == 3200.0

    # 3. SBI NetBanking Tab-Separated (.tsv/.txt) export with DD-Mon-YYYY dates
    sbi_tsv = (
        b"Account Name\t: SHARMA KIRANA STORE\n"
        b"Txn Date\tValue Date\tDescription\tRef No./Cheque No.\tDebit\tCredit\tBalance\n"
        b"14-Nov-2026\t14-Nov-2026\tTO TRANSFER-UPI/DR/431811223344/TATA POWER/PAYTM\t431811223344\t1850.00\t\t52150.00\n"
        b"15-Nov-2026\t15-Nov-2026\tBY TRANSFER-UPI/CR/431955667788/AMIT KUMAR/OKHDFCBANK\t431955667788\t\t4100.00\t56250.00\n"
    )
    sbi_rows = parse_statement_bytes(sbi_tsv, "sbi_statement.tsv")
    assert len(sbi_rows) == 2
    assert sbi_rows[0]["type"] == "DEBIT" and sbi_rows[0]["amount"] == 1850.0
    assert sbi_rows[1]["type"] == "CREDIT" and sbi_rows[1]["amount"] == 4100.0


def test_real_indian_multiline_pdf_parsers():
    """Verifies PhonePe multi-line PDF blocks and SBI/HDFC multi-line PDF rows with closing balance."""
    from app.services.statement_importer import _parse_pdf_statement_text

    # 1. PhonePe PDF layout text
    phonepe_text = (
        "Transaction Statement for +919876543210\n"
        "Date                Transaction Details                          Type     Amount\n"
        "Nov 15, 2026        Paid to Swiggy Food Delivery                 DEBIT    ₹450.00\n"
        "08:30 PM            Transaction ID T2611152030123456789012\n"
        "                    UTR No. 432011223344\n"
        "Nov 16, 2026        Received from Vikram Singh                   CREDIT   ₹2,750.00\n"
        "11:15 AM            Transaction ID T2611161115987654321098\n"
        "                    UTR No. 432155667788\n"
    )
    pp_rows = _parse_pdf_statement_text(phonepe_text)
    assert len(pp_rows) == 2
    assert pp_rows[0]["type"] == "DEBIT" and pp_rows[0]["amount"] == 450.0
    assert "Swiggy" in pp_rows[0]["narration"]
    assert pp_rows[1]["type"] == "CREDIT" and pp_rows[1]["amount"] == 2750.0
    assert "Vikram Singh" in pp_rows[1]["narration"]

    # 2. Multi-line SBI/HDFC PDF layout with trailing Closing Balance (must pick txn amount, NOT balance)
    bank_pdf_text = (
        "STATE BANK OF INDIA - ACCOUNT STATEMENT\n"
        "12-11-2026  12-11-2026  TO TRANSFER-UPI/DR/431612345678/AMAZON\n"
        "                        INDIA/OKICICI/Thermal Paper           1,299.00   84,701.00\n"
        "13-11-2026  13-11-2026  BY TRANSFER-UPI/CR/431787654321/PRIYA\n"
        "                        NAIR/PAYTM/Monthly Grocery            3,450.00   88,151.00\n"
    )
    bank_rows = _parse_pdf_statement_text(bank_pdf_text)
    assert len(bank_rows) == 2
    assert bank_rows[0]["type"] == "DEBIT" and bank_rows[0]["amount"] == 1299.0
    assert bank_rows[1]["type"] == "CREDIT" and bank_rows[1]["amount"] == 3450.0


@pytest.mark.anyio
async def test_encrypted_pdf_statement_unlock_flow():
    """Encrypted bank PDF returns 422 asking for password, rejects wrong password, and imports with correct password."""
    import base64

    from app.services.statement_importer import build_sample_statement_pdf_bytes

    locked_bytes = _encrypt_pdf_with_gs(build_sample_statement_pdf_bytes(), "PAN1999", "OWNER1999")
    if locked_bytes is None:
        pytest.skip("Ghostscript (gs) not installed to synthesize encrypted PDF")
    locked_b64 = base64.b64encode(locked_bytes).decode("ascii")

    await engine.dispose()
    merchant = User(
        id=uuid4(),
        email=f"pdf_{uuid4().hex[:6]}@shop.in",
        hashed_password="test_hash_value_123",
        role="STORE_OWNER",
    )
    async with SessionLocal() as db:
        db.add(merchant)
        await db.commit()

    app.dependency_overrides[get_current_user] = lambda: merchant
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            # 1. Missing password -> HTTP 422 mentioning password
            r_locked = await client.post(
                "/api/v1/banking/import-statement",
                json={"filename": "hdfc_locked.pdf", "content_base64": locked_b64},
            )
            assert r_locked.status_code == 422
            assert "password" in r_locked.json()["detail"].lower()

            # 2. Wrong password -> HTTP 422
            r_wrong = await client.post(
                "/api/v1/banking/import-statement",
                json={"filename": "hdfc_locked.pdf", "content_base64": locked_b64, "pdf_password": "WRONG"},
            )
            assert r_wrong.status_code == 422

            # 3. Correct password -> HTTP 200 with all 12 rows imported
            r_ok = await client.post(
                "/api/v1/banking/import-statement",
                json={"filename": "hdfc_locked.pdf", "content_base64": locked_b64, "pdf_password": "PAN1999"},
            )
            assert r_ok.status_code == 200
            assert r_ok.json()["imported_count"] == 12
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_hindi_devanagari_bill_parser_and_handwriting_preprocessing():
    """Verifies Devanagari numerals (०-९), Hindi labels (कुल योग/दिनांक/नकद/बिल), and paper preprocessing."""
    from io import BytesIO

    from app.services.invoice_parser import normalize_devanagari_text, parse_marketplace_receipt_text
    from app.services.ocr import preprocess_invoice_image
    from PIL import Image, ImageDraw

    hindi_bill = (
        "शर्मा किराना स्टोर\n"
        "बिल सं.: HND-२०२६-१४\n"
        "दिनांक: १५-११-२०२६\n"
        "१. आटा 5kg रु.२२०.००\n"
        "२. चीनी 2kg रु.९०.००\n"
        "कुल योग: रु.३१०.००\n"
        "नकद भुगतान"
    )
    norm = normalize_devanagari_text(hindi_bill)
    assert "310.00" in norm
    parsed = parse_marketplace_receipt_text(hindi_bill)
    assert parsed["marketplace"] == "शर्मा किराना स्टोर"
    assert parsed["order_id"] == "HND-2026-14"
    assert parsed["amount"] == 310.0
    assert parsed["payment_method"] == "Cash"
    assert parsed["purchased_at"].year == 2026
    assert parsed["purchased_at"].month == 11
    assert parsed["purchased_at"].day == 15
    assert len(parsed["line_items"]) == 2
    assert "आटा" in parsed["line_items"][0]["description"]

    # Handwritten shadow/paper preprocessing works cleanly on synthetic camera bill image
    img = Image.new("RGB", (600, 400), color=(240, 232, 195))
    draw = ImageDraw.Draw(img)
    draw.text((30, 40), "Bill No: 108  Total: Rs 450.00", fill=(25, 25, 40))
    buf = BytesIO()
    img.save(buf, format="PNG")
    processed = preprocess_invoice_image(Image.open(BytesIO(buf.getvalue())), handwriting=True)
    assert processed.mode == "L"
    assert processed.size == (1200, 800)


@pytest.mark.anyio
async def test_ocr_capabilities_and_handwritten_hindi_vision_flow(monkeypatch):
    """Verifies /ocr-capabilities and handwritten Hindi receipt extraction (Gemini Vision + offline fallback)."""
    from io import BytesIO

    from app.cores.config import settings
    from PIL import Image, ImageDraw

    await engine.dispose()
    user = User(id=uuid4(), email=f"ocr_hi_{uuid4().hex[:6]}@shop.in", role="CUSTOMER")
    app.dependency_overrides[get_current_user] = lambda: user

    img = Image.new("RGB", (500, 200), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((20, 40), "Sharma Kirana\nBill No: 901\nTotal: Rs. 245.00", fill=(0, 0, 0))
    buf = BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    class _FakeResp:
        status_code = 200

        def json(self):
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": (
                                        "गुप्ता जनरल स्टोर\n"
                                        "बिल सं.: GGS-88\n"
                                        "दिनांक: 18-11-2026\n"
                                        "1. अरहर दाल 2kg ₹२६०.००\n"
                                        "कुल योग: ₹२६०.००\n"
                                        "नकद"
                                    )
                                }
                            ]
                        }
                    }
                ]
            }

    orig_key = settings.GEMINI_API_KEY
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            # 1. Capabilities endpoint without Gemini key
            settings.GEMINI_API_KEY = ""
            cap1 = await client.get("/api/v1/purchases/ocr-capabilities")
            assert cap1.status_code == 200
            assert cap1.json()["handwriting_vision_ready"] is False

            # 2. Handwritten mode with Gemini Vision enabled
            settings.GEMINI_API_KEY = "test-gemini-key"
            monkeypatch.setattr("app.services.ocr.httpx.post", lambda *a, **kw: _FakeResp())
            cap2 = await client.get("/api/v1/purchases/ocr-capabilities")
            assert cap2.status_code == 200
            assert cap2.json()["handwriting_vision_ready"] is True

            res_hw = await client.post(
                "/api/v1/purchases/ocr-invoice?lang=hin&handwriting=true",
                files={"file": ("parcha.png", png_bytes, "image/png")},
            )
            assert res_hw.status_code == 200
            data = res_hw.json()
            assert data["marketplace"] == "गुप्ता जनरल स्टोर"
            assert data["order_id"] == "GGS-88"
            assert data["amount"] == 260.0
            assert data["payment_method"] == "Cash"
            assert len(data["line_items"]) == 1

            # 3. Graceful fallback to offline Tesseract when GEMINI_API_KEY is unset
            settings.GEMINI_API_KEY = ""
            res_offline = await client.post(
                "/api/v1/purchases/ocr-invoice?lang=hin&handwriting=true",
                files={"file": ("parcha.png", png_bytes, "image/png")},
            )
            assert res_offline.status_code == 200
            assert res_offline.json()["amount"] == 245.0
    finally:
        settings.GEMINI_API_KEY = orig_key
        app.dependency_overrides.pop(get_current_user, None)
