"""Tests for the workflo sandbox executor.

These tests back the Phase 1 exit gate. They mock Docker and git so they
can run in CI without a Docker daemon or network access — the orchestration
logic is what we're validating, not the container runtime itself.
"""

from __future__ import annotations

import json
import subprocess
from contextlib import contextmanager
from datetime import datetime, UTC
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from workflo_executor import SandboxExecutor
from workflo_executor.docker_runner import ContainerConfig, ContainerResult
from workflo_schema.sandbox import (
    CanaryCheckResult,
    RunReport,
    SandboxSpec,
    SignedReceipt,
    TeardownProof,
)


def _make_spec(**overrides) -> SandboxSpec:
    defaults = {
        "sandbox_id": "test-sandbox-001",
        "repo_url": "https://github.com/example/repo.git",
        "run_spec": {"goal": "security", "markers": ["security"]},
        "timeout_seconds": 60,
    }
    defaults.update(overrides)
    return SandboxSpec(**defaults)


def _fake_git_clone_success(*args, **kwargs):
    cmd = args[0] if args else kwargs.get("args", [])
    rc = 0
    return subprocess.CompletedProcess(args=cmd, returncode=rc, stdout="", stderr="")


def _fake_canary_failure(target_host="https://example.com", timeout_seconds=3.0):
    from sandbox_isolation.network_policy import CanaryResult
    return CanaryResult(
        attempted_at=datetime.now(UTC),
        target_host=target_host,
        request_succeeded=False,
        error="Network is unreachable",
    )


def _fake_canary_success(target_host="https://example.com", timeout_seconds=3.0):
    from sandbox_isolation.network_policy import CanaryResult
    return CanaryResult(
        attempted_at=datetime.now(UTC),
        target_host=target_host,
        request_succeeded=True,
        error=None,
    )


def _fake_mount():
    """A fake EphemeralMount that doesn't touch the filesystem."""
    from pathlib import Path
    from sandbox_isolation.ephemeral_fs import EphemeralMount
    return EphemeralMount(
        sandbox_id="test-sandbox-001",
        mount_point=Path("/tmp/fake-mount-test-001"),
        size_mb=64,
    )


@contextmanager
def _patched_orchestration(
    *,
    container_stdout: str = 'WORKFLO_REPORT: {"total":5,"passed":5,"failed":0,"skipped":0}',
    container_timed_out: bool = False,
    container_returncode: int = 0,
    canary_side_effect=None,
    fs_gone: bool = True,
    container_removed: bool = True,
    container_id: str = "fake-container-id-1234",
):
    """Context manager that patches everything the executor calls.

    By default: clone succeeds, container runs cleanly, canary fails (good),
    teardown verifies container + fs are gone. Override the kwargs to simulate
    failures.

    NOTE: We inject a MagicMock runtime into the executor + use a real tempdir
    as the tmpfs mount so the executor's spec-file write actually has a place
    to land. The canary line is now embedded in container stdout (mirroring
    how the worker emits WORKFLO_CANARY: from inside the container), not
    patched in via attempt_canary_request on the host.
    """

    if canary_side_effect is None:
        canary_side_effect = _fake_canary_failure

    # Simulate the in-container worker emitting WORKFLO_CANARY
    # based on the canary_side_effect callable (still CanaryResult-shaped).
    canary_result = canary_side_effect()
    canary_line = (
        f'WORKFLO_CANARY: {{"attempted_at": "{datetime.now(UTC).isoformat()}", '
        f'"target_host": "{canary_result.target_host}", '
        f'"request_succeeded": {str(canary_result.request_succeeded).lower()}, '
        f'"error": {json.dumps(canary_result.error)}}}'
    )
    full_stdout = container_stdout + "\n" + canary_line

    from workflo_schema.sandbox import TeardownProof

    # Real tempdir so the executor's spec-file write succeeds.
    import tempfile as _tempfile
    real_mount_dir = _tempfile.mkdtemp(prefix="workflo-test-")
    from sandbox_isolation.ephemeral_fs import EphemeralMount
    fake_mount = EphemeralMount(
        sandbox_id="test-sandbox",
        mount_point=Path(real_mount_dir),
        size_mb=8,
    )

    def _fake_build_teardown_proof(sandbox_id, container_id, **kwargs):
        return TeardownProof(
            sandbox_id=sandbox_id,
            container_id=container_id,
            filesystem_wipe_method=kwargs.get("filesystem_wipe_method", "tmpfs_umount"),
            container_removed=container_removed,
            filesystem_removed=fs_gone,
            no_snapshot_retained=True,
            destroyed_at=datetime.now(UTC),
        )

    # Build a mock ContainerRuntime with all five methods
    mock_runtime = MagicMock()
    mock_runtime.create.return_value = container_id
    mock_runtime.wait.return_value = ContainerResult(
        container_id=container_id,
        returncode=container_returncode,
        stdout=full_stdout,
        stderr="",
        timed_out=container_timed_out,
    )
    mock_runtime.exists.return_value = not container_removed

    # Defensive: real tempdir teardown helper
    import shutil as _shutil

    with patch("subprocess.run", side_effect=_fake_git_clone_success), \
         patch("workflo_executor.executor.mount_tmpfs", return_value=fake_mount), \
         patch("workflo_executor.executor.unmount_tmpfs") as mock_unmount, \
         patch("workflo_executor.executor.verify_ephemeral_gone", return_value=fs_gone), \
         patch("workflo_executor.executor.build_teardown_proof", side_effect=_fake_build_teardown_proof):
        try:
            yield {
                "runtime": mock_runtime,
                "unmount": mock_unmount,
            }
        finally:
            _shutil.rmtree(real_mount_dir, ignore_errors=True)


