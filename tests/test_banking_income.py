from uuid import uuid4

import httpx
import pytest
from app.cores.database import SessionLocal, engine
from app.main import app
from app.models.user import User
from app.services.auth import get_current_user
from app.services.bank_stream_simulator import simulator_manager


@pytest.fixture
def test_user():
    return User(
        id=uuid4(),
        email=f"test_msme_{uuid4().hex[:6]}@vyapaarkitaab.in",
        hashed_password="test_hashed_password_123",
        role="STORE_OWNER",
    )


@pytest.mark.anyio
async def test_banking_app_consent_and_safe_income_stream(test_user):
    """
    Verifies that a banking app can be connected via RBI Account Aggregator (AA)
    to represent incoming credits/income safely without asking for or exposing
    the user's bank account number, netbanking password, or MPIN.
    """
    await engine.dispose()
    app.dependency_overrides[get_current_user] = lambda: test_user
    transport = httpx.ASGITransport(app=app)

    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Initiate Consent for SBI YONO (Purpose code 102 - Customer budget & income)
            initiate_res = await client.post(
                "/api/v1/banking/consent/initiate",
                json={
                    "fip_id": "sbi_yono",
                    "phone": "9876543210",
                    "purpose_code": "102",
                    "fetch_type": "PERIODIC",
                    "data_life_months": 6,
                },
            )
            assert initiate_res.status_code == 201
            consent_data = initiate_res.json()
            assert consent_data["consent_id"].startswith("consent_")
            assert consent_data["fip_id"] == "sbi_yono"
            assert consent_data["fip_name"] == "State Bank of India (SBI YONO)"
            assert consent_data["masked_acc"] == "XXXX-XXXX-4821"
            assert "zero_account_storage" in consent_data["security_guarantees"]
            consent_id = consent_data["consent_id"]

            # 2. Authorize Consent (simulating customer approving on their SBI YONO / banking app)
            auth_res = await client.post(
                "/api/v1/banking/consent/authorize",
                json={"consent_id": consent_id, "approve": True, "fip_id": "sbi_yono"},
            )
            assert auth_res.status_code == 200
            auth_data = auth_res.json()
            assert auth_data["status"] == "APPROVED"

            # 3. Retrieve Safe Inward Income Stream
            income_res = await client.get("/api/v1/banking/income-stream")
            assert income_res.status_code == 200
            income_data = income_res.json()
            assert income_data["is_connected"] is True
            assert income_data["total_inward_income"] > 0
            assert income_data["total_credits_count"] > 0
            assert len(income_data["monthly_trend"]) >= 1
            assert len(income_data["category_breakdown"]) >= 1
            assert len(income_data["recent_inflows"]) >= 1

            # Verify no raw account numbers are exposed
            for inflow in income_data["recent_inflows"]:
                assert inflow["type"] == "CREDIT"
                assert "XXXX-XXXX" in inflow["masked_acc"]
                assert inflow["amount"] > 0

            # Verify security metadata
            sec_meta = income_data["security_metadata"]
            assert "Verified" in sec_meta["zero_account_exposure"]
            assert sec_meta["debit_risk"] == "0.0% (Cryptographically impossible to debit account)"

            # 4. Inward Directed Money Flow Graph
            graph_res = await client.get("/api/v1/banking/income-graph")
            assert graph_res.status_code == 200
            graph_data = graph_res.json()
            assert any(n["id"] == "source_bank" for n in graph_data["nodes"])
            assert any(n["id"] == "aa_tunnel" for n in graph_data["nodes"])
            assert any(n["id"] == "income_hub" for n in graph_data["nodes"])
            assert len(graph_data["edges"]) >= 2

            # 5. Revoke Consent (DPDP Act compliance)
            revoke_res = await client.post("/api/v1/banking/consent/revoke")
            assert revoke_res.status_code == 200
            assert revoke_res.json()["status"] == "REVOKED"

    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.anyio
async def test_bank_demo_stream_lifecycle(test_user):
    """
    Verifies the real-time Bank Sandbox Stream Simulator:
    1. Instant credit emit (POST /demo-stream/emit) generates, persists, and publishes SSE event.
    2. Start/Status/Stop lifecycle for automated producer.
    3. Emitted transaction immediately appears in personal spending analytics without page refresh.
    """
    await engine.dispose()
    async with SessionLocal() as session:
        session.add(test_user)
        await session.commit()

    app.dependency_overrides[get_current_user] = lambda: test_user
    transport = httpx.ASGITransport(app=app)

    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Emit instant credit
            emit_res = await client.post("/api/v1/banking/demo-stream/emit")
            assert emit_res.status_code == 201
            data = emit_res.json()
            assert data["event"] == "bank.credit.received"
            assert data["txn_id"].startswith("aa_demo_")
            assert data["type"] == "CREDIT"
            assert data["amount"] > 0
            assert data["source"] == "aa_sandbox"
            assert data["masked_acc"] == "XXXX-XXXX-4821"

            # 2. Check initial status
            status_res = await client.get("/api/v1/banking/demo-stream/status")
            assert status_res.status_code == 200
            status_data = status_res.json()
            assert "is_running" in status_data
            assert "interval_seconds" in status_data

            # 3. Start automated producer
            start_res = await client.post("/api/v1/banking/demo-stream/start?interval_seconds=5")
            assert start_res.status_code == 200
            assert start_res.json()["is_running"] is True
            assert start_res.json()["interval_seconds"] == 5

            # 4. Stop automated producer
            stop_res = await client.post("/api/v1/banking/demo-stream/stop")
            assert stop_res.status_code == 200
            assert stop_res.json()["is_running"] is False

            # 5. Verify the emitted credit is reflected in personal spending analytics
            spending_res = await client.get("/api/v1/banking/personal-spending")
            assert spending_res.status_code == 200
            spending = spending_res.json()
            assert spending["credits_count"] >= 1
            assert spending["total_received"] >= data["amount"]
            assert any(t["txn_id"] == data["txn_id"] for t in spending["transactions"])
    finally:
        simulator_manager.stop(test_user.id)
        app.dependency_overrides.pop(get_current_user, None)
        await engine.dispose()

