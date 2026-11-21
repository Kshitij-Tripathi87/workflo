"""Guest runtime tests: capability gate, identity, manifest, shutdown.

The transport is a scripted two-way queue — no VM, no sockets — so the
in-guest control flow is exercised end to end: capability first or refuse,
identity mismatch refuses, workload result travels in the manifest, and
host protocol violations are reported rather than obeyed.
"""

from __future__ import annotations

import pytest
from workflo_schema.contracts.canonical import digest_of
from workflo_worker_host.guest_runtime import (
    GuestSliceError,
    parse_boot_identity,
    run_guest_slice,
)
from workflo_worker_host.guest_supervisor import GuestCapabilityV1
from workflo_worker_host.protocol import (
    GuestMessageType,
    build_guest_message,
    frame_message,
    parse_frame,
)
from workflo_worker_host.workload import PINNED_MARKER_SHA256


class QueueTransport:
    """Two-way queue: host writes `from_host`, guest reads; vice versa."""

    def __init__(self, from_host: list, *, fail_send: Exception | None = None):
        self.from_host = list(from_host)
        self.to_host: list = []
        self._fail_send = fail_send

    def send(self, frame: bytes) -> None:
        if self._fail_send is not None:
            raise self._fail_send
        self.to_host.append(frame)

    def receive(self, *, timeout: float = 1.0):
        if self.from_host:
            return self.from_host.pop(0)
        return None


def _capability_dict(
    *,
    attempt_id="attempt-1",
    sandbox_id="sbx-1",
    issued="2026-01-01T00:00:00.000Z",
    expires="2099-01-01T00:00:00.000Z",
) -> dict:
    return GuestCapabilityV1(
        capability_id="cap-sbx-1",
        attempt_id=attempt_id,
        sandbox_id=sandbox_id,
        policy_digest="sha256:" + "ab" * 32,
        allowed_operations=("tests.execute",),
        issued_at=issued,
        expires_at=expires,
    ).model_dump(mode="json")


def _capability_frame(
    *, attempt_id="attempt-1", sandbox_id="sbx-1", tamper: bool = False,
    issued="2026-01-01T00:00:00.000Z",
    expires="2099-01-01T00:00:00.000Z",
) -> bytes:
    capability = _capability_dict(
        attempt_id=attempt_id, sandbox_id=sandbox_id,
        issued=issued, expires=expires,
    )
    digest = digest_of(capability)
    if tamper:
        capability = dict(capability, policy_digest="sha256:" + "cd" * 32)
    return frame_message(
        build_guest_message(
            message_id="host-capability-1",
            attempt_id=attempt_id,
            sandbox_id=sandbox_id,
            sequence_number=1,
            message_type=GuestMessageType.RUN_CAPABILITY_DELIVERED,
            sent_at="2026-01-01T00:00:00.000Z",
            payload={"capability": capability, "capability_digest": digest},
        )
    )


def _host_frame(message_type: GuestMessageType, *, seq: int = 2) -> bytes:
    return frame_message(
        build_guest_message(
            message_id=f"host-{seq}",
            attempt_id="attempt-1",
            sandbox_id="sbx-1",
            sequence_number=seq,
            message_type=message_type,
            sent_at="2026-01-01T00:00:00.000Z",
            payload={"deadline": "2099-01-01T00:00:00.000Z"},
        )
    )


CMDLINE = (
    "console=ttyS0 reboot=k panic=1 workflo.attempt_id=attempt-1 "
    "workflo.sandbox_id=sbx-1"
)


def test_parse_boot_identity_extracts_both_ids():
    assert parse_boot_identity(CMDLINE) == ("attempt-1", "sbx-1")


def test_parse_boot_identity_refuses_missing_ids():
    with pytest.raises(GuestSliceError, match="missing workflo"):
        parse_boot_identity("console=ttyS0 reboot=k")


def test_slice_completes_with_manifest_and_shutdown(tmp_path):
    transport = QueueTransport(
        [_capability_frame(), _host_frame(GuestMessageType.SHUTDOWN_REQUESTED)]
    )
    result = run_guest_slice(
        transport=transport, cmdline=CMDLINE, workspace=str(tmp_path)
    )
    assert result.status == "completed"
    assert result.workload["ok"] is True

    # First message out must be GUEST_READY with the capability digest.
    ready = parse_frame(transport.to_host[0])
    assert ready.message_type is GuestMessageType.GUEST_READY

    # Second: evidence manifest carrying the workload result + digest.
    manifest_msg = parse_frame(transport.to_host[1])
    assert manifest_msg.message_type is GuestMessageType.EVIDENCE_MANIFEST_SUBMITTED
    payload = manifest_msg.payload
    assert payload["manifest_digest"] == digest_of(payload["manifest"])
    workload = payload["manifest"]["workload_result"]
    assert workload["ok"] is True
    marker = next(c for c in workload["checks"] if c["name"] == "workspace_marker")
    assert marker["ok"] is True
    # Workload actually touched the workspace the host provided.
    assert (tmp_path / "workflo-slice-marker.bin").exists()


