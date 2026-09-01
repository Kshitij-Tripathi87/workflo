"""Gate execution tests.

Verify that:
  1. Gates actually run subprocesses (not silently skipped)
  2. Passing gates are recorded as passed=True
  3. Failing gates are recorded as passed=False with exit code captured
  4. Timeout gates are recorded as passed=False with TIMEOUT marker
  5. The pipeline short-circuits to LLM-skip when any required gate fails
  6. LLM is invoked only when ALL gates pass
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from validate_phase2.orchestrator import (
    DEFAULT_GATES,
    Gate,
    GateResult,
    call_vllm,
    run_gate,
    run_validation,
)


class TestGateExecution:
    """A gate must actually execute the subprocess; no silent skipping."""

    def test_passing_gate_recorded_as_passed(self, temp_work_dir):
        gate = Gate(
            name="true-gate",
            command=[sys.executable, "-c", "print('ok')"],
            timeout=10,
        )
        result = run_gate(gate, cwd=temp_work_dir)
        assert result.passed is True
        assert result.duration_s > 0
        assert "ok" in result.stdout_tail

    def test_failing_gate_recorded_as_failed(self, temp_work_dir):
        gate = Gate(
            name="false-gate",
            command=[sys.executable, "-c", "import sys; sys.exit(1)"],
            timeout=10,
        )
        result = run_gate(gate, cwd=temp_work_dir)
        assert result.passed is False

    def test_gate_actually_runs_subprocess(self, temp_work_dir):
        """Prove the gate executed by side-effect on the filesystem."""
        marker = temp_work_dir / "gate_ran.txt"
        gate = Gate(
            name="marker-gate",
            command=[
                sys.executable, "-c",
                f"open(r'{marker}', 'w').write('ran')",
            ],
            timeout=10,
        )
        result = run_gate(gate, cwd=temp_work_dir)
        assert marker.exists(), "Gate subprocess did not execute"
        assert marker.read_text() == "ran"
        assert result.passed

    def test_gate_timeout_recorded(self, temp_work_dir):
        """A gate exceeding timeout must be marked failed with TIMEOUT marker."""
        gate = Gate(
            name="slow-gate",
            command=[sys.executable, "-c", "import time; time.sleep(30)"],
            timeout=2,
        )
        start = time.monotonic()
        result = run_gate(gate, cwd=temp_work_dir)
        elapsed = time.monotonic() - start
        assert result.passed is False
        assert "TIMEOUT" in result.stderr_tail
        assert elapsed < 10, f"Took too long ({elapsed}s) — timeout didn't fire"

    def test_gate_stderr_captured_on_failure(self, temp_work_dir):
        gate = Gate(
            name="stderr-gate",
            command=[
                sys.executable, "-c",
                "import sys; sys.stderr.write('boom\\n'); sys.exit(2)",
            ],
            timeout=10,
        )
        result = run_gate(gate, cwd=temp_work_dir)
        assert result.passed is False
        assert "boom" in result.stderr_tail


class TestGateShortCircuit:
    """When any required gate fails, the pipeline must NOT call the LLM."""

    def test_llm_skipped_when_gate_fails(self, local_git_repo):
        """Force a gate failure and verify call_vllm is never invoked."""
        with patch("validate_phase2.orchestrator.call_vllm") as mock_call:
            # Create a gate that will fail
            bad_gate = Gate(
                name="intentional-fail",
                command=[sys.executable, "-c", "import sys; sys.exit(1)"],
                timeout=10,
            )
            with patch("validate_phase2.orchestrator.DEFAULT_GATES", [bad_gate]):
                result = run_validation(
                    repo_url=str(local_git_repo),
                    model_endpoint="http://localhost:9999",
                    model="m",
                    flags=["architecture"],
                    scope_paths=["."],
                )
            mock_call.assert_not_called()
            assert result.findings == []
            assert "Gates failed" in result.notes
            assert result.all_gates_passed is False

    def test_llm_called_only_when_all_gates_pass(self, local_git_repo, temp_work_dir):
        """When all gates pass, call_vllm IS invoked."""
        # Add a tiny file to the local repo so diff is non-empty
        (local_git_repo / "extra.txt").write_text("hello")
        import subprocess
        subprocess.run(["git", "add", "extra.txt"], cwd=local_git_repo, check=True)
        subprocess.run(
            ["git", "-c", "user.email=t@t", "-c", "user.name=t",
             "commit", "-m", "second"],
            cwd=local_git_repo, check=True,
        )

        passing_gates = [
            Gate(name="quick-ok",
                 command=[sys.executable, "-c", "print('ok')"], timeout=10),
        ]
        with patch("validate_phase2.orchestrator.DEFAULT_GATES", passing_gates), \
             patch("validate_phase2.orchestrator.call_vllm") as mock_call:
            mock_call.return_value = {
                "findings": [{
                    "id": "TEST-001", "severity": "medium",
                    "category": "test", "file": "x.py", "line": 1,
                    "pattern": "demo", "message": "m", "suggestion": "s",
                    "baseline_regression": False,
                }],
                "summary": {"medium": 1}, "notes": "ok",
            }
            result = run_validation(
                repo_url=str(local_git_repo),
                model_endpoint="http://localhost:9999",
                model="m",
                flags=["architecture"],
                scope_paths=["."],
            )
        mock_call.assert_called_once()
        assert result.findings, "findings should be populated"
        assert result.all_gates_passed


class TestDefaultGatesConfiguration:
    """The DEFAULT_GATES list itself must be sane."""

    def test_at_least_one_gate(self):
        assert len(DEFAULT_GATES) >= 1

    def test_gate_names_unique(self):
        names = [g.name for g in DEFAULT_GATES]
        assert len(names) == len(set(names)), f"Duplicate gate names: {names}"

    def test_gate_timeouts_positive(self):
        for g in DEFAULT_GATES:
            assert g.timeout > 0, f"Gate {g.name} has zero/negative timeout"

    def test_gate_commands_non_empty(self):
        for g in DEFAULT_GATES:
            assert len(g.command) >= 2, f"Gate {g.name} command too short: {g.command}"
