"""End-to-end integration test.

Runs the full validation pipeline against this very repository and
verifies that all 4 report formats are produced and structurally sound.

Marked SLOW because the pytest gate can run hundreds of unit tests.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from validate_phase2.orchestrator import Gate, run_validation
from validate_phase2.reporters import REPORTERS


# This is the repo we're testing — workflowpro-tests itself.
REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLO_TESTS_DIR = REPO_ROOT  # alias for clarity


pytestmark = pytest.mark.slow


@pytest.fixture
def fast_default_gates():
    """Replace DEFAULT_GATES with a single fast gate so the integration
    test doesn't run the entire pytest suite (which can take many minutes).
    """
    fast_gate = Gate(
        name="quick-ok",
        command=[sys.executable, "-c", "print('ok')"],
        timeout=10,
    )
    with patch("validate_phase2.orchestrator.DEFAULT_GATES", [fast_gate]):
        yield [fast_gate]


class TestEndToEnd:
    """Run the full pipeline against the local repo and verify outputs."""

    def test_full_pipeline_produces_all_four_reports(self, temp_work_dir, fast_default_gates):
        """A complete run against the local repo must produce 4 report files."""
        out_dir = temp_work_dir / "reports"

        result = run_validation(
            repo_url=str(WORKFLO_TESTS_DIR),
            model_endpoint="http://localhost:9999",  # unreachable; LLM skip OK
            model="Qwen/Qwen2.5-Coder-7B-AWQ",
            flags=["architecture", "patterns"],
            scope_paths=["apps/control-plane", "apps/workflo-cli"],
        )

        # Result must be populated
        assert result.gates, "No gates ran"
        assert result.started_at != ""
        assert result.finished_at != ""

        # Write all 4 reports via the REPORTERS dispatch
        for fmt in ("md", "json", "sarif", "html"):
            out_path = out_dir / f"validation_report.{fmt}"
            REPORTERS[fmt](result, out_path)
            assert out_path.exists(), f"{fmt} report not written"
            assert out_path.stat().st_size > 200, f"{fmt} report is too small"

    def test_result_serializes_to_summary_dict(self, temp_work_dir, fast_default_gates):
        """to_summary_dict must produce a JSON-serializable structure."""
        result = run_validation(
            repo_url=str(WORKFLO_TESTS_DIR),
            model_endpoint="http://localhost:9999",
            model="m",
            flags=["architecture"],
            scope_paths=["apps/control-plane"],
        )
        summary = result.to_summary_dict()
        # Must be JSON-serializable (no datetimes leaking as objects)
        serialized = json.dumps(summary, default=str)
        assert isinstance(serialized, str)
        # And round-trip
        data = json.loads(serialized)
        assert data["repo"] == str(WORKFLO_TESTS_DIR)
        assert "findings" in data
        assert "gates" in data
        assert "summary" in data

    def test_severity_counts_default_to_zeros(self, temp_work_dir, fast_default_gates):
        """A pipeline that never calls LLM (gates fail OR LLM down) must
        produce zero findings and zero severity counts, NOT crash."""
        result = run_validation(
            repo_url=str(WORKFLO_TESTS_DIR),
            model_endpoint="http://localhost:9999",
            model="m",
            flags=["architecture"],
            scope_paths=["."],
        )
        counts = result.severity_counts
        for sev in ("critical", "high", "medium", "low", "info"):
            assert counts[sev] == 0

    def test_dry_run_clone_succeeds(self):
        """Pre-flight: confirm the local repo exists."""
        assert (WORKFLO_TESTS_DIR / ".git").exists()
