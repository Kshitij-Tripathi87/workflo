"""Test the full demo flow endpoint."""
import pytest
from fastapi.testclient import TestClient
from app.main import app


client = TestClient(app)


def test_demo_run_schema_remove():
    """Test the full demo flow with schema_remove scenario."""
    response = client.post("/demo/run", json={
        "asset_urn": "urn:li:dataset:(urn:li:dataPlatform:postgres,orders,PROD)",
        "scenario_type": "schema_remove",
        "change": {"removed": ["customer_name"]}
    })
    
    assert response.status_code == 200
    data = response.json()
    
    assert "asset" in data
    assert "scenario" in data
    assert "impact" in data
    assert "recommendation" in data
    assert "artifact" in data
    assert "writeback" in data
    
    assert data["scenario"]["scenario_type"] == "schema_remove"
    assert data["impact"]["severity"] in ["low", "medium", "high", "critical"]
    assert data["recommendation"]["action_type"] is not None
    assert data["artifact"]["artifact_type"] in ["sql", "dbt", "dag", "yaml", "markdown"]
    assert data["writeback"]["record_id"] is not None


def test_demo_run_owner_missing():
    """Test the full demo flow with owner_missing scenario."""
    response = client.post("/demo/run", json={
        "asset_urn": "urn:li:dataset:(urn:li:dataPlatform:postgres,customers,PROD)",
        "scenario_type": "owner_missing",
        "change": {}
    })
    
    assert response.status_code == 200
    data = response.json()
    
    assert "asset" in data
    assert data["scenario"]["scenario_type"] == "owner_missing"


def test_demo_run_asset_not_found():
    """Test demo flow with non-existent asset."""
    response = client.post("/demo/run", json={
        "asset_urn": "urn:li:dataset:nonexistent",
        "scenario_type": "schema_remove",
        "change": {}
    })
    
    assert response.status_code == 404