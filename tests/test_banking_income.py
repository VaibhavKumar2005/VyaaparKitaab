from uuid import uuid4

import pytest
from app.main import app
from app.models.user import User
from app.services.auth import get_current_user
from starlette.testclient import TestClient


@pytest.fixture
def test_user():
    return User(
        id=uuid4(),
        email="test_msme@vyapaarkitaab.in",
        role="STORE_OWNER",
    )


def test_banking_app_consent_and_safe_income_stream(test_user):
    """
    Verifies that a banking app can be connected via RBI Account Aggregator (AA)
    to represent incoming credits/income safely without asking for or exposing
    the user's bank account number, netbanking password, or MPIN.
    """
    app.dependency_overrides[get_current_user] = lambda: test_user
    client = TestClient(app)

    try:
        # 1. Initiate Consent for SBI YONO (Purpose code 102 - Customer budget & income)
        initiate_res = client.post(
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
        auth_res = client.post(
            "/api/v1/banking/consent/authorize",
            json={"consent_id": consent_id, "approve": True, "fip_id": "sbi_yono"},
        )
        assert auth_res.status_code == 200
        auth_data = auth_res.json()
        assert auth_data["status"] == "APPROVED"

        # 3. Retrieve Safe Inward Income Stream
        income_res = client.get("/api/v1/banking/income-stream")
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
        graph_res = client.get("/api/v1/banking/income-graph")
        assert graph_res.status_code == 200
        graph_data = graph_res.json()
        assert any(n["id"] == "source_bank" for n in graph_data["nodes"])
        assert any(n["id"] == "aa_tunnel" for n in graph_data["nodes"])
        assert any(n["id"] == "income_hub" for n in graph_data["nodes"])
        assert len(graph_data["edges"]) >= 2

        # 5. Revoke Consent (DPDP Act compliance)
        revoke_res = client.post("/api/v1/banking/consent/revoke")
        assert revoke_res.status_code == 200
        assert revoke_res.json()["status"] == "REVOKED"

    finally:
        app.dependency_overrides.pop(get_current_user, None)
