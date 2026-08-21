"""Log-capture tests.

Verify that:
  1. stdout from a gate subprocess is captured
  2. stderr from a gate subprocess is captured
  3. Output is truncated to a bounded length (avoid memory blowup)
  4. Failed-gate diagnostics (stderr_tail) flow through to JSON report
  5. Pipeline logs (on_log callback) receive each phase transition
  6. The orchestrator records timing for each gate
"""

from __future__ import annotations

import json
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
    run_gate,
    run_validation,
)


class TestStdoutStderrCapture:

    def test_stdout_captured(self, temp_work_dir):
        gate = Gate(
            name="stdout-gate",
            command=[sys.executable, "-c", "print('hello stdout')"],
            timeout=10,
        )
        result = run_gate(gate, cwd=temp_work_dir)
        assert "hello stdout" in result.stdout_tail

    def test_stderr_captured(self, temp_work_dir):
        gate = Gate(
            name="stderr-gate",
            command=[
                sys.executable, "-c",
                "import sys; sys.stderr.write('error msg\\n')",
            ],
            timeout=10,
        )
        result = run_gate(gate, cwd=temp_work_dir)
        assert "error msg" in result.stderr_tail

    def test_stdout_truncated_to_1000_chars(self, temp_work_dir):
        """Long output must be truncated; we keep only the last 1000 chars."""
        gate = Gate(
            name="big-output",
            command=[
                sys.executable, "-c",
                "print('A' * 5000)",
            ],
            timeout=10,
        )
        result = run_gate(gate, cwd=temp_work_dir)
        assert len(result.stdout_tail) <= 1000
        # The LAST 1000 chars are kept — output is just A's + newline,
        # so the captured tail must be a long run of A's.
        stripped = result.stdout_tail.rstrip("\n")
        assert stripped.endswith("A" * 100) or len(stripped) == 1000

    def test_combined_stdout_stderr(self, temp_work_dir):
        gate = Gate(
            name="both",
            command=[
                sys.executable, "-c",
                "import sys; print('out'); sys.stderr.write('err\\n'); sys.exit(1)",
            ],
            timeout=10,
        )
        result = run_gate(gate, cwd=temp_work_dir)
        assert result.passed is False
        assert "out" in result.stdout_tail
        assert "err" in result.stderr_tail

    def test_duration_recorded(self, temp_work_dir):
        gate = Gate(
            name="timing",
            command=[sys.executable, "-c", "import time; time.sleep(0.2)"],
            timeout=10,
        )
        result = run_gate(gate, cwd=temp_work_dir)
        assert 0.15 < result.duration_s < 2.0

    def test_command_string_recorded(self, temp_work_dir):
        gate = Gate(
            name="echo-cmd",
            command=[sys.executable, "-c", "print('x')"],
            timeout=10,
        )
        result = run_gate(gate, cwd=temp_work_dir)
        assert result.command == f"{sys.executable} -c print('x')"


class TestGateResultSerialization:

    def test_to_dict_round_trip(self):
        g = GateResult(
            name="x", passed=True, duration_s=1.23,
            stdout_tail="out", stderr_tail="err", command="cmd",
        )
        d = g.to_dict()
        assert d["name"] == "x"
        assert d["passed"] is True
        assert d["duration_s"] == 1.23
        assert d["command"] == "cmd"
        assert d["stdout_tail"] == "out"
        assert d["stderr_tail"] == "err"


class TestPipelineLogging:

    def test_on_log_called_for_each_phase(self, local_git_repo):
        """The on_log callback must fire for: cloning, baseline, gate start, gate result."""
        logs = []

        def capture(msg: str) -> None:
            logs.append(msg)

        with patch("validate_phase2.orchestrator.DEFAULT_GATES", [
            Gate(name="quick", command=[sys.executable, "-c", "print('ok')"], timeout=10),
        ]):
            run_validation(
                repo_url=str(local_git_repo),
                model_endpoint="http://localhost:9999",
                model="m",
                flags=["architecture"],
                scope_paths=["."],
                on_log=capture,
            )

        # Spot-check log content
        text = "\n".join(logs)
        assert "cloning" in text
        assert "baseline=" in text
        assert "gate: quick" in text
        assert "PASS" in text

    def test_baseline_and_head_recorded_in_result(self, local_git_repo):
        """The result must carry the computed baseline + head commit hashes."""
        with patch("validate_phase2.orchestrator.DEFAULT_GATES", [
            Gate(name="q", command=[sys.executable, "-c", "print(1)"], timeout=10),
        ]):
            result = run_validation(
                repo_url=str(local_git_repo),
                model_endpoint="http://localhost:9999",
                model="m",
                flags=["architecture"],
                scope_paths=["."],
            )
        # Both should be hex strings of similar length
        assert len(result.baseline) >= 7
        assert len(result.head) >= 7
        assert result.baseline != result.head or result.baseline != ""

    def test_started_and_finished_timestamps_present(self, local_git_repo):
        with patch("validate_phase2.orchestrator.DEFAULT_GATES", [
            Gate(name="q", command=[sys.executable, "-c", "print(1)"], timeout=10),
        ]):
            result = run_validation(
                repo_url=str(local_git_repo),
                model_endpoint="http://localhost:9999",
                model="m",
                flags=["architecture"],
                scope_paths=["."],
            )
        assert result.started_at != ""
        assert result.finished_at != ""
        assert result.started_at <= result.finished_at

    def test_failed_gate_stderr_visible_in_result(self, local_git_repo):
        """A failed gate's stderr must be retrievable via result.gates."""
        with patch("validate_phase2.orchestrator.DEFAULT_GATES", [
            Gate(
                name="verbose-fail",
                command=[sys.executable, "-c",
                         "import sys; sys.stderr.write('failure detail'); sys.exit(1)"],
                timeout=10,
            ),
        ]):
            result = run_validation(
                repo_url=str(local_git_repo),
                model_endpoint="http://localhost:9999",
                model="m",
                flags=["architecture"],
                scope_paths=["."],
            )
        assert len(result.gates) == 1
        assert result.gates[0].passed is False
        assert "failure detail" in result.gates[0].stderr_tail
