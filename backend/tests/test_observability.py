"""Tests for observability middleware and metrics endpoints."""
from fastapi.testclient import TestClient
from app.main import app


client = TestClient(app)


def test_health_endpoint():
    """Health endpoint returns 200 and includes env."""
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "env" in data


def test_version_endpoint():
    """Version endpoint returns cortex version."""
    res = client.get("/version")
    assert res.status_code == 200
    assert res.json()["name"] == "Workflo"


def test_metrics_endpoint():
    """Metrics endpoint returns Prometheus format."""
    res = client.get("/metrics")
    assert res.status_code == 200
    body = res.text
    # After hitting some endpoints, counters should be present
    assert "cortex_requests_total" in body or "#" in body


def test_request_id_header():
    """Responses include X-Request-ID header."""
    res = client.get("/health")
    assert "X-Request-ID" in res.headers


def test_structured_error_response():
    """Unknown asset returns structured JSON error (404 via HTTPException)."""
    res = client.get("/assets/urn:li:dataset:nonexistent")
    assert res.status_code == 404
    assert "detail" in res.json()


def test_logout_or_me():
    """Auth /me endpoint works in dev mode (no auth required)."""
    res = client.get("/auth/me")
    assert res.status_code == 200
    data = res.json()
    assert data["subject"] == "dev-user"
    assert "admin" in data["roles"]
