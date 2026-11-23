import os
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/vyaapardb")
os.environ.setdefault("ENV", "testing")

from app.cores.database import SessionLocal, engine
from app.main import app
from app.models.business import Business, Customer, Product
from app.models.user import User
from app.services.auth import get_current_user
from app.services.classifier import build_category_tree, classify_hierarchical
from app.services.otp import dispatch_otp


def test_hierarchical_classifier_rules_and_ml_fallback() -> None:
    """Verify deterministic Indian MSME taxonomy + small-data ML prototype fallback."""
    assert classify_hierarchical("Blinkit Aashirvaad Atta 10kg", "Sharma Kirana")[:2] == ("Food", "Grocery")
    assert classify_hierarchical("Swiggy dinner order", "Swiggy")[:2] == ("Food", "Delivery")
    assert classify_hierarchical("Udupi Dosa Restaurant meal")[:2] == ("Food", "Restaurants")
    assert classify_hierarchical("Croma Sony Headphones", "Croma")[:2] == ("Shopping", "Electronics")
    assert classify_hierarchical("Myntra Cotton Kurta", "Myntra")[:2] == ("Shopping", "Clothing")
    assert classify_hierarchical("IndianOil Petrol Pump 500")[:2] == ("Transport", "Fuel")
    assert classify_hierarchical("Uber airport cab ride")[:2] == ("Transport", "Cab")
    assert classify_hierarchical("Apollo Pharmacy tablets")[:2] == ("Health & Medical", "Pharmacy & Medicines")
    assert classify_hierarchical("BESCOM monthly power bill")[:2] == ("Utilities & Bills", "Electricity & Power")

    # Small-data ML prototype fallback for unseen merchant phrasing
    cat, sub, src = classify_hierarchical("local market fresh flour staples")
    assert (cat, sub) == ("Food", "Grocery")
    assert src == "prototype_ml"

    nested, tree = build_category_tree(
        [
            {"category": "Food", "subcategory": "Grocery", "amount": 420.0},
            {"category": "Food", "subcategory": "Delivery", "amount": 180.0},
            {"category": "Transport", "subcategory": "Cab", "amount": 150.0},
        ]
    )
    assert nested == {"Food": {"Grocery": 420.0, "Delivery": 180.0}, "Transport": {"Cab": 150.0}}
    assert tree[0]["category"] == "Food"
    assert tree[0]["total_amount"] == 600.0
    assert [s["subcategory"] for s in tree[0]["subcategories"]] == ["Grocery", "Delivery"]


