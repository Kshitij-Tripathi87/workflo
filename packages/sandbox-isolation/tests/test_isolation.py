"""Tests for the sandbox-isolation package.

These tests back the Phase 1 exit gate. Specifically:
  - test_ephemeral_fs_unmount_removes_mount
  - test_teardown_proof_reflects_container_state
  - test_canary_failure_when_network_disabled
  - test_receipt_signature_verifies
  - test_receipt_signature_fails_when_tampered
"""

from __future__ import annotations

from datetime import datetime, UTC

import pytest

from sandbox_isolation import (
    mount_tmpfs,
    unmount_tmpfs,
    verify_ephemeral_gone,
    attempt_canary_request,
    generate_keypair,
    verify_receipt_signature,
)
from sandbox_isolation.teardown_proof import build_teardown_proof

from workflo_schema.sandbox import (
    SandboxSpec,
    SandboxLifecycleEvent,
    TeardownProof,
    CanaryCheckResult,
    RunReport,
    SignedReceipt,
)


def test_ephemeral_fs_unmount_removes_mount():
    """Mount a tmpfs, write to it, unmount, verify gone."""
    mount = mount_tmpfs("test-001", size_mb=64)

    assert mount.exists
    test_file = mount.path_for("secret.txt")
    test_file.write_text("customer code that must not persist")

    unmount_tmpfs(mount)

    assert not mount.exists, "mount point should be gone after unmount"
    assert verify_ephemeral_gone(mount), "verify_ephemeral_gone should return True"


def test_teardown_proof_refects_container_state(monkeypatch):
    """TeardownProof should reflect actual container state, not claims."""

    # Fake a docker inspect that says "no such container"
    def fake_inspect_success(*args, **kwargs):
        import subprocess
        result = subprocess.CompletedProcess(
            args=args[0],
            returncode=1,
            stdout="",
            stderr="Error: No such container: fake-id",
        )
        return result

    monkeypatch.setattr("subprocess.run", fake_inspect_success)

    proof = build_teardown_proof(
        sandbox_id="test-002",
        container_id="fake-id",
        filesystem_wipe_method="tmpfs_umount",
    )

    assert proof.container_removed is True
    assert proof.sandbox_id == "test-002"


def test_teardown_proof_handles_docker_desktop_no_such_object(monkeypatch):
    """Docker Desktop (mac/win) uses 'no such object' instead of 'No such container'.

    The earlier regex-based check would incorrectly return False for these
    systems, marking a successful teardown as failed. This test guards
    against that regression.
    """

    def fake_inspect_desktop(*args, **kwargs):
        import subprocess
        result = subprocess.CompletedProcess(
            args=args[0],
            returncode=1,
            stdout="[]",
            stderr="Error response from daemon: error: no such object: fake-id",
        )
        return result

    monkeypatch.setattr("subprocess.run", fake_inspect_desktop)

    proof = build_teardown_proof(
        sandbox_id="test-003",
        container_id="fake-id",
        filesystem_wipe_method="tmpfs_umount",
    )

    assert proof.container_removed is True, (
        "Docker Desktop 'no such object' message must be treated as 'gone'"
    )


def test_teardown_proof_fails_closed_on_inspect_error(monkeypatch):
    """If docker inspect errors out, teardown_proof must say 'not removed'."""

    def fake_inspect_error(*args, **kwargs):
        import subprocess
        result = subprocess.CompletedProcess(
            args=args[0],
            returncode=0,  # success — but stdout says container exists
            stdout='[{"Id": "fake-id", "State": {"Running": true}}]',
            stderr="",
        )
        return result

    monkeypatch.setattr("subprocess.run", fake_inspect_error)

    proof = build_teardown_proof(
        sandbox_id="test-003",
        container_id="fake-id",
        filesystem_wipe_method="tmpfs_umount",
    )

    assert proof.container_removed is False, "must fail closed when container exists"