def test_slice_refuses_when_first_frame_is_not_capability(tmp_path):
    wrong = frame_message(
        build_guest_message(
            message_id="msg-1",
            attempt_id="attempt-1",
            sandbox_id="sbx-1",
            sequence_number=1,
            message_type=GuestMessageType.GUEST_READY,  # guest-to-host type
            sent_at="2026-01-01T00:00:00.000Z",
            payload={},
        )
    )
    transport = QueueTransport([wrong])
    with pytest.raises(GuestSliceError, match="not run_capability_delivered"):
        run_guest_slice(
            transport=transport, cmdline=CMDLINE, workspace=str(tmp_path)
        )
    # Nothing was announced: no frames left the guest.
    assert transport.to_host == []


def test_slice_refuses_tampered_capability(tmp_path):
    transport = QueueTransport([_capability_frame(tamper=True)])
    with pytest.raises(GuestSliceError, match="digest does not match"):
        run_guest_slice(
            transport=transport, cmdline=CMDLINE, workspace=str(tmp_path)
        )
    assert transport.to_host == []


def test_slice_refuses_identity_mismatch(tmp_path):
    # Capability binds a different attempt than the boot args declare.
    transport = QueueTransport([_capability_frame(attempt_id="attempt-EVIL")])
    with pytest.raises(GuestSliceError, match="identity verification failed"):
        run_guest_slice(
            transport=transport, cmdline=CMDLINE, workspace=str(tmp_path)
        )
    assert transport.to_host == []


def test_slice_refuses_expired_capability(tmp_path):
    transport = QueueTransport(
        [
            _capability_frame(
                issued="2020-01-01T00:00:00.000Z",
                expires="2020-06-01T00:00:00.000Z",
            )
        ]
    )
    with pytest.raises(GuestSliceError, match="identity verification failed"):
        run_guest_slice(
            transport=transport, cmdline=CMDLINE, workspace=str(tmp_path)
        )
    assert transport.to_host == []


def test_slice_refuses_when_no_capability_arrives(tmp_path):
    transport = QueueTransport([])  # host sends nothing
    with pytest.raises(GuestSliceError, match="no capability arrived"):
        run_guest_slice(
            transport=transport,
            cmdline=CMDLINE,
            workspace=str(tmp_path),
            capability_timeout_seconds=0.05,
        )


def test_unknown_host_message_is_reported_not_obeyed(tmp_path):
    transport = QueueTransport(
        [
            _capability_frame(),
            # Host sends a guest-only type: protocol violation.
            frame_message(
                build_guest_message(
                    message_id="host-bad",
                    attempt_id="attempt-1",
                    sandbox_id="sbx-1",
                    sequence_number=2,
                    message_type=GuestMessageType.GUEST_READY,
                    sent_at="2026-01-01T00:00:00.000Z",
                    payload={},
                )
            ),
        ]
    )
    result = run_guest_slice(
        transport=transport, cmdline=CMDLINE, workspace=str(tmp_path)
    )
    assert result.status == "failed"
    assert "protocol violation" in result.detail
    # The violation was REPORTED to the host (last frame out).
    failure = parse_frame(transport.to_host[-1])
    assert failure.message_type is GuestMessageType.GUEST_FAILURE_REPORTED
    assert failure.payload["error_class"] == "protocol_violation"


def test_cancellation_is_recorded_and_shutdown_still_required(tmp_path):
    transport = QueueTransport(
        [
            _capability_frame(),
            _host_frame(GuestMessageType.RUN_CANCELLATION_RECEIVED),
            _host_frame(GuestMessageType.SHUTDOWN_REQUESTED, seq=3),
        ]
    )
    result = run_guest_slice(
        transport=transport, cmdline=CMDLINE, workspace=str(tmp_path)
    )
    # Cancellation alone does not end the slice; shutdown does.
    assert result.status == "completed"


def test_shutdown_timeout_reports_failure(tmp_path):
    transport = QueueTransport([_capability_frame()])  # no shutdown ever
    result = run_guest_slice(
        transport=transport,
        cmdline=CMDLINE,
        workspace=str(tmp_path),
        shutdown_timeout_seconds=0.05,
    )
    assert result.status == "failed"
    failure = parse_frame(transport.to_host[-1])
    assert failure.message_type is GuestMessageType.GUEST_FAILURE_REPORTED
    assert failure.payload["error_class"] == "shutdown_timeout"


def test_workload_result_digest_pins_the_marker(tmp_path):
    # The workload result inside the manifest must reflect the pinned
    # marker digest — a diverging guest hash fails the check host-visible.
    transport = QueueTransport(
        [_capability_frame(), _host_frame(GuestMessageType.SHUTDOWN_REQUESTED)]
    )
    result = run_guest_slice(
        transport=transport, cmdline=CMDLINE, workspace=str(tmp_path)
    )
    assert result.workload["ok"] is True
    determinism = next(
        c for c in result.workload["checks"] if c["name"] == "hash_determinism"
    )
    assert PINNED_MARKER_SHA256 in determinism["detail"]