@pytest.mark.anyio
async def test_unified_store_to_customer_flow_notifications_otp_and_assistant() -> None:
    """
    End-to-end integration against real PostgreSQL:
      1. Store creates confirmed Grocery bill with ₹50 discount for verified customer.
      2. Unified transaction + initial unread customer notification are generated automatically.
      3. Customer pays bill with Transaction OTP enforcement (invalid rejected, valid succeeds).
      4. Customer logs external PersonalPurchase + Statement CSV + thin UPI Bridge structured event.
      5. Unified ledger (/transactions/unified), /dashboard/customer/me, /dashboard/store,
         and /ai/assistant return accurate normalized multi-source analytics.
    """
    await engine.dispose()

    cust_phone = f"+9197{uuid4().int % 10**8:08d}"
    owner = User(
        id=uuid4(),
        email=f"store_owner_{uuid4().hex[:6]}@vk.in",
        role="STORE_OWNER",
        hashed_password="hash",
        full_name="Rajendra Kirana",
    )
    customer_user = User(
        id=uuid4(),
        email=f"cust_{uuid4().hex[:6]}@vk.in",
        phone=cust_phone,
        phone_verified=True,
        role="CUSTOMER",
        hashed_password="hash",
        full_name="Verified Buyer",
    )
    stranger = User(
        id=uuid4(),
        email=f"stranger_{uuid4().hex[:6]}@vk.in",
        phone=f"+9191{uuid4().int % 10**8:08d}",
        phone_verified=True,
        role="CUSTOMER",
        hashed_password="hash",
    )

    biz = Business(id=uuid4(), name="Sharma Kirana & General Store", owner_id=owner.id)
    crm_customer = Customer(id=uuid4(), name="Verified Buyer", phone=cust_phone, business_id=biz.id)
    atta = Product(
        id=uuid4(),
        name="Aashirvaad Atta 10kg",
        sku=f"SKU-{uuid4().hex[:6]}",
        selling_price=450.0,
        cost_price=400.0,
        stock_qty=30.0,
        business_id=biz.id,
    )

    async with SessionLocal() as s:
        s.add_all([owner, customer_user, stranger])
        await s.flush()
        s.add(biz)
        await s.flush()
        s.add_all([crm_customer, atta])
        await s.commit()

    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Store owner creates CONFIRMED bill with ₹50 discount
            app.dependency_overrides[get_current_user] = lambda: owner
            inv_res = await client.post(
                "/api/v1/invoices",
                json={
                    "invoice_number": f"INV-UNI-{uuid4().hex[:6].upper()}",
                    "business_id": str(biz.id),
                    "customer_id": str(crm_customer.id),
                    "type": "SALE",
                    "status": "CONFIRMED",
                    "discount_amount": 50.0,
                    "tax_amount": 1.0,
                    "items": [
                        {
                            "product_id": str(atta.id),
                            "quantity": 2,
                            "unit_price": 450.0,
                            "discount": 0.0,
                        }
                    ],
                },
            )
            assert inv_res.status_code == 200
            invoice = inv_res.json()
            # Subtotal 900 - 50 discount = 850; + 5% GST (42.5) = 892.50
            assert invoice["total_amount"] == 892.5

            # 2. Customer checks automatic notification & creates OTP-protected payment
            app.dependency_overrides[get_current_user] = lambda: customer_user
            notifs_res = await client.get("/api/v1/portal/notifications")
            assert notifs_res.status_code == 200
            notifs = notifs_res.json()
            assert len(notifs) >= 1
            first_notif = notifs[0]
            assert first_notif["category"] == "Food"
            assert first_notif["subcategory"] == "Grocery"
            assert first_notif["discount_amount"] == 50.0
            assert first_notif["is_read"] is False

            # Mark notification read
            read_res = await client.post(f"/api/v1/portal/notifications/{first_notif['id']}/read")
            assert read_res.status_code == 200
            assert read_res.json()["updated"] == 1

            # Create gateway order
            ord_res = await client.post(
                "/api/v1/payments/create-order",
                json={"invoice_id": invoice["id"]},
            )
            assert ord_res.status_code == 200
            order_id = ord_res.json()["order_id"]

            # Generate real TRANSACTION OTP in PostgreSQL
            async with SessionLocal() as otp_db:
                otp_dispatch = await dispatch_otp(otp_db, cust_phone, purpose="TRANSACTION")
                dev_otp = otp_dispatch["dev_otp"]

            pay_id = f"pay_otp_{uuid4().hex[:8]}"
            bad_verify = await client.post(
                "/api/v1/payments/verify",
                json={
                    "invoice_id": invoice["id"],
                    "order_id": order_id,
                    "payment_id": pay_id,
                    "signature": "sandbox_valid",
                    "require_otp": True,
                    "otp_code": "000000",
                },
            )
            assert bad_verify.status_code == 400

            good_verify = await client.post(
                "/api/v1/payments/verify",
                json={
                    "invoice_id": invoice["id"],
                    "order_id": order_id,
                    "payment_id": pay_id,
                    "signature": "sandbox_valid",
                    "require_otp": True,
                    "otp_code": dev_otp,
                },
            )
            assert good_verify.status_code == 200
            assert good_verify.json()["invoice_status"] == "PAID"

            # Verify post-payment confirmation notification created
            notifs_after = (await client.get("/api/v1/portal/notifications")).json()
            assert any("Payment Confirmed" in n["title"] for n in notifs_after)

            # 3. Customer adds PersonalPurchase + Statement CSV + Thin UPI Bridge structured event
            purch_res = await client.post(
                "/api/v1/purchases",
                json={
                    "marketplace": "Amazon",
                    "category": "Electronics",
                    "amount": 1200.0,
                    "purchased_at": datetime.now(UTC).isoformat(),
                    "order_id": f"404-{uuid4().hex[:8]}",
                    "items_note": "Sony wireless earbuds",
                    "payment_method": "UPI (Google Pay)",
                },
            )
            assert purch_res.status_code == 201

            csv_content = "Date,Narration,Debit,Credit,TxnID\n2026-11-10,UPI/DR/77112233/SWIGGY/HDFC/swiggy@okhdfcbank,350.00,,SWG77112233\n"
            imp_res = await client.post(
                "/api/v1/banking/import-statement",
                json={"filename": "gpay.csv", "content": csv_content},
            )
            assert imp_res.status_code == 200
            assert imp_res.json()["imported_count"] == 1

            cfg_res = await client.get("/api/v1/banking/upi-bridge/config")
            assert cfg_res.status_code == 200
            ingest_token = cfg_res.json()["ingest_token"]

            bridge_res = await client.post(
                "/api/v1/banking/upi-bridge/ingest",
                headers={"X-Ingest-Token": ingest_token},
                json={
                    "source_channel": "ios_shortcut",
                    "amount": 220.0,
                    "direction": "DEBIT",
                    "counterparty": "Uber India",
                    "category": "Transport",
                    "subcategory": "Cab",
                    "txn_id": f"UBR{uuid4().hex[:8]}",
                },
            )
            assert bridge_res.status_code == 200
            assert bridge_res.json()["status"] == "ingested"
            assert bridge_res.json()["transaction"]["subcategory"] == "Cab"

            # 4. Query unified ledger and verify ALL 4 channels unified cleanly
            uni_res = await client.get("/api/v1/transactions/unified?view=customer")
            assert uni_res.status_code == 200
            uni_data = uni_res.json()
            assert uni_data["total_count"] == 4
            assert uni_data["total_discount_saved"] == 50.0
            assert uni_data["nested_summary"]["Food"]["Grocery"] == 892.5
            assert uni_data["nested_summary"]["Food"]["Delivery"] == 350.0
            assert uni_data["nested_summary"]["Shopping"]["Electronics"] == 1200.0
            assert uni_data["nested_summary"]["Transport"]["Cab"] == 220.0

            # Customer hierarchical dashboard endpoint must match unified summary
            dash_cust = (await client.get("/api/v1/dashboard/customer/me")).json()
            assert dash_cust["summary"]["Food"]["Grocery"] == 892.5
            assert dash_cust["summary"]["Transport"]["Cab"] == 220.0

            # 5. Query Natural Language Financial Assistant
            ai_food = await client.post(
                "/api/v1/ai/assistant",
                json={"question": "How much did I spend on food this month?"},
            )
            assert ai_food.status_code == 200
            food_ans = ai_food.json()
            assert food_ans["intent"] == "category_spend"
            assert food_ans["metrics"]["total_amount"] == 1242.5
            assert "Grocery" in food_ans["answer"]

            ai_disc = await client.post(
                "/api/v1/ai/assistant",
                json={"question": "How much discount did I save?"},
            )
            assert ai_disc.status_code == 200
            assert ai_disc.json()["metrics"]["total_discount_saved"] == 50.0
            assert "50.00" in ai_disc.json()["answer"]

            # 6. Verify strict isolation for stranger
            app.dependency_overrides[get_current_user] = lambda: stranger
            assert (await client.get("/api/v1/portal/notifications")).json() == []
            assert (await client.get("/api/v1/transactions/unified?view=customer")).json()["total_count"] == 0
            assert (await client.get(f"/api/v1/dashboard/customer/{customer_user.id}")).status_code == 403

            # 7. Store side dashboard & unified store view
            app.dependency_overrides[get_current_user] = lambda: owner
            store_dash = (await client.get("/api/v1/dashboard/store")).json()
            assert store_dash["totalDiscountsGiven"] >= 50.0
            assert any(c["category"] == "Food" for c in store_dash["categoryBreakdown"])
            store_uni = (await client.get("/api/v1/transactions/unified?view=store")).json()
            assert store_uni["total_count"] >= 1
            assert store_uni["total_discount_saved"] >= 50.0
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        await engine.dispose()

