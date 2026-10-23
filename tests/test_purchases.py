import os
from datetime import datetime, timezone
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/vyaapardb")
os.environ.setdefault("ENV", "testing")

from app.cores.database import get_db
from app.main import app
from app.models.purchase import PersonalPurchase
from app.models.user import User
from app.services.auth import get_current_user
from app.services.encryption import blind_index, decrypt_field, encrypt_field
from app.services.invoice_parser import parse_marketplace_receipt_text


def test_encryption_and_blind_index():
    raw_order_id = "404-9876543-1234567"
    ciphertext = encrypt_field(raw_order_id)
    assert ciphertext.startswith("enc_v1:")
    assert raw_order_id not in ciphertext

    decrypted = decrypt_field(ciphertext)
    assert decrypted == raw_order_id

    # Blind index must be deterministic and hash length 64 (HMAC-SHA256 hex)
    bidx_1 = blind_index(raw_order_id)
    bidx_2 = blind_index(raw_order_id)
    assert bidx_1 == bidx_2
    assert len(bidx_1) == 64
    assert raw_order_id not in bidx_1

    # Different inputs produce distinct blind indexes
    bidx_diff = blind_index("404-0000000-0000000")
    assert bidx_1 != bidx_diff


def test_parse_marketplace_receipt_text_amazon():
    amazon_email_snippet = """
    Final Details for Order #404-7123456-7890123
    Order Placed: 23 October 2026
    Amazon.in order number: 404-7123456-7890123
    Order Total: ₹1,499.00
    Payment Method: UPI (Google Pay)
    
    Items Ordered:
    boAt Rockerz 450 Bluetooth On Ear Headphones with Mic (Luscious Black)
    Condition: New
    Sold by: Appario Retail Private Ltd
    """
    res = parse_marketplace_receipt_text(amazon_email_snippet)
    assert res["marketplace"] == "Amazon"
    assert res["order_id"] == "404-7123456-7890123"
    assert res["amount"] == 1499.0
    assert "boAt Rockerz" in (res["items_summary"] or "")
    assert res["confidence"] == "HIGH"


def test_parse_marketplace_receipt_text_flipkart():
    flipkart_text = """
    Your Flipkart order OD30492817264819203 is confirmed.
    Grand Total: Rs. 2,499
    Item: Men Slim Fit Solid Spread Collar Casual Shirt
    """
    res = parse_marketplace_receipt_text(flipkart_text)
    assert res["marketplace"] == "Flipkart"
    assert res["order_id"] == "OD30492817264819203"
    assert res["amount"] == 2499.0
    assert res["confidence"] == "HIGH"


def test_parse_invoice_text_endpoint():
    user = User(id=uuid4(), email="user1@example.com", role="CUSTOMER")
    app.dependency_overrides[get_current_user] = lambda: user
    client = TestClient(app)

    payload = {
        "invoice_text": "Amazon order 402-1112223-3334445 total ₹799.00 on 23-10-2026 for Wireless Mouse"
    }
    response = client.post("/api/v1/purchases/parse-invoice-text", json=payload)
    app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    data = response.json()
    assert data["marketplace"] == "Amazon"
    assert data["order_id"] == "402-1112223-3334445"
    assert data["amount"] == 799.0


@pytest.mark.anyio
async def test_personal_purchases_crud_and_isolation():
    """
    Verifies end-to-end CRUD, AES encryption at rest, duplicate blind-index protection,
    and strict multi-tenant isolation so no other user can leak or retrieve the purchase.
    """
    from app.cores.database import engine
    await engine.dispose()

    user_a = User(
        id=UUID("602a1564-0036-4239-8fd6-b4ac99142721"),
        email="vaibhavkrsharma0412@gmail.com",
        role="STORE_OWNER",
    )
    user_b = User(
        id=UUID("10f42a49-1e4f-4991-8bae-786704921c2e"),
        email="demo@vyapaarkitaab.in",
        role="STORE_OWNER",
    )

    # Override current user as user_a
    app.dependency_overrides[get_current_user] = lambda: user_a
    transport = httpx.ASGITransport(app=app)

    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Create a purchase today for user_a
            today_iso = datetime.now(timezone.utc).isoformat()
            order_id = f"408-{uuid4().hex[:7]}-{uuid4().hex[:7]}"
            purchase_data = {
                "marketplace": "Amazon",
                "category": "Electronics",
                "amount": 1499.0,
                "currency": "INR",
                "purchased_at": today_iso,
                "order_id": order_id,
                "items_note": "Sony WH-CH520 Wireless Bluetooth Headphones",
                "payment_method": "UPI (Google Pay)",
            }

            create_res = await client.post("/api/v1/purchases", json=purchase_data)
            assert create_res.status_code == 201
            created_item = create_res.json()
            assert created_item["order_id"] == order_id
            assert created_item["items_note"] == "Sony WH-CH520 Wireless Bluetooth Headphones"
            assert created_item["is_encrypted"] is True
            purchase_id = created_item["id"]

            # 2. Duplicate check (same user, same marketplace, same order ID) must return 409
            dup_res = await client.post("/api/v1/purchases", json=purchase_data)
            assert dup_res.status_code == 409

            # 3. User A can list their own purchase
            list_res = await client.get("/api/v1/purchases")
            assert list_res.status_code == 200
            items = list_res.json()
            assert any(it["id"] == purchase_id for it in items)

            # 4. User A analytics reflects today's cost
            analytics_res = await client.get("/api/v1/purchases/analytics")
            assert analytics_res.status_code == 200
            analytics = analytics_res.json()
            assert analytics["today_cost"] >= 1499.0
            assert analytics["total_orders"] >= 1
            assert any(m["marketplace"] == "Amazon" for m in analytics["marketplace_breakdown"])

            # 4.5 Transaction graph verification (Bank -> GPay -> Amazon)
            graph_res = await client.get("/api/v1/purchases/transaction-graph")
            assert graph_res.status_code == 200
            graph_data = graph_res.json()
            assert any(n["id"] == "user_bank" for n in graph_data["nodes"])
            assert any(n["id"] == "gpay" for n in graph_data["nodes"])
            assert any(n["id"] == "mkt_amazon" for n in graph_data["nodes"])
            assert len(graph_data["edges"]) >= 2

            # 5. Multitenant isolation: Switch user to User B -> User B must NOT see User A's purchases
            app.dependency_overrides[get_current_user] = lambda: user_b
            bob_list = await client.get("/api/v1/purchases")
            assert bob_list.status_code == 200
            bob_items = bob_list.json()
            assert all(it["id"] != purchase_id for it in bob_items)

            # Clean up created record
            app.dependency_overrides[get_current_user] = lambda: user_a
            del_res = await client.delete(f"/api/v1/purchases/{purchase_id}")
            assert del_res.status_code == 200

    finally:
        app.dependency_overrides.pop(get_current_user, None)
        await engine.dispose()
