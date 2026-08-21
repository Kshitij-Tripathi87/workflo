"""Sandbox isolation tests for the validation pipeline.

These tests verify that:
  1. The pipeline works in a temporary directory, not the host working dir
  2. The temp directory is cleaned up after the run (via TemporaryDirectory)
  3. Gate commands execute inside the cloned repo dir, not the host
  4. No host files leak into the result
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from validate_phase2.orchestrator import (
    Gate,
    GateResult,
    clone_repo,
    resolve_baseline,
    run_gate,
    run_validation,
)


class TestSandboxIsolation:
    """Verify the pipeline's sandbox boundaries."""

    def test_clone_repo_writes_to_target_dir(self, temp_work_dir, local_git_repo):
        """clone_repo() must write the clone into the passed-in tempdir,
        not the host working directory or any other location."""
        work = temp_work_dir / "work"
        work.mkdir()
        result = clone_repo(str(local_git_repo), work)
        assert result.exists()
        assert result.parent == work
        assert (result / ".git").exists()
        assert (result / "README.md").exists()
        # And NOT in the parent tempdir at the top level
        assert not (temp_work_dir / "README.md").exists()

    def test_tempdir_is_cleaned_up_after_run(self, local_git_repo):
        """run_validation() uses tempfile.TemporaryDirectory which guarantees
        cleanup. Verify by inspecting the host temp dir before/after."""
        before = set(os.listdir(tempfile.gettempdir()))
        result = run_validation(
            repo_url=str(local_git_repo),
            model_endpoint="http://localhost:9999",  # unreachable; will be skipped
            model="test-model",
            flags=["architecture"],
            scope_paths=["."],
        )
        # Pipeline should have completed (gates may fail; that's OK)
        assert result.finished_at != ""
        after = set(os.listdir(tempfile.gettempdir()))
        # No new top-level validate-phase2-* dirs left behind
        new_dirs = (after - before) & {
            d for d in after if d.startswith("validate-phase2-")
        }
        assert new_dirs == set(), f"Tempdirs leaked: {new_dirs}"

    def test_gate_runs_in_repo_cwd(self, local_git_repo):
        """A gate subprocess must execute in the repo dir, not the host cwd.
        Verified by making the gate write a marker file with a relative path."""
        gate = Gate(
            name="cwd-test",
            command=[
                sys.executable, "-c",
                "open('marker.txt','w').write(open('README.md').read())",
            ],
            timeout=30,
        )
        result = run_gate(gate, cwd=local_git_repo)
        assert result.passed, f"Gate failed: stdout={result.stdout_tail!r} stderr={result.stderr_tail!r}"
        marker = local_git_repo / "marker.txt"
        assert marker.exists(), "Gate didn't write the marker in cwd"
        assert "# test" in marker.read_text()

    def test_gate_command_does_not_leak_host_path(self, local_git_repo):
        """A gate's recorded command must not reference the host temp dir.
        The command list is captured as a space-joined string; check that
        it doesn't include /tmp/ or any tempdir path."""
        gate = Gate(
            name="echo-test",
            command=[sys.executable, "-c", "print('hello')"],
            timeout=30,
        )
        result = run_gate(gate, cwd=local_git_repo)
        assert result.command == " ".join(gate.command)
        assert "tmp" not in result.command.lower()
        assert result.passed

    def test_run_validation_uses_tempfile(self, local_git_repo):
        """run_validation() must wrap everything in tempfile.TemporaryDirectory,
        which means after the call returns there should be NO leftover
        cloned repo on the host filesystem."""
        before_dirs = set(os.listdir(tempfile.gettempdir()))
        run_validation(
            repo_url=str(local_git_repo),
            model_endpoint="http://localhost:9999",
            model="m",
            flags=["architecture"],
            scope_paths=["."],
        )
        after_dirs = set(os.listdir(tempfile.gettempdir()))
        leaked = (after_dirs - before_dirs) & {
            d for d in after_dirs if d.startswith("validate-phase2-")
        }
        assert leaked == set(), f"Sandbox tempdir leaked: {leaked}"

    def test_clone_failure_does_not_corrupt_workdir(self, temp_work_dir):
        """If clone_repo fails (bad URL), the tempdir must still be intact
        and no partial state should remain."""
        with pytest.raises(subprocess.CalledProcessError):
            clone_repo("https://invalid.example.invalid/nonexistent.git", temp_work_dir)
        # Tempdir should still exist but be empty (no partial clone)
        assert temp_work_dir.exists()
        assert list(temp_work_dir.iterdir()) == []