def test_indian_gst_invoice_parser_and_image_preprocessing():
    from app.services.invoice_parser import parse_marketplace_receipt_text, validate_gstin
    from app.services.ocr import preprocess_invoice_image
    from PIL import Image

    assert validate_gstin("27AAPFU0939F1ZV") is True
    assert validate_gstin("27AAPFU0939F1Z0") is False

    gst_bill = """
    Sharma Kirana & General Store
    GSTIN: 27AAPFU0939F1ZV
    Tax Invoice No: INV-2026-1084
    Date: 15-11-2026
    1. Aashirvaad Atta 5kg HSN 1101 x 2 ₹490.00
    2. Amul Taaza Milk 1L HSN 0401 x 2 ₹140.00
    CGST @ 2.5%: ₹15.75
    SGST @ 2.5%: ₹15.75
    Discount: ₹31.50
    Grand Total: ₹630.00
    Paid via PhonePe UPI
    """
    parsed = parse_marketplace_receipt_text(gst_bill)
    assert parsed["marketplace"] == "Sharma Kirana & General Store"
    assert parsed["order_id"] == "INV-2026-1084"
    assert parsed["gstin"] == "27AAPFU0939F1ZV"
    assert parsed["gstin_valid"] is True
    assert parsed["tax_amount"] == 31.5
    assert parsed["discount_amount"] == 31.5
    assert parsed["amount"] == 630.0
    assert parsed["category"] == "Food"
    assert parsed["subcategory"] == "Grocery"
    assert parsed["payment_method"] == "UPI (PhonePe)"
    assert len(parsed["line_items"]) == 2
    assert parsed["line_items"][0]["hsn_code"] == "1101"

    raw_img = Image.new("RGB", (400, 200), color=(240, 240, 240))
    proc_img = preprocess_invoice_image(raw_img)
    assert proc_img.mode == "L"
    assert proc_img.size == (800, 400)


