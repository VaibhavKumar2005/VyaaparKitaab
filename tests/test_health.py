import os

os.environ.setdefault('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/vyaapardb')
os.environ.setdefault('ENV', 'testing')

from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint() -> None:
    client = TestClient(app)
    response = client.get('/api/v1/health')
    assert response.status_code == 200
    assert response.json() == {'status': 'healthy'}