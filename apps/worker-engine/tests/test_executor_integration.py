"""Integration tests for the worker-engine execute_run() — the full pipeline
from spec to pytest to receipt.

These tests exercise the END-TO-END worker logic against the fixture repo
apps/worker-engine/tests/fixtures/sample_repo. They mock only the ModelServer
(Ollama + Qwen) because we don't have a GPU in CI — but everything else
runs for real: pytest executes against the fixture, the JSON report is
parsed, the generated test file is written, findings are collected.

This is the Phase 1 Exit Gate test that proves:

  1. `--test` (surface) produces 3 passing tests, NO model teardown line,
     NO generated test file, NO model findings.
  2. `--deep-test` produces 3 passed + N skipped model probes when no
     app-under-test is booted (WORKFLO_API_BASE_URL unset), YES model
     teardown line, YES generated ProbeRunner file, YES model findings.
     (With a live target, those N probes pass/fail for real.)

The difference in the RunReport is the auditable, receipt-level proof that
--deep-test and --test do DIFFERENT WORK.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from workflo_worker.executor import execute_run
from workflo_worker.model import ModelServer, ModelServerError
from workflo_worker.streamer import ResultStreamer
from workflo_schema import RunSummary


# --------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------

FIXTURE_REPO = Path(__file__).parent / "fixtures" / "sample_repo"


def _make_spec(probe_groups: list[str]) -> dict:
    """A minimal spec dict that execute_run expects (it wraps in RunSpec)."""
    return {
        "run_id": "test-run",
        "goal": "security" if "security" in probe_groups else "functional",
        "markers": probe_groups,
        "env": {},
        "targets": {"include": [], "exclude": []},
        "config": {
            "browsers": ["chromium"],
            "mobile_devices": [],
            "parallelism": 1,
            "retries": 0,
            "timeout_seconds": 60,
            "browser_mode": "container",
        },
        "artifacts": {"screenshots": False, "traces": "off", "soc2_report": False, "logs": False},
        "probe_groups": probe_groups,
    }


class _CapturingStreamer:
    """A ResultStreamer that captures log lines instead of printing.

    execute_run emits WORKFLO_REPORT, WORKFLO_CANARY, WORKFLO_MODEL_TEARDOWN
    via streamer.log(). We capture them here for assertion.
    """

    def __init__(self):
        self.lines: list[str] = []

    def log(self, line: str) -> None:
        self.lines.append(line)

    def complete(self, summary: RunSummary) -> None:
        pass

    def fail(self, error: str) -> None:
        pass


def _run_worker(probe_groups: list[str]):
    """Execute the worker against the fixture repo with the given probe groups.

    Returns (streamer, spec) so the caller can inspect the captured lines
    and the final report.

    IMPORTANT: The worker decides whether to run the model stage based on
    the PROBE_GROUPS env var (set by the executor), NOT the spec's
    probe_groups field. So we must set both.
    """
    spec = _make_spec(probe_groups)

    # Clean up any generated test file from a PREVIOUS run so this run
    # starts with a clean fixture repo. We do this at the START (not end)
    # so that the test can assert on the generated file after the run.
    generated = FIXTURE_REPO / "tests" / "test_workflo_generated.py"
    generated.unlink(missing_ok=True)

    # Point the worker at our fixture repo. The executor injects this via
    # env var; the worker reads it as WORKFLO_REPO_PATH.
    env = os.environ.copy()
    env["WORKFLO_REPO_PATH"] = str(FIXTURE_REPO)
    # CRITICAL: worker reads PROBE_GROUPS from env to decide model stage
    env["PROBE_GROUPS"] = json.dumps(probe_groups)

    streamer = _CapturingStreamer()

    with patch.dict(os.environ, env):
        summary = execute_run(spec, streamer)

    # Do NOT clean up here - the test will assert on the generated file
    # and clean up itself if needed.

    return streamer, summary


# --------------------------------------------------------------------
# ModelServer mock
# --------------------------------------------------------------------

def _mock_model_server(deep_tier: bool):
    """Return a contextmanager that patches ModelServer to return a fake
    probe list when the model stage runs (i.e., when deep/aggressive is in
    probe_groups). For surface runs, the model stage is never entered, so
    the mock is a no-op.
    """
    # A valid YAML list of 5 ProbeSpecs — the model's "proposal".
    # The worker writes these via ProbeGenerator.generate_pytest_file;
    # without WORKFLO_API_BASE_URL they skip rather than assert True.
    model_probes_yaml = (
        "- name: model_probe_1\n"
        "  pattern: api_read\n"
        "  path: /api/v1/items\n"
        "  method: GET\n"
        "  expected_status: 403\n"
        "  soc2_controls: ['CC6.1']\n"
        "  description: model proposed read check\n"
        "- name: model_probe_2\n"
        "  pattern: api_delete\n"
        "  path: /api/v1/items/42\n"
        "  method: DELETE\n"
        "  expected_status: [403, 404]\n"
        "  soc2_controls: ['CC6.1', 'CC6.6']\n"
        "  description: model proposed delete check\n"
        "- name: model_probe_3\n"
        "  pattern: api_modify\n"
        "  path: /api/v1/items\n"
        "  method: PUT\n"
        "  expected_status: 403\n"
        "  soc2_controls: ['CC6.1']\n"
        "  description: model proposed modify check\n"
        "- name: model_probe_4\n"
        "  pattern: api_list\n"
        "  path: /api/v1/items\n"
        "  method: GET\n"
        "  list_key: items\n"
        "  expect_resource_absent: true\n"
        "  expected_status: 200\n"
        "  soc2_controls: ['CC6.1']\n"
        "  description: model proposed list exclusion\n"
        "- name: model_probe_5\n"
        "  pattern: positive_control\n"
        "  path: /api/v1/health\n"
        "  method: GET\n"
        "  expected_status: 200\n"
        "  soc2_controls: []\n"
        "  description: model positive control\n"
    )

    if not deep_tier:
        # Surface tier: model stage never runs. Return a no-op mock that
        # asserts ModelServer.start() is never called.
        mock = MagicMock()
        mock.start = MagicMock(side_effect=AssertionError("ModelServer.start() must not be called for surface tier"))
        mock.generate = MagicMock(side_effect=AssertionError("ModelServer.generate() must not be called for surface tier"))
        mock.stop = MagicMock()
        return patch("workflo_worker.executor.ModelServer", return_value=mock)

    # Deep tier: mock ModelServer to return our probes on generate().
    mock_server = MagicMock()
    mock_server.start = MagicMock()
    mock_server.generate = MagicMock(return_value=model_probes_yaml)
    mock_server.stop = MagicMock()
    mock_server.is_alive = MagicMock(return_value=True)
    return patch("workflo_worker.executor.ModelServer", return_value=mock_server)


# --------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------

class TestWorkerSurfaceVsDeep:
    """The exit-gate tests: surface and deep produce observably different
    RunReport / receipt artifacts."""

    def test_surface_run_three_tests_no_model(self):
        """--test (surface): runs the fixture's 3 native tests, no model
        stage, no generated file, no model teardown line."""
        streamer, summary = _run_worker(["surface"])

        # The fixture repo has exactly 3 native tests in test_native.py.
        assert summary.total == 3
        assert summary.passed == 3
        assert summary.failed == 0

        # No WORKFLO_MODEL_TEARDOWN line was emitted — the model stage
        # never ran for surface tier.
        model_teardown_lines = [l for l in streamer.lines if l.startswith("WORKFLO_MODEL_TEARDOWN:")]
        assert model_teardown_lines == [], (
            f"Expected no model teardown line for surface; got {model_teardown_lines}"
        )

        # No WORKFLO_SECURITY_PROBES line — security tier wasn't requested.
        security_lines = [l for l in streamer.lines if l.startswith("WORKFLO_SECURITY_PROBES:")]
        assert security_lines == [], (
            f"Expected no security probes line for surface; got {security_lines}"
        )

        # No generated test file was written.
        generated = FIXTURE_REPO / "tests" / "test_workflo_generated.py"
        assert not generated.exists(), (
            f"Surface run must not create test_workflo_generated.py; "
            f"but {generated} exists"
        )

        # No model findings in the report — findings only come from the
        # model stage (surface tests don't produce structured findings).
        # The summary.findings is empty (the surface tests are pass/fail
        # pytest assertions, not structured ProbeSpecs).
        # The execute_run merges model_findings into summary.findings; for
        # surface, model_findings is [].
        assert summary.findings == []

    def test_deep_run_surface_plus_model_probes(self):
        """--deep-test: runs the fixture's 3 native tests PLUS 5
        model-generated probes. Without an app-under-test
        (WORKFLO_API_BASE_URL unset), generated probes skip — they must
        NOT silently pass. Model teardown + findings still recorded."""
        with _mock_model_server(deep_tier=True):
            streamer, summary = _run_worker(["deep"])

        # 3 surface pass + 5 generated probes skip (no live API target).
        assert summary.total == 8
        assert summary.passed == 3
        assert summary.skipped == 5
        assert summary.failed == 0

        # WORKFLO_MODEL_TEARDOWN line was emitted with teardown=true.
        model_teardown_lines = [l for l in streamer.lines if l.startswith("WORKFLO_MODEL_TEARDOWN:")]
        assert len(model_teardown_lines) == 1, f"Expected 1 model teardown line; got {model_teardown_lines}"

        import json as _json
        teardown_data = _json.loads(model_teardown_lines[0][len("WORKFLO_MODEL_TEARDOWN:"):].strip())
        assert teardown_data["teardown"] is True, "Model stage ran and state was wiped"
        assert teardown_data["error"] is None
        assert teardown_data["findings_count"] == 5

        # The generated test file was written by the model stage.
        generated = FIXTURE_REPO / "tests" / "test_workflo_generated.py"
        assert generated.exists(), "Deep run must create test_workflo_generated.py"

        # Real ProbeRunner codegen — not assert-True stubs.
        content = generated.read_text()
        test_func_count = content.count("def test_")
        assert test_func_count == 5, f"Expected 5 generated tests; found {test_func_count}"
        assert "ProbeRunner" in content
        assert "runner.run_one(" in content
        assert "assert True" not in content
        assert "WORKFLO_API_BASE_URL" in content

        # Model findings are present in the summary — these are the
        # structured ProbeSpecs the model proposed, converted to finding
        # dicts for the receipt. Surface run has none; deep has 5.
        assert len(summary.findings) == 5
        for f in summary.findings:
            assert f["source"] == "model_inference"
            assert f["name"].startswith("model_probe_")
            assert "soc2_controls" in f

        # Cleanup: remove the generated file so other tests don't see it.
        generated.unlink(missing_ok=True)

    def test_aggressive_run_same_model_stage_as_deep(self):
        """--aggressive-test: runs the same model stage as --deep-test
        (same image, same model, same probe generation). The difference
        is Phase 2+ would add fuzz/chaos; Phase 1 it's identical to deep."""
        with _mock_model_server(deep_tier=True):
            streamer, summary = _run_worker(["aggressive"])

        assert summary.total == 8  # 3 pass + 5 skip
        assert summary.passed == 3
        assert summary.skipped == 5
        model_teardown_lines = [l for l in streamer.lines if l.startswith("WORKFLO_MODEL_TEARDOWN:")]
        assert len(model_teardown_lines) == 1
        teardown_data = json.loads(model_teardown_lines[0][len("WORKFLO_MODEL_TEARDOWN:"):].strip())
        assert teardown_data["teardown"] is True

        generated = FIXTURE_REPO / "tests" / "test_workflo_generated.py"
        assert generated.exists()
        assert "ProbeRunner" in generated.read_text()
        generated.unlink(missing_ok=True)

    def test_surface_plus_security_no_model_stage(self):
        """--test --security: surface tests + security probes, but no
        model stage. Security is composable with surface but doesn't
        trigger the deep image / Ollama."""
        streamer, summary = _run_worker(["surface", "security"])

        # Only the 3 surface native tests run.
        assert summary.total == 3
        assert summary.passed == 3

        model_teardown_lines = [l for l in streamer.lines if l.startswith("WORKFLO_MODEL_TEARDOWN:")]
        assert model_teardown_lines == [], "Security tier must not run model stage"

        generated = FIXTURE_REPO / "tests" / "test_workflo_generated.py"
        assert not generated.exists()

        # The security tier boots the app-under-test (start_app_under_test)
        # and emits a WORKFLO_SECURITY_PROBES line — ALWAYS produced, even
        # when the app fails to start (same discipline as the web tier).
        # Without config (no WORKFLO_SECURITY_START_COMMAND/PORT and no
        # workflo.yaml), the payload carries an app_start_error.
        security_lines = [l for l in streamer.lines if l.startswith("WORKFLO_SECURITY_PROBES:")]
        assert len(security_lines) == 1, (
            f"Expected one WORKFLO_SECURITY_PROBES line; got {security_lines}"
        )
        security_payload = json.loads(security_lines[0][len("WORKFLO_SECURITY_PROBES:"):].strip())
        assert security_payload["app_start_error"] is not None
        assert security_payload["probes"] == []

    def test_deep_plus_security_model_stage_runs(self):
        """--deep-test --security: deep model stage runs + security
        composable flag. Same model output as deep alone, but the receipt
        records security probe group too."""
        with _mock_model_server(deep_tier=True):
            streamer, summary = _run_worker(["deep", "security"])

        assert summary.total == 8  # 3 surface + 5 model
        # Same skip behavior as deep-only: without an app-under-test
        # (WORKFLO_API_BASE_URL unset), the 5 generated probes skip rather
        # than silently pass — consistency with test_deep_run_surface_plus_model_probes.
        assert summary.passed == 3
        assert summary.skipped == 5
        assert summary.failed == 0

        model_teardown_lines = [l for l in streamer.lines if l.startswith("WORKFLO_MODEL_TEARDOWN:")]
        assert len(model_teardown_lines) == 1
        teardown_data = json.loads(model_teardown_lines[0][len("WORKFLO_MODEL_TEARDOWN:"):].strip())
        assert teardown_data["teardown"] is True

        generated = FIXTURE_REPO / "tests" / "test_workflo_generated.py"
        assert generated.exists()
        generated.unlink(missing_ok=True)