def test_invoice_parser_adversarial_and_edge_cases():
    from app.services.invoice_parser import parse_marketplace_receipt_text

    # 1. "order with us" must NOT invent order_id="with" or marketplace="Amazon"
    r1 = parse_marketplace_receipt_text("Thank you for your order with us. Total Rs. 500")
    assert r1["marketplace"] == "Unknown Merchant"
    assert r1["order_id"] is None
    assert r1["amount"] == 500.0
    assert r1["payment_method"] is None
    assert r1["confidence"] == "MEDIUM"

    # 2. "Receipt sent to your email" must NOT invent marketplace="your email" or order_id="sent"
    r2 = parse_marketplace_receipt_text("Receipt sent to your email. Amount paid Rs. 250")
    assert r2["marketplace"] == "Unknown Merchant"
    assert r2["order_id"] is None
    assert r2["amount"] == 250.0
    assert r2["payment_method"] is None
    assert r2["confidence"] == "MEDIUM"

    # 3. CGST/SGST rate without '@' must skip the percentage rate (2.5%) and sum 15.75 + 15.75 = 31.5
    r3 = parse_marketplace_receipt_text(
        "Ramesh Traders\nCGST 2.5% 15.75\nSGST 2.5% 15.75\nGrand Total: Rs. 661.50"
    )
    assert r3["marketplace"] == "Ramesh Traders"
    assert r3["order_id"] is None
    assert r3["tax_amount"] == 31.5
    assert r3["amount"] == 661.5
    assert r3["payment_method"] is None

    # 4. Percentage-only discount ("Discount 10% applied") must NOT be read as Rs. 10.0
    r4 = parse_marketplace_receipt_text("Big Bazaar\nDiscount 10% applied\nTotal: Rs. 900")
    assert r4["marketplace"] == "Big Bazaar"
    assert r4["discount_amount"] == 0.0
    assert r4["amount"] == 900.0

    # 5. Discount with both rate and rupee value ("Discount (10%): Rs. 90.00") extracts Rs. 90.0
    r5 = parse_marketplace_receipt_text("Big Bazaar\nDiscount (10%): Rs. 90.00\nTotal: Rs. 810.00")
    assert r5["marketplace"] == "Big Bazaar"
    assert r5["discount_amount"] == 90.0
    assert r5["amount"] == 810.0

    # 6. Bill with no payment hint returns payment_method=None instead of guessing Google Pay
    r6 = parse_marketplace_receipt_text("Local Store\nBill No: B-77\nTotal: Rs. 120")
    assert r6["marketplace"] == "Local Store"
    assert r6["order_id"] == "B-77"
    assert r6["amount"] == 120.0
    assert r6["payment_method"] is None
    assert r6["confidence"] == "HIGH"

    # 7. Bare amount with no merchant hint returns "Unknown Merchant", not "Amazon"
    r7 = parse_marketplace_receipt_text("Total: Rs. 300")
    assert r7["marketplace"] == "Unknown Merchant"
    assert r7["order_id"] is None
    assert r7["amount"] == 300.0
    assert r7["payment_method"] is None


