"""Guest supervisor tests: identity-first, honest cancellation, no widening."""

from __future__ import annotations

import pytest

from workflo_schema.contracts.common import utc_now_ms

from workflo_worker_host.guest_supervisor import (
    GuestCapabilityV1,
    GuestIdentityError,
    GuestSupervisor,
    SupervisorState,
)
from workflo_worker_host.protocol import (
    GuestMessageType,
    GuestProtocolSession,
    ProtocolError,
    build_guest_message,
    frame_message,
    parse_frame,
)


def _capability(**overrides) -> GuestCapabilityV1:
    values = {
        "capability_id": "cap-1",
        "attempt_id": "attempt-1",
        "sandbox_id": "sbx-1",
        "policy_digest": "sha256:" + "ab" * 32,
        "allowed_operations": ("tests.execute", "evidence.submit"),
        "issued_at": utc_now_ms(),
        # Far-future expiry keeps these tests clock-independent; expiry
        # enforcement itself is covered by test_expired_capability_is_refused.
        "expires_at": "2099-01-01T00:00:00.000Z",
    }
    values.update(overrides)
    return GuestCapabilityV1(**values)


def _supervisor(capability=None):
    sent: list = []
    supervisor = GuestSupervisor(
        capability=capability or _capability(),
        send_frame=sent.append,
    )
    return supervisor, sent


def test_identity_must_bind_the_attempt():
    supervisor, _ = _supervisor()
    with pytest.raises(GuestIdentityError):
        supervisor.verify_identity("attempt-OTHER", "sbx-1")


def test_ready_is_the_first_message_and_carries_binding():
    supervisor, sent = _supervisor()
    supervisor.verify_identity("attempt-1", "sbx-1")
    supervisor.announce_ready()

    # The HOST side verifies what it received.
    host_session = GuestProtocolSession(attempt_id="attempt-1", sandbox_id="sbx-1")
    message = host_session.receive(sent[0])
    assert message.message_type is GuestMessageType.GUEST_READY
    assert message.payload["capability_digest"]
    assert supervisor.state is SupervisorState.READY

    # A second guest_ready is out of protocol.
    with pytest.raises(ProtocolError):
        supervisor.announce_ready()


def test_heartbeat_is_protocol_valid_and_sequential():
    supervisor, sent = _supervisor()
    supervisor.verify_identity("attempt-1", "sbx-1")
    supervisor.announce_ready()
    supervisor.heartbeat()
    supervisor.heartbeat({"progress": "tests_running"})

    host_session = GuestProtocolSession(attempt_id="attempt-1", sandbox_id="sbx-1")
    parsed = [host_session.receive(frame) for frame in sent]
    assert [m.sequence_number for m in parsed] == [1, 2, 3]
    assert parsed[2].payload == {"progress": "tests_running"}


def test_shutdown_stops_the_supervisor():
    supervisor, _ = _supervisor()
    supervisor.verify_identity("attempt-1", "sbx-1")
    supervisor.announce_ready()
    host_frame = frame_message(
        build_guest_message(
            message_id="host-1",
            attempt_id="attempt-1",
            sandbox_id="sbx-1",
            sequence_number=1,
            message_type=GuestMessageType.SHUTDOWN_REQUESTED,
            sent_at=utc_now_ms(),
        )
    )
    assert supervisor.receive_host_message(host_frame) == "shutdown_requested"
    assert supervisor.state is SupervisorState.STOPPING


def test_cancellation_is_recorded_not_faked():
    supervisor, _ = _supervisor()
    supervisor.verify_identity("attempt-1", "sbx-1")
    supervisor.announce_ready()
    host_frame = frame_message(
        build_guest_message(
            message_id="host-2",
            attempt_id="attempt-1",
            sandbox_id="sbx-1",
            sequence_number=1,
            message_type=GuestMessageType.RUN_CANCELLATION_RECEIVED,
            sent_at=utc_now_ms(),
        )
    )
    assert supervisor.receive_host_message(host_frame) == "cancellation_recorded"
    assert supervisor.state is SupervisorState.CANCELLATION_RECEIVED
    assert supervisor.cancellation_received_at is not None


def test_guest_cannot_accept_unknown_host_operations():
    supervisor, _ = _supervisor()
    supervisor.verify_identity("attempt-1", "sbx-1")
    supervisor.announce_ready()
    # The host cannot send agent/tool messages to the guest — the guest
    # refuses to widen its own authority.
    with pytest.raises(ProtocolError):
        supervisor.receive_host_message(
            frame_message(
                build_guest_message(
                    message_id="host-3",
                    attempt_id="attempt-1",
                    sandbox_id="sbx-1",
                    sequence_number=1,
                    message_type=GuestMessageType.GUEST_READY,  # host may not send this
                    sent_at=utc_now_ms(),
                )
            )
        )


def test_failure_report_is_honest_and_terminal():
    supervisor, sent = _supervisor()
    supervisor.verify_identity("attempt-1", "sbx-1")
    supervisor.announce_ready()
    supervisor.report_failure("oom", "guest killed by memory ceiling")
    assert supervisor.state is SupervisorState.FAILED
    assert supervisor.failure_reported == {
        "error_class": "oom",
        "detail": "guest killed by memory ceiling",
    }
    # The host must consume the FULL stream in order — the strict sequence
    # rule rejects out-of-order consumption by design.
    host_session = GuestProtocolSession(attempt_id="attempt-1", sandbox_id="sbx-1")
    messages = [host_session.receive(frame) for frame in sent]
    assert messages[-1].message_type is GuestMessageType.GUEST_FAILURE_REPORTED


def test_evidence_manifest_is_digest_bound_and_metadata_only():
    supervisor, sent = _supervisor()
    supervisor.verify_identity("attempt-1", "sbx-1")
    supervisor.announce_ready()
    entry = supervisor.build_evidence_manifest(
        [
            {
                "artifact_type": "test_output",
                "sha256": "sha256:" + "aa" * 32,
                "size_bytes": 4321,
            }
        ]
    )
    # The digest binds the manifest bytes; host re-derives it.
    from workflo_schema.contracts.canonical import digest_matches

    assert digest_matches(entry["manifest_digest"], entry["manifest"])
    host_session = GuestProtocolSession(attempt_id="attempt-1", sandbox_id="sbx-1")
    messages = [host_session.receive(frame) for frame in sent]
    assert messages[-1].payload["manifest_digest"] == entry["manifest_digest"]


def test_expired_capability_is_refused():
    expired = _capability(
        issued_at="2020-01-01T00:00:00.000Z",
        expires_at="2020-01-02T00:00:00.000Z",
    )
    supervisor, _ = _supervisor(capability=expired)
    with pytest.raises(GuestIdentityError, match="expired"):
        supervisor.verify_identity("attempt-1", "sbx-1")
    assert supervisor.state is SupervisorState.BOOTING
    assert supervisor._sequence == 0  # nothing was ever announced