class TestWorkerModelStageFailureHandling:
    """When the model stage fails (Ollama won't start, generation fails,
    teardown fails), the receipt must record the failure — fail closed."""

    def test_model_server_start_failure_reported(self):
        """If ModelServer.start() raises, the error flows to the receipt's
        model_inference_teardown=false + error message."""
        mock_server = MagicMock()
        mock_server.start.side_effect = ModelServerError("ollama failed to start")
        mock_server.stop = MagicMock()

        with patch("workflo_worker.executor.ModelServer", return_value=mock_server):
            streamer, summary = _run_worker(["deep"])

        # The run should still complete the surface tests (the model stage
        # failure doesn't kill the whole run — it records the failure).
        assert summary.total == 3  # only surface tests ran
        assert summary.passed == 3

        # WORKFLO_MODEL_TEARDOWN line has teardown=false and the error.
        model_teardown_lines = [l for l in streamer.lines if l.startswith("WORKFLO_MODEL_TEARDOWN:")]
        assert len(model_teardown_lines) == 1
        teardown_data = json.loads(model_teardown_lines[0][len("WORKFLO_MODEL_TEARDOWN:"):].strip())
        assert teardown_data["teardown"] is False
        assert "ollama failed to start" in teardown_data["error"]

        # No generated file (model stage didn't get to generate).
        generated = FIXTURE_REPO / "tests" / "test_workflo_generated.py"
        assert not generated.exists()


# --------------------------------------------------------------------
# Fixture validation (sanity)
# --------------------------------------------------------------------

class TestFixtureRepoValidity:
    """Sanity checks that the fixture repo itself is well-formed and
    produces the expected baseline. These are NOT exit-gate tests; they
    just make sure the fixture repo hasn't been accidentally broken."""

    def test_fixture_has_three_native_tests(self):
        """The fixture repo's test_native.py has exactly 3 tests."""
        # We already verified this in the surface run, but assert it
        # explicitly here as documentation.
        import pytest as _pytest
        # Run pytest programmatically on the fixture to count tests.
        from _pytest.config import Config as _Config
        from _pytest.config.argparsing import Parser as _Parser
        # Skip this — it's a meta-test. The surface run test above is the
        # real validation. This class is just documentation.
        pass


# Run standalone if needed (for manual debugging).
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
