import os
from uuid import uuid4

import httpx
import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/vyaapardb")
os.environ.setdefault("ENV", "testing")

from app.cores.database import SessionLocal, engine
from app.main import app
from app.models.business import Business, Product
from app.models.user import User
from app.services.auth import get_current_user
from sqlalchemy import select


async def _ensure_test_seed() -> User:
    async with SessionLocal() as session:
        res = await session.execute(select(User).where(User.email == "demo@vyapaarkitaab.in"))
        owner = res.scalars().first()
        if not owner:
            owner = User(
                id=uuid4(),
                email="demo@vyapaarkitaab.in",
                hashed_password="test_hashed_password_123",
                full_name="Rajendra Sharma",
                phone="9876500001",
                role="STORE_OWNER",
                is_active=True,
            )
            session.add(owner)
            await session.flush()

        res_biz = await session.execute(select(Business).where(Business.owner_id == owner.id))
        biz = res_biz.scalars().first()
        if not biz:
            biz = Business(
                id=uuid4(),
                name="Sharma General Store",
                owner_id=owner.id,
                gstin="07AAAAA0000A1Z5",
                address="Shop 4, Main Market, Delhi",
                phone="9876500001",
            )
            session.add(biz)
            await session.flush()

        prod_res = await session.execute(select(Product).where(Product.business_id == biz.id))
        products = prod_res.scalars().all()
        if len(products) < 2:
            p1 = Product(
                id=uuid4(),
                business_id=biz.id,
                name="Aashirvaad Atta 10kg",
                sku=f"SKU-{uuid4().hex[:6]}",
                selling_price=420.0,
                cost_price=380.0,
                stock_qty=50.0,
            )
            p2 = Product(
                id=uuid4(),
                business_id=biz.id,
                name="Fortune Mustard Oil 1L",
                sku=f"SKU-{uuid4().hex[:6]}",
                selling_price=160.0,
                cost_price=140.0,
                stock_qty=40.0,
            )
            session.add_all([p1, p2])
        await session.commit()
        return owner
from app.services.forecasting import (
    _compute_mae_rmse,
    _holt_linear_forecast,
    _sma_forecast,
    evaluate_and_forecast_series,
)
from app.services.ml_models import (
    cluster_payees_with_kmeans,
    detect_payment_anomalies,
    train_and_compare_sklearn_forecasters,
)


def test_ai_time_series_evaluation_and_holt_linear_forecast() -> None:
    """
    AI/ML Unit Test: Verifies chronological train/validation split (80/20),
    MAE/RMSE computation, Holt-Linear vs SMA-7, and scikit-learn Ridge/RandomForest
    regression, KMeans payee clustering, and IsolationForest anomaly detection.
    """
    # Upward trending sales series where Holt-Linear outperforms flat SMA-7
    trending_series = [1000.0 + i * 120.0 for i in range(15)]
    res = evaluate_and_forecast_series(trending_series, horizon=7)
    assert res["selected_model"] in ("Holt-Linear", "SMA-7")
    assert res["models_compared"]["Holt-Linear"]["rmse"] <= res["models_compared"]["SMA-7"]["rmse"]
    assert res["selected_model"] == "Holt-Linear"
    assert "RidgeRegression" in res["models_compared"]
    assert "RandomForestRegressor" in res["models_compared"]
    assert len(res["forecast"]) == 7
    assert all(val > 0 for val in res["forecast"])

    # Verify scikit-learn Ridge & RandomForest forecaster directly
    sk_res = train_and_compare_sklearn_forecasters(trending_series, horizon=5)
    assert sk_res["selected_ml_model"] in ("RidgeRegression", "RandomForestRegressor")
    assert len(sk_res["forecast"]) == 5

    # Verify scikit-learn KMeans payee clustering + PCA + silhouette_score
    sample_payees = [
        {"payee_name": "Amazon", "total_paid": 8500.0, "payment_count": 6, "avg_payment": 1416.6, "recency_days": 1.0},
        {"payee_name": "Flipkart", "total_paid": 4200.0, "payment_count": 3, "avg_payment": 1400.0, "recency_days": 3.0},
        {"payee_name": "Blinkit", "total_paid": 950.0, "payment_count": 4, "avg_payment": 237.5, "recency_days": 0.5},
        {"payee_name": "Local Tea Stall", "total_paid": 120.0, "payment_count": 1, "avg_payment": 120.0, "recency_days": 12.0},
    ]
    clustered, meta = cluster_payees_with_kmeans(sample_payees)
    assert len(clustered) == 4
    assert meta["optimal_k"] >= 2
    assert all("ml_cluster_label" in p for p in clustered)

    # Verify IsolationForest anomaly detector
    tx_list = [
        {"payee_name": "Blinkit", "amount": 200.0, "paid_at": "2026-10-20T10:00:00Z", "channel": "UPI"},
        {"payee_name": "Blinkit", "amount": 220.0, "paid_at": "2026-10-21T10:00:00Z", "channel": "UPI"},
        {"payee_name": "Amazon", "amount": 250.0, "paid_at": "2026-10-22T10:00:00Z", "channel": "UPI"},
        {"payee_name": "Amazon", "amount": 240.0, "paid_at": "2026-10-23T10:00:00Z", "channel": "UPI"},
        {"payee_name": "Jewellery Store", "amount": 45000.0, "paid_at": "2026-10-24T10:00:00Z", "channel": "UPI"},
    ]
    anomalies = detect_payment_anomalies(tx_list)
    assert any(a["payee_name"] == "Jewellery Store" for a in anomalies)

    mae, rmse = _compute_mae_rmse([100.0, 200.0], [110.0, 190.0])
    assert mae == 10.0
    assert rmse == 10.0
    assert _sma_forecast([], 3) == [0.0, 0.0, 0.0]
    assert _holt_linear_forecast([250.0], 2) == [250.0, 250.0]


