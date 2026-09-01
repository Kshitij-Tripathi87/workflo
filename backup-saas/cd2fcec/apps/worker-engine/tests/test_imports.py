"""Test that all worker-engine modules import cleanly."""

from workflo_worker.executor import execute_run, _parse_results
from workflo_worker.streamer import ResultStreamer
from workflo_worker.adapters.browser import BrowserAdapter
from workflo_worker.adapters.grid import GridAdapter
from workflo_schema import RunSpec, RunSummary, BrowserMode


def test_executor_imports():
    assert callable(execute_run)
    assert callable(_parse_results)


def test_streamer_imports():
    assert isinstance(ResultStreamer, type)


def test_browser_adapter_imports():
    assert isinstance(BrowserAdapter, type)


def test_grid_adapter_imports():
    assert isinstance(GridAdapter, type)


def test_schema_imports():
    assert isinstance(RunSpec, type)
    assert isinstance(RunSummary, type)
    assert isinstance(BrowserMode, type)