@contextmanager
def _patched_clone_failure():
    """Patch the orchestration so git clone fails."""

    def fake_clone_fail(*args, **kwargs):
        cmd = args[0] if args else []
        if isinstance(cmd, list) and "clone" in cmd:
            return subprocess.CompletedProcess(
                args=cmd, returncode=128, stdout="", stderr="fatal: repository not found"
            )
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    with patch("subprocess.run", side_effect=fake_clone_fail), \
         patch("workflo_executor.executor.mount_tmpfs", return_value=_fake_mount()), \
         patch("workflo_executor.executor.unmount_tmpfs"):
        yield


class TestSandboxExecutorOrchestration:
    """Tests for the full orchestration flow — the Phase 1 exit gate backing."""

    def test_successful_run_produces_signed_receipt(self):
        """A successful run must: mount tmpfs, clone, run container, teardown, sign."""
        executor = SandboxExecutor(worker_image="workflo-worker:test")

        with _patched_orchestration() as mocks:
            executor.runtime = mocks["runtime"]
            result = executor.run(_make_spec())

        assert result.success is True
        assert result.receipt is not None
        assert result.receipt.signature is not None
        assert result.receipt.signature != ""
        assert result.receipt.public_key_fingerprint is not None
        assert result.receipt.public_key_fingerprint != ""
        assert result.report.total == 5
        assert result.report.passed == 5
        assert result.report.failed == 0
        assert result.receipt.teardown_proof.container_removed is True
        assert result.receipt.teardown_proof.filesystem_removed is True
        assert result.receipt.canary_check.request_succeeded is False
        mocks["runtime"].kill.assert_called_once_with("fake-container-id-1234")

    def test_receipt_signature_verifies_against_public_key(self):
        """The receipt must verify against the signer's public key (Claim #4)."""
        executor = SandboxExecutor(worker_image="workflo-worker:test")

        with _patched_orchestration(
            container_stdout='WORKFLO_REPORT: {"total":3,"passed":3,"failed":0}\n'
        ) as mocks:
            executor.runtime = mocks["runtime"]
            result = executor.run(_make_spec())

        from sandbox_isolation import verify_receipt_signature
        assert verify_receipt_signature(result.receipt, executor.signer.public_key) is True

    def test_tampered_receipt_fails_verification(self):
        """Modifying the report after signing must invalidate the signature."""
        executor = SandboxExecutor(worker_image="workflo-worker:test")

        with _patched_orchestration(
            container_stdout='WORKFLO_REPORT: {"total":3,"passed":3,"failed":0}\n'
        ) as mocks:
            executor.runtime = mocks["runtime"]
            result = executor.run(_make_spec())

        result.receipt.run_report.passed = 999  # tamper

        from sandbox_isolation import verify_receipt_signature
        assert verify_receipt_signature(result.receipt, executor.signer.public_key) is False

    def test_lifecycle_events_recorded_in_receipt(self):
        """Lifecycle events must be embedded in the receipt (audit trail)."""
        executor = SandboxExecutor(worker_image="workflo-worker:test")

        with _patched_orchestration(
            container_stdout='WORKFLO_REPORT: {"total":1,"passed":1}\n'
        ) as mocks:
            executor.runtime = mocks["runtime"]
            result = executor.run(_make_spec())

        events = result.receipt.lifecycle_events
        event_names = [e.event for e in events]
        assert "created" in event_names
        assert "repo_cloned" in event_names
        assert "tests_started" in event_names
        assert "tests_completed" in event_names
        assert "teardown_started" in event_names
        assert "destroyed" in event_names
        assert "receipt_signed" in event_names