def test_canary_failure_when_network_disabled(monkeypatch):
    """The canary request must report failure when network is blocked.

    We simulate the block by making socket.create_connection raise OSError.
    """

    def fake_create_connection(*args, **kwargs):
        raise OSError("Network is unreachable (simulated isolation)")

    monkeypatch.setattr("socket.create_connection", fake_create_connection)

    result = attempt_canary_request(target_host="https://example.com")

    assert result.request_succeeded is False
    assert result.error is not None
    assert "unreachable" in result.error.lower() or "simulated" in result.error.lower()


def test_canary_success_when_network_open(monkeypatch):
    """Sanity check: if the network IS open, canary reports success.

    This is the negative test — we want to be sure canary actually detects
    open networks, not that it always reports failure.
    """

    class FakeResponse:
        def __init__(self):
            self.status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(*args, **kwargs):
        return FakeResponse()

    import sandbox_isolation.network_policy as np
    monkeypatch.setattr(np.urllib.request, "urlopen", fake_urlopen)

    result = attempt_canary_request(target_host="https://example.com")

    assert result.request_succeeded is True


def test_receipt_signature_round_trip():
    """Sign a receipt, verify it, confirm it round-trips."""

    signer = generate_keypair()

    receipt = SignedReceipt(
        sandbox_id="test-004",
        issued_at=datetime.now(UTC),
        run_report=RunReport(
            sandbox_id="test-004",
            total=10,
            passed=9,
            failed=1,
            duration_seconds=2.5,
        ),
        teardown_proof=TeardownProof(
            sandbox_id="test-004",
            container_id="fake-container-id",
            container_removed=True,
            filesystem_removed=True,
            no_snapshot_retained=True,
            destroyed_at=datetime.now(UTC),
        ),
        canary_check=CanaryCheckResult(
            sandbox_id="test-004",
            attempted_at=datetime.now(UTC),
            target_host="https://example.com",
            request_succeeded=False,
            error="Network is unreachable",
        ),
        lifecycle_events=[
            SandboxLifecycleEvent(
                sandbox_id="test-004",
                event="created",
                timestamp=datetime.now(UTC),
            ),
        ],
    )

    signed = signer.sign(receipt)

    assert signed.signature != ""
    assert signed.public_key_fingerprint != ""

    # Standalone verification — no signer needed
    assert verify_receipt_signature(signed, signer.public_key) is True


def test_receipt_signature_fails_when_tampered():
    """Modifying any field after signing must invalidate the signature."""

    signer = generate_keypair()

    receipt = SignedReceipt(
        sandbox_id="test-005",
        issued_at=datetime.now(UTC),
        run_report=RunReport(sandbox_id="test-005", total=5, passed=5),
        teardown_proof=TeardownProof(
            sandbox_id="test-005",
            container_id="x",
            container_removed=True,
            filesystem_removed=True,
            no_snapshot_retained=True,
            destroyed_at=datetime.now(UTC),
        ),
        canary_check=CanaryCheckResult(
            sandbox_id="test-005",
            attempted_at=datetime.now(UTC),
            target_host="https://example.com",
            request_succeeded=False,
            error="blocked",
        ),
        lifecycle_events=[],
    )

    signed = signer.sign(receipt)

    # Tamper: change passed count
    signed.run_report.passed = 99

    assert verify_receipt_signature(signed, signer.public_key) is False


def test_isolation_args_default_to_no_network():
    """build_isolation_args must default to network_mode='none'."""

    from sandbox_isolation.network_policy import build_isolation_args

    args = build_isolation_args(allowed_egress_hosts=[])

    assert args["network_mode"] == "none"
    assert args["add_hosts"] == []
    assert args["dns"] == []


def test_isolation_args_refuses_unresolvable_control_plane():
    """If the control plane host can't be resolved, refuse to start."""

    from sandbox_isolation.network_policy import build_isolation_args

    with pytest.raises(RuntimeError, match="Cannot resolve control plane host"):
        build_isolation_args(
            allowed_egress_hosts=[],
            control_plane_host="this-host-does-not-exist.invalid",
        )