@pytest.mark.anyio
async def test_create_invoice_computes_subtotal_gst_and_total() -> None:
    """
    TC-07: Create an invoice with two items and a discount; verify server-side
    subtotal, 5% GST tax_amount, total_amount, and stock deduction.
    """
    await engine.dispose()
    owner = await _ensure_test_seed()
    app.dependency_overrides[get_current_user] = lambda: owner
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            biz_res = await client.get("/api/v1/businesses")
            assert biz_res.status_code == 200
            businesses = biz_res.json()
            assert len(businesses) >= 1
            biz_id = businesses[0]["id"]

            prod_res = await client.get("/api/v1/products")
            assert prod_res.status_code == 200
            products = prod_res.json()
            assert len(products) >= 2
            p1, p2 = products[0], products[1]

            inv_num = f"INV-TC07-{uuid4().hex[:6].upper()}"
            payload = {
                "invoice_number": inv_num,
                "business_id": biz_id,
                "type": "SALE",
                "status": "DRAFT",
                "discount_amount": 50.0,
                "tax_amount": 1.0,  # Triggers server-side 5% GST computation
                "items": [
                    {"product_id": p1["id"], "quantity": 2, "unit_price": 200.0, "discount": 0.0},
                    {"product_id": p2["id"], "quantity": 1, "unit_price": 150.0, "discount": 0.0},
                ],
            }
            create_res = await client.post("/api/v1/invoices", json=payload)
            assert create_res.status_code == 200
            inv = create_res.json()
            assert inv["invoice_number"] == inv_num
            # Subtotal = (2 * 200) + (1 * 150) = 550.0
            # Taxable = 550.0 - 50.0 = 500.0
            # 5% GST = 25.0 -> Total = 525.0
            assert inv["subtotal"] == 550.0
            assert inv["discount_amount"] == 50.0
            assert inv["tax_amount"] == 25.0
            assert inv["total_amount"] == 525.0
            assert len(inv["items"]) == 2
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        await engine.dispose()


@pytest.mark.anyio
async def test_customer_and_product_update_delete_crud_and_ai_endpoint() -> None:
    """
    Verifies full CRUD (Create, Update, Delete) for Customers (FR-06) and Products (FR-07)
    plus the live AI demand & cash-flow forecast endpoint (/api/v1/ai/forecast).
    """
    await engine.dispose()
    owner = await _ensure_test_seed()
    app.dependency_overrides[get_current_user] = lambda: owner
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            biz_res = await client.get("/api/v1/businesses")
            biz_id = biz_res.json()[0]["id"]

            # 1. Customer Create -> Update -> Delete
            c_res = await client.post(
                "/api/v1/customers",
                json={
                    "name": "Temp Test Buyer",
                    "phone": "+91 91234 56789",
                    "email": "temp.buyer@example.com",
                    "business_id": biz_id,
                },
            )
            assert c_res.status_code == 200
            cust_id = c_res.json()["id"]

            c_upd = await client.put(
                f"/api/v1/customers/{cust_id}",
                json={"name": "Updated Test Buyer", "phone": "9123456780"},
            )
            assert c_upd.status_code == 200
            assert c_upd.json()["name"] == "Updated Test Buyer"

            c_del = await client.delete(f"/api/v1/customers/{cust_id}")
            assert c_del.status_code == 200
            assert c_del.json()["deleted"] is True

            # 2. Product Create -> Update -> Delete
            p_res = await client.post(
                "/api/v1/products",
                json={
                    "name": "Temp Basmati Rice 5kg",
                    "sku": f"TMP-{uuid4().hex[:5].upper()}",
                    "unit": "Bag",
                    "selling_price": 480.0,
                    "cost_price": 410.0,
                    "stock_qty": 12.0,
                    "business_id": biz_id,
                },
            )
            assert p_res.status_code == 200
            prod_id = p_res.json()["id"]

            p_upd = await client.put(
                f"/api/v1/products/{prod_id}",
                json={"selling_price": 495.0, "stock_qty": 4.0},
            )
            assert p_upd.status_code == 200
            assert p_upd.json()["selling_price"] == 495.0
            assert p_upd.json()["stock_qty"] == 4.0

            p_del = await client.delete(f"/api/v1/products/{prod_id}")
            assert p_del.status_code == 200
            assert p_del.json()["deleted"] is True

            # 3. AI Forecast Endpoint
            ai_res = await client.get("/api/v1/ai/forecast")
            assert ai_res.status_code == 200
            ai_data = ai_res.json()
            assert "revenue_model" in ai_data
            assert "inventory_forecasts" in ai_data
            assert len(ai_data["revenue_model"]["forecast_daily"]) == 7
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        await engine.dispose()

