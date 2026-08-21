"""Tenant Shield pytest plugin.

Captures per-test outcomes and any isolation evidence pushed by the
isolation library, and on session finish writes a JSON results file in the
schema defined by `workflo.reporting.results`.

Activation:
- The plugin is registered as a `pytest11` entry point so it load automatically
  when `workflo` is installed.
- It only WRITES the results file when the user passes
  `--tenant-shield-results <path>`. Otherwise it is a passive no-op (the
  evidence sink stays unregistered, so isolation records are not captured).
"""

from __future__ import annotations

import os

import pytest

from workflo.isolation import evidence
from workflo.reporting.results import RunReport, TestResult


def _opts(config):
    return (
        config.getoption("--tenant-shield-results", default=None),
        config.getoption("--tenant-shield-suite", default="tenant-isolation"),
        config.getoption("--tenant-shield-screenshot-dir", default="reports/screenshots"),
    )


def pytest_addoption(parser):
    group = parser.getgroup("workflo")
    group.addoption(
        "--tenant-shield-results",
        action="store",
        default=None,
        help="Write Tenant Shield JSON results to this path after the session.",
    )
    group.addoption(
        "--tenant-shield-suite",
        action="store",
        default="tenant-isolation",
        help="Suite label for the results report.",
    )
    group.addoption(
        "--tenant-shield-screenshot-dir",
        action="store",
        default="reports/screenshots",
        help="Directory screenshots are saved to (used to link evidence).",
    )


def pytest_configure(config):
    _, suite, _ = _opts(config)
    config._workflo_report = RunReport.new(suite=suite)


def pytest_runtest_setup(item):
    try:
        sink = evidence.register_sink(item.nodeid)
        item._ts_sink = sink
        evidence.set_current_key(item.nodeid)
    except Exception:
        item._ts_sink = None


# We collect reports per-item via the hookwrapper on makereport, which has
# access to the item (logreport does not). This is the reliable way to tie
# reports back to the item across phases.
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call):
    outcome = yield
    try:
        report = outcome.get_result()
        reports = getattr(item, "_ts_reports", None)
        if reports is None:
            reports = []
            item._ts_reports = reports
        reports.append({"when": report.when, "outcome": report.outcome, "longrepr": getattr(report, "longreprtext", "")})
        if report.when == "call":
            item._ts_call_duration = getattr(report, "duration", 0.0)
    except Exception:
        pass


def pytest_runtest_teardown(item, nextitem):
    try:
        evidence.set_current_key(None)
        sink = getattr(item, "_ts_sink", None)
        config = item.config
        results_path, suite, screenshot_dir = _opts(config)
        report = config._workflo_report

        status, error = _derive_status(getattr(item, "_ts_reports", []))
        markers = [m.name for m in item.iter_markers()]
        duration = getattr(item, "_ts_call_duration", 0.0)

        assertion = ""
        tenant_pair = []
        soc2_controls = []
        pattern = None
        actual_status = None
        records = []
        if sink is not None:
            records, tenant_pair, soc2_controls = sink.to_confirmation()
        if records:
            assertion = " | ".join(dict.fromkeys(r.assertion for r in records))
            pattern = records[0].pattern
            actual_status = records[0].actual_status

        screenshot_path = _screenshot_path(item, screenshot_dir, status)

        result = TestResult(
            test_name=item.name,
            nodeid=item.nodeid,
            status=status,
            duration=duration,
            markers=[m for m in markers if m not in ("",)],
            assertion=assertion,
            tenant_pair=tenant_pair,
            soc2_controls=soc2_controls,
            pattern=pattern,
            actual_status=actual_status,
            screenshot_path=screenshot_path,
            error=error[:1000] if error else None,
            timestamp=report.timestamp,
        )
        report.results.append(result)
        evidence.clear_sink(item.nodeid)
    except Exception:
        try:
            evidence.clear_sink(item.nodeid)
        except Exception:
            pass


def _derive_status(reports):
    """Decide the final test status from per-phase reports."""
    setup = [r for r in reports if r["when"] == "setup"]
    call = [r for r in reports if r["when"] == "call"]
    teardown = [r for r in reports if r["when"] == "teardown"]

    error = ""
    if setup:
        if setup[0]["outcome"] == "skipped":
            return "skipped", setup[0].get("longrepr", "") or ""
        if setup[0]["outcome"] in ("failed",):
            error = setup[0].get("longrepr", "")
            return "failed", error
    if call:
        outcome = call[0]["outcome"]
        error = call[0].get("longrepr", "")
        return {"passed": "passed", "failed": "failed", "skipped": "skipped"}.get(outcome, outcome), error
    if teardown and teardown[0]["outcome"] == "failed":
        return "failed", teardown[0].get("longrepr", "")
    return "passed", ""


def _screenshot_path(item, screenshot_dir: str, status: str):
    if status != "failed":
        return None
    name = item.nodeid.replace("::", "_").replace("/", "_")
    path = os.path.join(screenshot_dir, f"{name}_fail.png")
    return path if os.path.exists(path) else None


def pytest_sessionfinish(session, exitstatus):
    try:
        config = session.config
        results_path, suite, _ = _opts(config)
        if not results_path:
            return
        report = config._workflo_report
        os.makedirs(os.path.dirname(os.path.abspath(results_path)) or ".", exist_ok=True)
        with open(results_path, "w", encoding="utf-8") as f:
            f.write(report.to_json())
    except Exception:
        pass
