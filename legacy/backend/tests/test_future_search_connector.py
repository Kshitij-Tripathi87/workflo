"""Test that the future-search API can route to different connectors."""
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app


FIXTURE = Path(__file__).parent / "fixtures" / "dbt_manifest.json"


client = TestClient(app)


ORDER_URN_DATAHUB = "urn:li:dataset:(urn:li:dataPlatform:postgres,orders,PROD)"
ORDER_URN_DBT = "urn:dbt:model:jaffle_shop:orders"


@pytest.fixture(autouse=True)
def _dbt_env(monkeypatch):
    """Point the dbt connector at our fixture manifest."""
    monkeypatch.setenv("CORTEX_DBT_MANIFEST_PATH", str(FIXTURE))
    monkeypatch.setenv("CORTEX_DBT_CATALOG_PATH", "")
    monkeypatch.setenv("CORTEX_SNOWFLAKE_MOCK", "true")
    yield


def test_default_connector_is_datahub():
    """Omitting `connector` still works — uses the existing DataHub path."""
    response = client.post("/future-search/run", json={"asset_urn": ORDER_URN_DATAHUB})
    assert response.status_code == 200
    body = response.json()
    assert body["asset_urn"] == ORDER_URN_DATAHUB
    assert body["ranked_choice"]["predicted_blast_radius"] >= 0


def test_explicit_datahub_connector():
    """connector='datahub' works the same as the default."""
    response = client.post(
        "/future-search/run",
        json={"asset_urn": ORDER_URN_DATAHUB, "connector": "datahub"},
    )
    assert response.status_code == 200
    assert response.json()["asset_urn"] == ORDER_URN_DATAHUB


def test_dbt_connector_returns_plan():
    """connector='dbt' parses the fixture manifest and returns a plan."""
    response = client.post(
        "/future-search/run",
        json={"asset_urn": ORDER_URN_DBT, "connector": "dbt"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["asset_urn"] == ORDER_URN_DBT
    assert body["ranked_choice"]["predicted_blast_radius"] >= 1
    assert body["ranked_choice"]["scenario_type"] != ""


def test_dbt_connector_with_blocking_policy():
    """Policies apply to plans from non-datahub connectors too."""
    response = client.post(
        "/future-search/run",
        json={
            "asset_urn": ORDER_URN_DBT,
            "connector": "dbt",
            "policies": [
                {
                    "name": "BlockAnyBlast",
                    "max_blast_radius": 0,
                    "action": "block",
                }
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    pr = body["policy_result"]
    assert pr is not None
    assert pr["verdict"] == "block"


def test_snowflake_connector_in_mock_mode():
    """connector='snowflake' with CORTEX_SNOWFLAKE_MOCK=true returns a plan."""
    response = client.post(
        "/future-search/run",
        json={
            "asset_urn": "urn:snowflake:table:PROD.PUBLIC.ORDERS",
            "connector": "snowflake",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["asset_urn"] == "urn:snowflake:table:PROD.PUBLIC.ORDERS"
    assert body["ranked_choice"]["predicted_blast_radius"] >= 1


def test_unknown_connector_returns_400():
    """An unknown connector name returns 400, not 500."""
    response = client.post(
        "/future-search/run",
        json={
            "asset_urn": "urn:anything:x",
            "connector": "nonexistent-connector",
        },
    )
    assert response.status_code == 400
    assert "nonexistent-connector" in response.json()["detail"]


def test_dbt_connector_asset_not_found_returns_404():
    """A valid connector with an unknown asset returns 404."""
    response = client.post(
        "/future-search/run",
        json={
            "asset_urn": "urn:dbt:model:jaffle_shop:no_such_model",
            "connector": "dbt",
        },
    )
    assert response.status_code == 404


def test_list_connectors_endpoint():
    """GET /future-search/connectors lists registered connectors."""
    response = client.get("/future-search/connectors")
    assert response.status_code == 200
    names = response.json()["connectors"]
    assert "datahub" in names
    assert "dbt" in names
    assert "snowflake" in names