@pytest.mark.anyio
async def test_save_ocr_purchase_respects_detected_fields(monkeypatch):
    await engine.dispose()
    user = User(
        id=uuid4(),
        email=f"ocr_save_{uuid4().hex[:6]}@test.in",
        hashed_password="x",
        role="CUSTOMER",
    )
    async with SessionLocal() as session:
        session.add(user)
        await session.commit()

    bill_no = f"BILL-{uuid4().hex[:6].upper()}9"
    monkeypatch.setattr(
        "app.routers.purchases.extract_invoice_text",
        lambda image_bytes, content_type: (
            f"Sharma Kirana Store\n"
            f"Bill No: {bill_no}\n"
            f"1. Aashirvaad Atta 5kg ₹245.00\n"
            f"Total: ₹245.00\n"
            f"Paid via Cash"
        ),
    )

    app.dependency_overrides[get_current_user] = lambda: user
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                "/api/v1/purchases/ocr-invoice/save",
                files={"file": ("kirana_bill.png", b"fake-img", "image/png")},
            )
            assert res.status_code == 201
            saved = res.json()
            assert saved["marketplace"] == "Sharma Kirana Store"
            assert saved["order_id"] == bill_no
            assert saved["category"] == "Food"
            assert saved["payment_method"] == "Cash"
            assert saved["amount"] == 245.0
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        await engine.dispose()


