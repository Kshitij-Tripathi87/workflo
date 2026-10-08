"""Tests for the Browser and Grid adapters."""

from workflo_worker.adapters.browser import BrowserAdapter
from workflo_worker.adapters.grid import GridAdapter
from workflo_schema import BrowserMode


# ---------------------------------------------------------------------------
# BrowserAdapter
# ---------------------------------------------------------------------------


def test_browser_adapter_defaults_to_container():
    adapter = BrowserAdapter()
    assert adapter.mode == BrowserMode.CONTAINER


def test_browser_adapter_container_mode():
    adapter = BrowserAdapter(BrowserMode.CONTAINER)
    assert adapter.mode == BrowserMode.CONTAINER


def test_browser_adapter_real_fleet_mode():
    adapter = BrowserAdapter(BrowserMode.REAL_FLEET, remote_url="ws://grid.example.test")
    assert adapter.mode == BrowserMode.REAL_FLEET
    assert adapter.remote_url == "ws://grid.example.test"


# ---------------------------------------------------------------------------
# GridAdapter.build_endpoint
# ---------------------------------------------------------------------------


def test_grid_adapter_browserstack_endpoint_contains_browserstack():
    grid = GridAdapter(provider="browserstack", username="u", access_key="k")
    endpoint = grid.build_endpoint()
    assert "browserstack" in endpoint
    assert "u" in endpoint
    assert "k" in endpoint


def test_grid_adapter_saucelabs_endpoint():
    grid = GridAdapter(provider="saucelabs", username="u", access_key="k")
    endpoint = grid.build_endpoint()
    assert "saucelabs" in endpoint


def test_grid_adapter_private_endpoint_contains_grid():
    grid = GridAdapter(provider="private", username="u", access_key="k")
    endpoint = grid.build_endpoint()
    assert "grid" in endpoint
    assert "u" in endpoint
    assert "k" in endpoint


def test_grid_adapter_unknown_provider_raises_value_error():
    import pytest

    grid = GridAdapter(provider="bogus")
    with pytest.raises(ValueError):
        grid.build_endpoint()


# ---------------------------------------------------------------------------
# GridAdapter.build_capabilities
# ---------------------------------------------------------------------------


def test_grid_adapter_browserstack_capabilities_with_device():
    grid = GridAdapter(provider="browserstack")
    caps = grid.build_capabilities(browser="chrome", device="iPhone 14")
    assert caps["browserName"] == "chrome"
    assert "bstack:options" in caps
    assert caps["bstack:options"]["deviceName"] == "iPhone 14"
    assert caps["bstack:options"]["realMobile"] is True


def test_grid_adapter_browserstack_capabilities_no_device():
    grid = GridAdapter(provider="browserstack")
    caps = grid.build_capabilities(browser="firefox")
    assert caps["browserName"] == "firefox"
    # No device -> bstack:options should not be present (only added when device is set)
    assert "bstack:options" not in caps


def test_grid_adapter_non_browserstack_ignores_device():
    """For non-browserstack providers, the device should not add bstack:options."""
    grid = GridAdapter(provider="saucelabs")
    caps = grid.build_capabilities(browser="chrome", device="iPhone 14")
    assert caps["browserName"] == "chrome"
    assert "bstack:options" not in caps
