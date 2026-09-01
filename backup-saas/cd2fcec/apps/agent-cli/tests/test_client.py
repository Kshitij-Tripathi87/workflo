"""Unit tests for the ControlPlaneClient HTTP client.

All network access is mocked at the level of ``httpx.Client`` so no real
connections are made and tests stay fast.
"""

from unittest.mock import MagicMock, patch

from workflo_agent.client import ControlPlaneClient


def _patch_httpx_client():
    """Patch ``httpx.Client`` so it behaves as a context manager.

    Returns a tuple ``(patcher, client_mock)`` where ``client_mock`` is the
    object that ``with httpx.Client(...) as client:`` binds to ``client``.
    """
    client_mock = MagicMock()
    client_mock.__enter__.return_value = client_mock
    client_mock.__exit__.return_value = None
    patcher = patch("workflo_agent.client.httpx.Client", return_value=client_mock)
    return patcher, client_mock


def test_client_reads_api_key_and_base_url_from_config(monkeypatch):
    def fake_get_config_value(key, default=None, path=None):
        mapping = {
            "auth.api_key": "stored-api-key",
            "defaults.api_base_url": "https://from-config.example.com",
        }
        return mapping.get(key, default)

    monkeypatch.setattr(
        "workflo_agent.client.get_config_value", fake_get_config_value
    )

    client = ControlPlaneClient()

    assert client.api_key == "stored-api-key"
    assert client.base_url == "https://from-config.example.com"


def test_client_uses_config_default_base_url_when_missing(monkeypatch):
    def fake_get_config_value(key, default=None, path=None):
        if key == "auth.api_key":
            return "k"
        return default

    monkeypatch.setattr(
        "workflo_agent.client.get_config_value", fake_get_config_value
    )

    client = ControlPlaneClient()

    assert client.api_key == "k"
    assert client.base_url == "https://api.tenantshield.dev"


def test_headers_property_returns_api_key_header():
    client = ControlPlaneClient(api_key="abc-123", base_url="https://api.test")
    assert client.headers == {"X-TenantShield-Key": "abc-123"}


def test_headers_property_handles_missing_key():
    client = ControlPlaneClient(api_key=None, base_url="https://api.test")
    assert client.headers == {"X-TenantShield-Key": ""}


def test_submit_run_calls_post_and_parses_json():
    resp = MagicMock()
    resp.json.return_value = {"run_id": "r-1", "status": "queued"}
    resp.raise_for_status.return_value = None

    patcher, client_mock = _patch_httpx_client()
    client_mock.post.return_value = resp

    with patcher:
        client = ControlPlaneClient(api_key="k", base_url="https://api.test")
        result = client.submit_run({"goal": "smoke", "markers": ["smoke"]})

    assert result == {"run_id": "r-1", "status": "queued"}

    client_mock.post.assert_called_once()
    args, kwargs = client_mock.post.call_args
    assert args[0] == "https://api.test/v1/runs"
    assert kwargs["json"] == {"goal": "smoke", "markers": ["smoke"]}
    resp.raise_for_status.assert_called_once()


def test_submit_run_passes_headers_and_timeout_to_httpx_client():
    resp = MagicMock()
    resp.json.return_value = {}
    resp.raise_for_status.return_value = None

    patcher, client_mock = _patch_httpx_client()
    client_mock.post.return_value = resp

    with patcher as client_cls:
        client = ControlPlaneClient(api_key="k", base_url="https://api.test")
        client.submit_run({})

        _, init_kwargs = client_cls.call_args
        assert init_kwargs["headers"] == {"X-TenantShield-Key": "k"}
        assert init_kwargs["timeout"] == 30


def test_get_run_calls_get_with_correct_url():
    resp = MagicMock()
    resp.json.return_value = {"run_id": "r-99", "status": "completed"}
    resp.raise_for_status.return_value = None

    patcher, client_mock = _patch_httpx_client()
    client_mock.get.return_value = resp

    with patcher:
        client = ControlPlaneClient(api_key="k", base_url="https://api.test")
        result = client.get_run("r-99")

    assert result == {"run_id": "r-99", "status": "completed"}
    client_mock.get.assert_called_once_with("https://api.test/v1/runs/r-99")
    resp.raise_for_status.assert_called_once()


def test_list_runs_calls_get_with_params():
    resp = MagicMock()
    resp.json.return_value = [{"run_id": "r-1"}, {"run_id": "r-2"}]
    resp.raise_for_status.return_value = None

    patcher, client_mock = _patch_httpx_client()
    client_mock.get.return_value = resp

    with patcher:
        client = ControlPlaneClient(api_key="k", base_url="https://api.test")
        result = client.list_runs(limit=15)

    assert result == [{"run_id": "r-1"}, {"run_id": "r-2"}]
    client_mock.get.assert_called_once_with(
        "https://api.test/v1/runs", params={"limit": 15}
    )
    resp.raise_for_status.assert_called_once()


def test_list_runs_uses_default_limit_of_twenty():
    resp = MagicMock()
    resp.json.return_value = []
    resp.raise_for_status.return_value = None

    patcher, client_mock = _patch_httpx_client()
    client_mock.get.return_value = resp

    with patcher:
        client = ControlPlaneClient(api_key="k", base_url="https://api.test")
        client.list_runs()

    client_mock.get.assert_called_once_with(
        "https://api.test/v1/runs", params={"limit": 20}
    )
