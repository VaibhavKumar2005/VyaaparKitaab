import os

os.environ.setdefault('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/vyaapardb')
os.environ.setdefault('ENV', 'testing')

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.cores.database import get_db
from app.main import app
from app.models.user import User


class FakeResult:
    def __init__(self, user):
        self._user = user

    def scalar_one_or_none(self):
        return self._user


class FakeSession:
    def __init__(self):
        self.users = []

    async def execute(self, statement):
        if hasattr(statement, 'column_descriptions'):
            filters = getattr(statement, '_where_criteria', ())
            for user in self.users:
                matched = True
                for criterion in filters:
                    left = getattr(criterion.left, 'name', None)
                    right = getattr(criterion.right, 'value', None)
                    if left == 'email' and right != user.email:
                        matched = False
                    if left == 'phone' and right != user.phone:
                        matched = False
                if matched:
                    return FakeResult(user)
            return FakeResult(None)
        return FakeResult(None)

    def add(self, obj):
        self.users.append(obj)

    async def commit(self):
        return None

    async def refresh(self, obj):
        return None


async def override_get_db():
    yield fake_session


fake_session = FakeSession()
app.dependency_overrides[get_db] = override_get_db


def test_register_login_happy_path() -> None:
    client = TestClient(app)
    register_response = client.post(
        '/api/v1/auth/register',
        json={
            'email': 'owner@example.com',
            'password': 'Password123!',
            'full_name': 'Owner',
            'phone': '9999999999',
            'role': 'STORE_OWNER',
        },
    )
    assert register_response.status_code == 200

    login_response = client.post(
        '/api/v1/auth/login',
        json={'email': 'owner@example.com', 'password': 'Password123!'},
    )
    assert login_response.status_code == 200