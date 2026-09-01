from workflo_worker.adapters.browser import BrowserAdapter
from workflo_schema import BrowserMode


def test_browser_adapter_init():
    adapter = BrowserAdapter(mode=BrowserMode.CONTAINER)
    assert adapter.mode == BrowserMode.CONTAINER


def test_grid_adapter():
    from workflo_worker.adapters.grid import GridAdapter
    grid = GridAdapter(provider="browserstack", username="user", access_key="key")
    endpoint = grid.build_endpoint()
    assert "browserstack" in endpoint
