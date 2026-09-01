from fastapi.testclient import TestClient
from app.main import create_app


def test_root():
    app = create_app()
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["service"] == "tenant-shield-control-plane"


def test_health():
    app = create_app()
    client = TestClient(app)
    response = client.get("/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