@pytest.mark.anyio
async def test_production_qa_suite_gst_ocr_refunds_bola_and_readme_ai(monkeypatch):
    """
    Production QA suite covering:
    - QA-01: Zero-amount OCR receipt save returns 422 (never 500)
    - QA-02: Final payable total beats Subtotal / MRP Total / Total Items / lakh formatting
    - QA-03: CREDIT refunds classify as Financial & Transfers > Refund & Cashback and do not inflate spend
    - QA-04: All README AI prompts (profit, restock, spending) return real PostgreSQL answers
    - QA-07: CSV TxnID preservation, slash-format 12-digit UTR extraction, 2-digit year dates
    - QA-08 & OWASP BOLA: GSTIN state bounds (00 invalid), CANCELLED invoice exclusion, UUID 422, BOLA 403/404
    """
    from app.services.invoice_parser import parse_marketplace_receipt_text, validate_gstin
    from app.services.statement_importer import parse_statement_bytes

    # --- QA-02 & QA-07 & QA-08 (Parser & GSTIN state code bounds) ---
    assert validate_gstin("00AAAAA0000A1ZI") is False
    assert validate_gstin("27AAPFU0939F1ZV") is True

    r_sub = parse_marketplace_receipt_text(
        "Ramesh Traders\nBill No: B-101\nSubtotal: ₹1,000.00\nDiscount: ₹100.00\nGrand Total: ₹900.00"
    )
    assert r_sub["amount"] == 900.0
    assert r_sub["discount_amount"] == 100.0

    r_mrp = parse_marketplace_receipt_text(
        "Apollo Pharmacy\nBill #AP-19\nMRP Total: ₹600.00\nAmount Paid: ₹510.00"
    )
    assert r_mrp["amount"] == 510.0

    r_lakh = parse_marketplace_receipt_text(
        "Sharma Kirana Store\nInvoice No: INV-2026-901\nTotal Items: 12\nGrand Total: ₹1,24,500.50"
    )
    assert r_lakh["amount"] == 124500.5

    r_utr_date = parse_marketplace_receipt_text(
        "Paid ₹500 to Raju Tea Stall\nUPI/DR/431899887766/RAJU/HDFC\nDate: 16/11/26"
    )
    assert r_utr_date["marketplace"] == "Raju Tea Stall"
    assert r_utr_date["order_id"] == "UPI-431899887766"
    assert r_utr_date["purchased_at"].strftime("%Y-%m-%d") == "2026-11-16"

    # CSV TxnID header preservation & CREDIT refund classification
    csv_bytes = (
        b"Date,Narration,Amount,Type,TxnID\n"
        b"16/11/2026,\"UPI/DR/431900112233/SWIGGY/HDFC/swiggy@okhdfcbank\",350.00,DEBIT,TXN9001\n"
        b"16/11/2026,\"UPI/CR/431900112234/REFUND SWIGGY/HDFC\",350.00,CREDIT,TXN9002\n"
    )
    parsed_csv = parse_statement_bytes(csv_bytes, "refund_check.csv")
    assert len(parsed_csv) == 2
    assert parsed_csv[0]["txn_id"] == "TXN9001"
    assert parsed_csv[1]["txn_id"] == "TXN9002"
    assert parsed_csv[1]["category"] == "Refund & Cashback"
    assert parsed_csv[1]["canonical_category"] == "Financial & Transfers"
    assert parsed_csv[1]["subcategory"] == "Refund & Cashback"

    # --- Real PostgreSQL end-to-end QA scenarios ---
    await engine.dispose()
    phone = f"+9197{uuid4().int % 10**8:08d}"
    owner = User(id=uuid4(), email=f"qa_own_{uuid4().hex[:6]}@s.in", role="STORE_OWNER", hashed_password="x")
    customer = User(
        id=uuid4(),
        email=f"qa_cus_{uuid4().hex[:6]}@c.in",
        phone=phone,
        phone_verified=True,
        role="CUSTOMER",
        hashed_password="x",
    )
    stranger = User(id=uuid4(), email=f"qa_str_{uuid4().hex[:6]}@c.in", role="CUSTOMER", hashed_password="x")
    biz = Business(id=uuid4(), name="QA Retail Mart", owner_id=owner.id)
    cust_rec = Customer(id=uuid4(), business_id=biz.id, name="QA Customer", phone=phone)
    low_prod = Product(
        id=uuid4(),
        business_id=biz.id,
        name="Tata Salt Vacuum 1kg",
        sku=f"SKU-QA-{uuid4().hex[:6]}",
        selling_price=28.0,
        stock_qty=3,
    )
    ok_prod = Product(
        id=uuid4(),
        business_id=biz.id,
        name="Basmati Rice 5kg",
        sku=f"SKU-QA-{uuid4().hex[:6]}",
        selling_price=450.0,
        stock_qty=40,
    )

    async with SessionLocal() as session:
        session.add_all([owner, customer, stranger])
        await session.flush()
        session.add(biz)
        await session.flush()
        session.add_all([cust_rec, low_prod, ok_prod])
        await session.commit()

    monkeypatch.setattr(
        "app.routers.purchases.extract_invoice_text",
        lambda image_bytes, content_type: "Test Store\nBill No: B-01\nTotal: ₹0.00",
    )

    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # QA-01: OCR zero-amount receipt must return 422 instead of 500
            app.dependency_overrides[get_current_user] = lambda: customer
            zero_res = await client.post(
                "/api/v1/purchases/ocr-invoice/save",
                files={"file": ("zero.png", b"img", "image/png")},
            )
            assert zero_res.status_code == 422

            # QA-03: Import DEBIT (350) + CREDIT refund (350) -> customer spend category only counts DEBIT (350)
            imp = await client.post(
                "/api/v1/banking/import-statement",
                json={"filename": "refund_check.csv", "content": csv_bytes.decode()},
            )
            assert imp.status_code == 200
            uni_cust = (await client.get("/api/v1/transactions/unified?view=customer")).json()
            assert uni_cust["nested_summary"]["Food"]["Delivery"] == 350.0
            assert "Financial & Transfers" not in uni_cust["nested_summary"]
            assert uni_cust["total_credits"] == 350.0

            # QA-08 (Store Sales, Supplier Purchase, Cancelled exclusion, Malformed UUID 422, README AI)
            app.dependency_overrides[get_current_user] = lambda: owner
            # Create one PAID sale (900), one CANCELLED sale (500), and one PAID purchase (400)
            sale_ok_res = await client.post(
                "/api/v1/invoices",
                json={
                    "invoice_number": f"QA-S-{uuid4().hex[:6]}",
                    "business_id": str(biz.id),
                    "customer_id": str(cust_rec.id),
                    "type": "SALE",
                    "status": "PAID",
                    "discount_amount": 25.0,
                    "payment_method": "UPI",
                    "items": [{"product_id": str(ok_prod.id), "quantity": 2, "unit_price": 450.0}],
                },
            )
            assert sale_ok_res.status_code == 200
            sale_ok = sale_ok_res.json()

            sale_cancel_res = await client.post(
                "/api/v1/invoices",
                json={
                    "invoice_number": f"QA-C-{uuid4().hex[:6]}",
                    "business_id": str(biz.id),
                    "customer_id": str(cust_rec.id),
                    "type": "SALE",
                    "status": "CONFIRMED",
                    "discount_amount": 50.0,
                    "payment_method": "CASH",
                    "items": [{"product_id": str(ok_prod.id), "quantity": 1, "unit_price": 500.0}],
                },
            )
            assert sale_cancel_res.status_code == 200
            sale_cancel = sale_cancel_res.json()
            cancel_res = await client.patch(f"/api/v1/invoices/{sale_cancel['id']}/status?status=CANCELLED")
            assert cancel_res.status_code == 200

            purchase_ok_res = await client.post(
                "/api/v1/invoices",
                json={
                    "invoice_number": f"QA-P-{uuid4().hex[:6]}",
                    "business_id": str(biz.id),
                    "type": "PURCHASE",
                    "status": "PAID",
                    "payment_method": "CASH",
                    "items": [{"product_id": str(ok_prod.id), "quantity": 1, "unit_price": 400.0}],
                },
            )
            assert purchase_ok_res.status_code == 200
            purchase_ok = purchase_ok_res.json()

            dash = (await client.get("/api/v1/dashboard/store")).json()
            assert dash["totalDiscountsGiven"] == 25.0
            assert dash["todayRevenue"] == float(sale_ok["total_amount"])

            # Malformed UUID must return 422 instead of 500
            assert (await client.get("/api/v1/invoices/not-a-uuid")).status_code == 422

            # QA-04: Both missing README questions on /api/v1/ai/assistant
            ai_profit = (
                await client.post("/api/v1/ai/assistant", json={"question": "How much profit did I make this month?"})
            ).json()
            assert ai_profit["intent"] == "store_profit"
            expected_profit = round(float(sale_ok["total_amount"]) - float(purchase_ok["total_amount"]), 2)
            assert ai_profit["metrics"]["net_profit"] == expected_profit

            ai_restock = (
                await client.post("/api/v1/ai/assistant", json={"question": "Which products should I restock?"})
            ).json()
            assert ai_restock["intent"] == "restock_alert"
            assert "Tata Salt" in ai_restock["answer"]

            # OWASP API1 BOLA: stranger cannot read owner invoice
            app.dependency_overrides[get_current_user] = lambda: stranger
            assert (await client.get(f"/api/v1/invoices/{sale_ok['id']}")).status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        await engine.dispose()


