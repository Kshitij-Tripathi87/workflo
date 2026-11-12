"""Guest/host protocol tests (brief §3.4): strict, bound, replay-safe."""

from __future__ import annotations

import pytest

from workflo_schema.contracts.common import utc_now_ms

from workflo_worker_host.protocol import (
    MAX_MESSAGE_BYTES,
    MAX_PAYLOAD_BYTES,
    PROTOCOL_VERSION,
    BindingError,
    GuestMessageV1,
    GuestMessageType,
    GuestProtocolSession,
    ProtocolError,
    SequenceError,
    UnknownOperationError,
    VersionMismatchError,
    build_guest_message,
    frame_message,
    parse_frame,
)

ATTEMPT = "attempt-1"
SANDBOX = "sbx-1"


def _reframe(body: bytes) -> bytes:
    """Re-pack a mutated body so the length prefix matches (real peers do
    this; a stale prefix is exactly the truncated-frame error)."""
    import struct

    return struct.pack(">I", len(body)) + body


def _mutate_frame(message, old: bytes, new: bytes) -> bytes:
    raw = frame_message(message)
    return _reframe(raw[4:].replace(old, new))


def _msg(seq: int = 1, kind: GuestMessageType = GuestMessageType.GUEST_READY, **overrides):
    values = {
        "message_id": f"msg-{seq}",
        "attempt_id": ATTEMPT,
        "sandbox_id": SANDBOX,
        "sequence_number": seq,
        "message_type": kind,
        "sent_at": utc_now_ms(),
        "payload": {},
    }
    values.update(overrides)
    return build_guest_message(**values)


def _session() -> GuestProtocolSession:
    return GuestProtocolSession(attempt_id=ATTEMPT, sandbox_id=SANDBOX)


def test_frame_round_trip():
    session = _session()
    message = _msg(1)
    parsed = session.receive(frame_message(message))
    assert parsed.message_type is GuestMessageType.GUEST_READY
    assert session.last_sequence == 1


def test_unknown_operation_rejected():
    raw = _mutate_frame(_msg(1), b'"guest_ready"', b'"open_a_shell"')
    with pytest.raises(UnknownOperationError):
        parse_frame(raw)


def test_unknown_message_type_not_silently_ignored():
    with pytest.raises(UnknownOperationError):
        parse_frame(
            _mutate_frame(
                _msg(1, GuestMessageType.SHUTDOWN_REQUESTED),
                b'"shutdown_requested"',
                b'"host_shell"',
            )
        )


def test_version_mismatch_rejected():
    with pytest.raises(VersionMismatchError):
        parse_frame(_mutate_frame(_msg(1), b'"protocol_version":1', b'"protocol_version":99'))


def test_wrong_attempt_binding_rejected():
    session = _session()
    foreign = _msg(1, attempt_id="attempt-other")
    with pytest.raises(BindingError):
        session.receive(frame_message(foreign))


def test_wrong_sandbox_binding_rejected():
    session = _session()
    foreign = _msg(1, sandbox_id="sbx-other")
    with pytest.raises(BindingError):
        session.receive(frame_message(foreign))


def test_replay_rejected():
    session = _session()
    frame = frame_message(_msg(1))
    session.receive(frame)
    with pytest.raises(SequenceError):
        session.receive(frame)


def test_sequence_gap_rejected():
    session = _session()
    session.receive(frame_message(_msg(1)))
    with pytest.raises(SequenceError):
        session.receive(frame_message(_msg(3)))


def test_payload_digest_must_match():
    message = build_guest_message(
        message_id="msg-1",
        attempt_id=ATTEMPT,
        sandbox_id=SANDBOX,
        sequence_number=1,
        message_type=GuestMessageType.EVIDENCE_MANIFEST_SUBMITTED,
        sent_at=utc_now_ms(),
        payload={"manifest_digest": "sha256:" + "aa" * 32},
    )
    # Full re-validation (model_copy bypasses validators, which is exactly
    # the kind of bypass this contract must reject).
    with pytest.raises(ProtocolError):
        GuestMessageV1(
            **{**message.model_dump(), "payload_digest": "sha256:" + "bb" * 32}
        )


def test_oversized_payload_rejected():
    with pytest.raises(ProtocolError):
        build_guest_message(
            message_id="msg-big",
            attempt_id=ATTEMPT,
            sandbox_id=SANDBOX,
            sequence_number=1,
            message_type=GuestMessageType.ARTIFACT_UPLOAD_REQUESTED,
            sent_at=utc_now_ms(),
            payload={"blob": "x" * (MAX_PAYLOAD_BYTES + 1)},
        )


def test_oversized_frame_rejected():
    blob = "x" * (MAX_MESSAGE_BYTES + 1)
    with pytest.raises(ProtocolError):
        frame_message(
            _msg(1, payload={"blob": blob})
        )


def test_truncated_frame_rejected():
    with pytest.raises(ProtocolError):
        parse_frame(b"\x00\x00\x10\x00short")


def test_non_json_frame_rejected():
    import struct

    with pytest.raises(ProtocolError):
        parse_frame(struct.pack(">I", 4) + b"nope")


def test_guest_failure_and_heartbeat_are_valid_types():
    session = _session()
    session.receive(frame_message(_msg(1, GuestMessageType.GUEST_FAILURE_REPORTED, payload={"error_class": "oom"})))
    session.receive(frame_message(_msg(2, GuestMessageType.LIFECYCLE_HEARTBEAT)))
    assert session.messages_received == 2
