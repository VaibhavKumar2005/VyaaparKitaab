import os
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/vyaapardb")
os.environ.setdefault("ENV", "testing")

from app.cores.config import settings
from app.cores.database import get_db
from app.cores.rate_limit import reset_rate_limits
from app.main import app
from app.models.transaction import OTPVerification
from app.models.user import User
from app.services.otp import hash_otp
from fastapi.testclient import TestClient
from jose import jwt


class FakeScalars:
    def __init__(self, items: list[Any]) -> None:
        self._items = items

    def first(self) -> Any:
        return self._items[0] if self._items else None

    def all(self) -> list[Any]:
        return self._items


class FakeResult:
    def __init__(self, items: list[Any]) -> None:
        self._items = items

    def scalar_one_or_none(self) -> Any:
        return self._items[0] if self._items else None

    def scalars(self) -> FakeScalars:
        return FakeScalars(self._items)


class FakeSession:
    def __init__(self) -> None:
        self.users: list[User] = []
        self.otps: list[OTPVerification] = []

    async def execute(self, statement: Any) -> FakeResult:
        if hasattr(statement, "column_descriptions") and statement.column_descriptions:
            entity = statement.column_descriptions[0].get("entity")
            filters = getattr(statement, "_where_criteria", ())

            if entity is User:
                for user in self.users:
                    matched = True
                    for criterion in filters:
                        left = getattr(criterion.left, "name", None)
                        right = getattr(criterion.right, "value", None)
                        if left == "email" and right != user.email:
                            matched = False
                        if left == "phone" and right != user.phone:
                            matched = False
                    if matched:
                        return FakeResult([user])
                return FakeResult([])

            if entity is OTPVerification:
                now = datetime.now(UTC)
                valid_otps = [o for o in self.otps if not o.used and o.expires_at > now]
                return FakeResult(valid_otps)

        return FakeResult([])

    def add(self, obj: Any) -> None:
        if isinstance(obj, User):
            if not getattr(obj, "id", None):
                obj.id = uuid4()
            self.users.append(obj)
        elif isinstance(obj, OTPVerification):
            if not getattr(obj, "id", None):
                obj.id = uuid4()
            self.otps.append(obj)

    async def commit(self) -> None:
        return None

    async def refresh(self, obj: Any) -> None:
        return None


fake_session = FakeSession()


async def override_get_db():
    yield fake_session


def test_register_login_happy_path() -> None:
    """TC-02: Register a store owner, log in, and log out."""
    reset_rate_limits()
    fake_session.users.clear()
    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        register_response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "owner@example.com",
                "password": "Password123!",
                "full_name": "Owner",
                "phone": "9999999999",
                "role": "STORE_OWNER",
            },
        )
        assert register_response.status_code == 200

        login_response = client.post(
            "/api/v1/auth/login",
            json={"email": "owner@example.com", "password": "Password123!"},
        )
        assert login_response.status_code == 200
        payload = jwt.decode(login_response.json()["access_token"], settings.SECRET_KEY, algorithms=["HS256"])
        assert payload["role"] == "STORE_OWNER"

        logout_response = client.post("/api/v1/auth/logout")
        assert logout_response.status_code == 200
        assert logout_response.json() == {"message": "logged out"}
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_login_wrong_password_returns_401() -> None:
    """TC-06: Log in with wrong password returns HTTP 401 with generic Invalid credentials detail."""
    reset_rate_limits()
    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        bad_login = client.post(
            "/api/v1/auth/login",
            json={"email": "owner@example.com", "password": "WrongPassword999!"},
        )
        assert bad_login.status_code == 401
        assert bad_login.json()["detail"] == "Invalid credentials"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_verify_otp_second_time_is_rejected() -> None:
    """TC-10: Verify an OTP a second time after it has been used is rejected with HTTP 400."""
    reset_rate_limits()
    fake_session.otps.clear()
    fake_session.otps.append(
        OTPVerification(
            id=uuid4(),
            phone="9876543210",
            otp_hash=hash_otp("654321"),
            purpose="TRANSACTION",
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
            used=False,
            created_at=datetime.now(UTC),
        )
    )
    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        first_res = client.post("/api/v1/auth/otp/verify?phone=9876543210&otp=654321&purpose=TRANSACTION")
        assert first_res.status_code == 200
        assert first_res.json()["verified"] is True

        # Second verification attempt with the same OTP must fail because used=True
        second_res = client.post("/api/v1/auth/otp/verify?phone=9876543210&otp=654321&purpose=TRANSACTION")
        assert second_res.status_code == 400
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_login_rate_limiting_returns_429() -> None:
    """Verifies sliding-window rate limiter blocks brute-force login attempts with HTTP 429."""
    reset_rate_limits()
    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        for _ in range(10):
            res = client.post(
                "/api/v1/auth/login",
                json={"email": "ratelimit@example.com", "password": "wrong"},
            )
            assert res.status_code == 401
        blocked = client.post(
            "/api/v1/auth/login",
            json={"email": "ratelimit@example.com", "password": "wrong"},
        )
        assert blocked.status_code == 429
    finally:
        reset_rate_limits()
        app.dependency_overrides.pop(get_db, None)