@pytest.mark.anyio
async def test_active_learning_category_override_and_bounded_rate_limit():
    from app.cores.rate_limit import MAX_BUCKETS, _buckets, check_rate_limit, reset_rate_limits
    from app.services.classifier import USER_LEARNED_RULES

    # 1. Verify bounded rate-limiter eviction prevents unbounded memory growth
    reset_rate_limits()
    try:
        for i in range(MAX_BUCKETS + 25):
            check_rate_limit(f"flood-ip-{i}", max_requests=5, window_seconds=60)
        assert len(_buckets) <= MAX_BUCKETS
    finally:
        reset_rate_limits()

    # 2. Verify active-learning category override persists in DB and teaches classify_hierarchical
    await engine.dispose()
    user = User(id=uuid4(), email=f"al_{uuid4().hex[:6]}@test.in", role="CUSTOMER", hashed_password="x")
    async with SessionLocal() as session:
        session.add(user)
        await session.commit()

    app.dependency_overrides[get_current_user] = lambda: user
    transport = httpx.ASGITransport(app=app)
    unique_vendor = f"ZohoBooksSaaS-{uuid4().hex[:6]}"
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            p_res = await client.post(
                "/api/v1/purchases",
                json={
                    "marketplace": unique_vendor,
                    "category": "Shopping",
                    "amount": 999.0,
                    "purchased_at": datetime.now(UTC).isoformat(),
                    "order_id": f"ZB-{uuid4().hex[:8]}",
                    "items_note": "Annual cloud ledger plan",
                    "payment_method": "Credit Card",
                },
            )
            assert p_res.status_code == 201

            uni = (await client.get("/api/v1/transactions/unified?view=customer")).json()
            target_tx = next(it for it in uni["items"] if it["counterparty"] == unique_vendor)

            patch_res = await client.patch(
                f"/api/v1/transactions/unified/{target_tx['id']}/category",
                json={"category": "Business & MSME", "subcategory": "Services & SaaS"},
            )
            assert patch_res.status_code == 200
            updated = patch_res.json()
            assert updated["category"] == "Business & MSME"
            assert updated["subcategory"] == "Services & SaaS"
            assert updated["classification_source"] == "user_learned"

            # Subsequent calls for this counterparty now use active-learning memory automatically
            cat, sub, src = classify_hierarchical(text="Monthly renewal", counterparty=unique_vendor)
            assert (cat, sub, src) == ("Business & MSME", "Services & SaaS", "user_learned")
    finally:
        USER_LEARNED_RULES.pop(unique_vendor.lower(), None)
        app.dependency_overrides.pop(get_current_user, None)
        await engine.dispose()
