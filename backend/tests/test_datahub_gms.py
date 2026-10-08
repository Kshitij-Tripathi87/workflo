"""Tests for the DataHub adapter and GMS client."""
import pytest
from app.connectors.datahub.adapter import adapter, MockDataHubClient
from app.connectors.datahub.client import DataHubClient
from app.core.exceptions import DataHubNotFoundError


ORDER_URN = "urn:li:dataset:(urn:li:dataPlatform:postgres,orders,PROD)"


def test_mock_client_get_asset():
    """Mock client returns asset from in-memory store."""
    client = MockDataHubClient()
    asset = client.get_asset(ORDER_URN)
    assert asset["name"] == "orders"
    assert asset["kind"] == "dataset"


def test_mock_client_get_lineage():
    """Mock client returns upstream and downstream."""
    client = MockDataHubClient()
    lineage = client.get_lineage(ORDER_URN)
    assert "downstream" in lineage
    assert "upstream" in lineage
    assert len(lineage["downstream"]) >= 1


def test_mock_client_not_found():
    """Mock client raises DataHubNotFoundError for missing asset."""
    client = MockDataHubClient()
    with pytest.raises(DataHubNotFoundError):
        client.get_asset("urn:li:dataset:nonexistent")


def test_mock_client_ml_dependencies():
    """Mock client returns ML model dependencies."""
    client = MockDataHubClient()
    ml_deps = client.get_ml_dependencies(ORDER_URN)
    assert any("mlModel" in dep for dep in ml_deps)


def test_adapter_sync_mock_by_default():
    """Adapter defaults to mock mode when no DataHub configured."""
    assert adapter.use_mock is True
    assert adapter.async_client is None
    assert adapter.sync is not None


def test_legacy_datahub_client_facade():
    """Legacy DataHubClient facade still works through adapter."""
    client = DataHubClient()
    asset = client.get_asset(ORDER_URN)
    assert asset["name"] == "orders"
    assert client.get_criticality(ORDER_URN) in ["low", "medium", "high", "critical"]
    assert client.get_kind(ORDER_URN) in ["dataset", "pipeline", "dashboard", "model"]


def test_mock_client_tags():
    """Mock client returns tags."""
    client = MockDataHubClient()
    tags = client.get_tags(ORDER_URN)
    assert isinstance(tags, list)
    assert len(tags) >= 1


def test_gms_client_base_url_from_settings_is_str_coerced(monkeypatch):
    """Regression: settings.DATAHUB_BASE_URL is a pydantic AnyHttpUrl.

    The GMS client used to call ``.rstrip("/")`` directly on the settings value,
    which raised ``AttributeError: 'Url' object has no attribute 'rstrip'``.
    mypy reported this (union-attr) but CI ran mypy with ``|| true``, so the
    defect shipped silently. Exercised through the *settings* path.
    """
    from pydantic import AnyHttpUrl
    from app.core import settings as settings_module

    # Must be a real pydantic Url: patching in a plain str would silently make
    # this test pass even with the defect present (str.rstrip works fine).
    monkeypatch.setattr(
        settings_module.settings,
        "DATAHUB_BASE_URL",
        AnyHttpUrl("http://localhost:8080/"),
    )
    from app.connectors.datahub.gms import DataHubGMSClient

    client = DataHubGMSClient()
    assert client.base_url == "http://localhost:8080"


def test_gms_client_without_base_url_is_empty_not_crash(monkeypatch):
    """Unset base URL must degrade to "" - never raise."""
    from app.core import settings as settings_module

    monkeypatch.setattr(settings_module.settings, "DATAHUB_BASE_URL", None)
    from app.connectors.datahub.gms import DataHubGMSClient

    assert DataHubGMSClient().base_url == ""
