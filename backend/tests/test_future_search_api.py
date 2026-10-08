"""Test the future-search API with policy evaluation attached."""
import pytest
from fastapi.testclient import TestClient
from app.main import app


client = TestClient(app)


ORDER_URN = "urn:li:dataset:(urn:li:dataPlatform:postgres,orders,PROD)"


def test_future_search_without_policies():
    """Default request returns a plan with no policy_result attached."""
    response = client.post("/future-search/run", json={
        "asset_urn": ORDER_URN,
        "objective": "minimize incident risk",
    })

    assert response.status_code == 200
    body = response.json()
    assert "ranked_choice" in body
    assert body["asset_urn"] == ORDER_URN
    assert "policy_result" in body
    # When no policies are sent, policy_result should be null
    assert body["policy_result"] is None
    # New blast_radius field must be populated
    assert body["ranked_choice"]["predicted_blast_radius"] >= 0


def test_future_search_with_passthrough_policy():
    """A policy that isn't violated results in verdict = pass."""
    response = client.post("/future-search/run", json={
        "asset_urn": ORDER_URN,
        "policies": [
            {
                "name": "Allow up to 100 blast radius",
                "max_blast_radius": 100,
                "max_severity": 100,
                "action": "block",
            }
        ],
    })

    assert response.status_code == 200
    body = response.json()
    pr = body["policy_result"]
    assert pr is not None
    assert pr["verdict"] == "pass"
    assert pr["results"] == []


def test_future_search_with_blocking_policy():
    """A policy with a tiny threshold should produce a block verdict."""
    response = client.post("/future-search/run", json={
        "asset_urn": ORDER_URN,
        "policies": [
            {
                "name": "Block anything that touches downstream",
                "max_blast_radius": 0,
                "action": "block",
            }
        ],
    })

    assert response.status_code == 200
    body = response.json()
    pr = body["policy_result"]
    assert pr is not None
    assert pr["verdict"] == "block"
    assert len(pr["results"]) >= 1
    assert pr["results"][0]["policy_name"].startswith("Block")


def test_future_search_warn_dominated_by_block():
    """When one policy warns and another blocks, the combined verdict is block."""
    response = client.post("/future-search/run", json={
        "asset_urn": ORDER_URN,
        "policies": [
            {"name": "Strict", "max_blast_radius": 0, "action": "block"},
            {"name": "Soft", "max_severity": 10, "action": "warn"},
        ],
    })

    assert response.status_code == 200
    pr = response.json()["policy_result"]
    assert pr["verdict"] == "block"


def test_future_search_invalid_policy_action_rejected():
    """Invalid action value is rejected by pydantic with 422."""
    response = client.post("/future-search/run", json={
        "asset_urn": ORDER_URN,
        "policies": [
            {"name": "Bad", "action": "explode"}
        ],
    })

    assert response.status_code == 422