class TestSandboxExecutorFailureModes:
    """Tests for failure paths — the executor must fail closed."""

    def test_git_clone_failure_produces_failure_receipt(self):
        executor = SandboxExecutor(worker_image="workflo-worker:test")

        with _patched_clone_failure():
            result = executor.run(_make_spec())

        assert result.success is False
        assert result.error is not None
        assert "clone" in result.error.lower() or "not found" in result.error.lower()
        assert result.receipt is not None  # even failures get a receipt

    def test_test_failures_marked_in_report(self):
        """Failed tests must appear in the report and mark run as unsuccessful."""
        executor = SandboxExecutor(worker_image="workflo-worker:test")

        with _patched_orchestration(
            container_stdout='WORKFLO_REPORT: {"total":5,"passed":3,"failed":2}\n'
        ) as mocks:
            executor.runtime = mocks["runtime"]
            result = executor.run(_make_spec())

        assert result.report.failed == 2
        assert result.success is False  # failures => not success

    def test_canary_success_flags_broken_isolation(self):
        """If canary SUCCEEDS, the run must know network isolation is broken."""
        executor = SandboxExecutor(worker_image="workflo-worker:test")

        with _patched_orchestration(canary_side_effect=_fake_canary_success) as mocks:
            executor.runtime = mocks["runtime"]
            result = executor.run(_make_spec())

        assert result.receipt.canary_check.request_succeeded is True
        assert result.success is False
        assert "network isolation" in result.error.lower() or "canary" in result.error.lower()

    def test_container_timeout_marks_run_failed(self):
        """A container that times out must produce a failed run."""
        executor = SandboxExecutor(worker_image="workflo-worker:test")

        with _patched_orchestration(container_timed_out=True, container_returncode=-1) as mocks:
            executor.runtime = mocks["runtime"]
            result = executor.run(_make_spec())

        assert result.success is False
        assert "timed out" in result.error.lower()

    def test_filesystem_not_removed_flags_failure(self):
        """If the tmpfs survives teardown, the run must report failure."""
        executor = SandboxExecutor(worker_image="workflo-worker:test")

        with _patched_orchestration(fs_gone=False, container_removed=True) as mocks:
            executor.runtime = mocks["runtime"]
            result = executor.run(_make_spec())

        assert result.success is False
        assert "filesystem" in result.error.lower() or "tmpfs" in result.error.lower()


class TestDockerRunner:
    """Unit tests for the Docker CLI wrapper — purely orchestration, no daemon."""

    def test_create_container_builds_correct_command(self):
        """The docker create command must include --network none and resource limits."""
        from workflo_executor.docker_runner import create_container

        captured = []

        def fake_run(*args, **kwargs):
            captured.append(args[0] if args else [])
            return subprocess.CompletedProcess(
                args=args[0] if args else [], returncode=0, stdout="abc123\n", stderr=""
            )

        config = ContainerConfig(
            image="workflo-worker:test",
            command=["pytest", "-v"],
            network_mode="none",
            memory_mb=1024,
            cpu_cores=1.5,
        )

        with patch("subprocess.run", side_effect=fake_run):
            cid = create_container(config)

        assert cid == "abc123"
        cmd = captured[0]
        assert "docker" in cmd
        assert "create" in cmd
        assert "--network" in cmd
        assert "none" in cmd
        assert "--memory" in cmd
        assert "1024m" in cmd
        assert "--cpus" in cmd
        assert "1.5" in cmd

    def test_create_container_raises_on_failure(self):
        from workflo_executor.docker_runner import create_container

        def fake_fail(*args, **kwargs):
            return subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr="docker daemon not running"
            )

        with patch("subprocess.run", side_effect=fake_fail):
            with pytest.raises(RuntimeError, match="docker create failed"):
                create_container(ContainerConfig(image="x", command=[]))

    def test_kill_container_is_idempotent(self):
        """kill_container must not raise even if the container is already gone."""
        from workflo_executor.docker_runner import kill_container

        with patch("subprocess.run", return_value=subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )):
            kill_container("nonexistent-id")  # must not raise


class TestContainerConfig:
    """Tests for the declarative container config."""

    def test_defaults_enforce_no_network(self):
        config = ContainerConfig(image="test", command=["echo"])
        assert config.network_mode == "none"

    def test_tmpfs_mounts_optional(self):
        config = ContainerConfig(image="test", command=[])
        # default_factory=dict — empty dict when not set, NOT None
        assert config.tmpfs_mounts == {}
        assert config.tmpfs_mounts is not None
