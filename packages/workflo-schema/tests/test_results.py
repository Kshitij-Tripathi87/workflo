"""Tests for result models."""
import json
from datetime import datetime
from workflo_schema import TestResult, RunSummary


class TestTestResult:
    def test_basic_serialization(self):
        now = datetime(2025, 6, 15, 10, 30, 0)
        tr = TestResult(
            nodeid="tests/test_auth.py::test_login",
            status="passed",
            duration=1.234,
            markers=["security", "auth"],
            soc2_controls=["CC6.1"],
            assertion="User cannot access other tenant's data",
            tenant_pair=["tenant-A", "tenant-B"],
            pattern="cross_tenant_read",
            actual_status=200,
            screenshot_path="/tmp/screenshot.png",
            timestamp=now,
        )
        assert tr.nodeid == "tests/test_auth.py::test_login"
        assert tr.status == "passed"
        assert tr.duration == 1.234
        assert tr.markers == ["security", "auth"]
        assert tr.soc2_controls == ["CC6.1"]
        assert tr.pattern == "cross_tenant_read"

    def test_minimal_serialization(self):
        tr = TestResult(nodeid="tests/minimal_test.py::TestMinimal::test_x", status="passed", duration=0.123)
        data = tr.model_dump()
        reloaded = TestResult(**data)
        assert reloaded.nodeid == "tests/minimal_test.py::TestMinimal::test_x"
        assert reloaded.status == "passed"
        assert reloaded.duration == 0.123
        assert reloaded.markers == []
        assert reloaded.assertion == ""

    def test_optional_round_trip(self):
        tr = TestResult(
            nodeid="test_opt.py::test",
            status="failed",
            duration=3.0,
            error="Timed out after 3000ms",
            actual_status=500,
        )
        dumped = tr.model_dump()
        reloaded = TestResult(**dumped)
        assert reloaded.status == "failed"
        assert reloaded.error == "Timed out after 3000ms"
        assert reloaded.actual_status == 500
        assert reloaded.pattern is None
        assert reloaded.timestamp is None

    def test_skipped_status(self):
        tr = TestResult(nodeid="skip_me.py::test", status="skipped", duration=0.0)
        assert tr.status == "skipped"
        assert tr.duration == 0.0

    def test_deselected_status(self):
        tr = TestResult(nodeid="deselect.py::test", status="deselected", duration=0.0)
        assert tr.status == "deselected"
        assert tr.duration == 0.0


class TestRunSummary:
    def test_pass_rate_all_pass(self):
        summary = RunSummary(total=10, passed=10, failed=0, skipped=0)
        assert summary.pass_rate_pct == 100.0

    def test_pass_rate_half(self):
        summary = RunSummary(total=10, passed=5, failed=5, skipped=0)
        assert summary.pass_rate_pct == 50.0

    def test_pass_rate_mixed(self):
        summary = RunSummary(total=100, passed=87, failed=10, skipped=3)
        assert summary.pass_rate_pct == 87.0

    def test_pass_rate_fractional(self):
        s = RunSummary(total=3, passed=2, failed=1, skipped=0)
        assert s.pass_rate_pct == round((2 / 3) * 100, 2)

    def test_pass_rate_empty(self):
        summary = RunSummary(total=0, passed=0, failed=0, skipped=0)
        assert summary.pass_rate_pct == 0.0

    def test_pass_rate_all_fail(self):
        summary = RunSummary(total=5, passed=0, failed=5, skipped=0)
        assert summary.pass_rate_pct == 0.0

    def test_defaults(self):
        summary = RunSummary()
        assert summary.total == 0
        assert summary.passed == 0
        assert summary.failed == 0
        assert summary.skipped == 0
        assert summary.duration_seconds == 0.0
        assert summary.pass_rate_pct == 0.0

    def test_duration_field(self):
        summary = RunSummary(total=10, passed=8, failed=2, duration_seconds=120.5)
        assert summary.duration_seconds == 120.5

    def test_positive_controls_field(self):
        summary = RunSummary(total=10, passed=10, positive_controls_passed=2)
        assert summary.positive_controls_passed == 2

    def test_round_trip_json(self):
        original = RunSummary(total=20, passed=18, failed=1, skipped=1, duration_seconds=42.0)
        reloaded = RunSummary.model_validate_json(original.model_dump_json())
        assert reloaded.total == 20
        assert reloaded.passed == 18
        assert reloaded.failed == 1
        assert reloaded.skipped == 1
        assert reloaded.duration_seconds == 42.0
        assert reloaded.pass_rate_pct == 90.0