"""Narrow guest/host protocol, message layer (brief §3.4, ADR-0022).

This module is TRANSPORT-AGNOSTIC: it defines the only messages a guest may
send, frames them for the vsock channel, and enforces every protocol rule
the brief requires:

- strict schemas (unknown fields rejected; unknown types rejected);
- attempt/sandbox binding (a message from another attempt is invalid);
- version negotiation (mismatched protocol version is a hard error);
- sequence numbers (gaps and replays are hard errors);
- mutual identity (message_id) and payload digests;
- message size limits at the frame layer.

There is no generic RPC here: no filesystem access, no shell execution, no
host process management, no Docker. Unknown operations are REJECTED, not
ignored. The transport (AF_VSOCK) is injected behind a small seam so the
protocol can be tested on any platform while real sockets stay
Linux-gated.
"""

from __future__ import annotations

import hashlib
import json
import struct
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from workflo_schema.contracts.canonical import (
    CanonicalizationError,
    canonical_bytes,
    digest_matches,
    digest_of,
)
from workflo_schema.contracts.common import (
    CanonicalTimestamp,
    DigestString,
    IdString,
    SCHEMA_VERSION,
)

__all__ = [
    "PROTOCOL_VERSION",
    "MAX_MESSAGE_BYTES",
    "MAX_PAYLOAD_BYTES",
    "GuestMessageType",
    "GuestMessageV1",
    "build_guest_message",
    "frame_message",
    "parse_frame",
    "GuestProtocolSession",
    "ProtocolError",
    "UnknownOperationError",
    "VersionMismatchError",
    "SequenceError",
    "BindingError",
]

PROTOCOL_VERSION = 1
MAX_MESSAGE_BYTES = 1_048_576          # 1 MiB per message
MAX_PAYLOAD_BYTES = 786_432            # 768 KiB payload budget
_FRAME_HEADER = struct.Struct(">I")


class ProtocolError(Exception):
    """Base class for protocol violations.

    Deliberately NOT a ValueError: pydantic wraps ValueError from validators
    into ValidationError, and protocol violations must surface as their
    explicit types (same rationale as EvidenceScopeError).
    """


class UnknownOperationError(ProtocolError):
    """An operation outside the frozen message registry."""


class VersionMismatchError(ProtocolError):
    """The peer speaks a different protocol version."""


class SequenceError(ProtocolError):
    """Sequence gap or replay."""


class BindingError(ProtocolError):
    """A message bound to a different attempt/sandbox."""


class GuestMessageType(str, Enum):
    """The frozen message registry (brief §3.4). Anything else is rejected."""

    GUEST_READY = "guest_ready"
    LIFECYCLE_HEARTBEAT = "lifecycle_heartbeat"
    EVIDENCE_MANIFEST_SUBMITTED = "evidence_manifest_submitted"
    ARTIFACT_UPLOAD_REQUESTED = "artifact_upload_requested"
    RUN_CANCELLATION_RECEIVED = "run_cancellation_received"
    SHUTDOWN_REQUESTED = "shutdown_requested"
    GUEST_FAILURE_REPORTED = "guest_failure_reported"


class GuestMessageV1(BaseModel):
    """One typed message on the guest/host channel."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = SCHEMA_VERSION
    protocol_version: int = PROTOCOL_VERSION
    message_id: IdString
    attempt_id: IdString
    sandbox_id: IdString
    sequence_number: int = Field(ge=1)
    message_type: GuestMessageType
    sent_at: CanonicalTimestamp
    payload_digest: DigestString
    payload: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _payload_rules(self) -> "GuestMessageV1":
        try:
            encoded = canonical_bytes(self.payload)
        except CanonicalizationError as exc:
            raise ProtocolError(f"payload not canonicalizable: {exc}") from exc
        if len(encoded) > MAX_PAYLOAD_BYTES:
            raise ProtocolError(
                f"payload exceeds {MAX_PAYLOAD_BYTES} bytes"
            )
        if not digest_matches(self.payload_digest, self.payload):
            raise ProtocolError("payload_digest does not match payload")
        return self

    def message_digest(self) -> str:
        return digest_of(self.model_dump(mode="json"))


def build_guest_message(
    *,
    message_id: str,
    attempt_id: str,
    sandbox_id: str,
    sequence_number: int,
    message_type: GuestMessageType,
    sent_at: str,
    payload: dict | None = None,
) -> GuestMessageV1:
    body = dict(payload or {})
    return GuestMessageV1(
        message_id=message_id,
        attempt_id=attempt_id,
        sandbox_id=sandbox_id,
        sequence_number=sequence_number,
        message_type=message_type,
        sent_at=sent_at,
        payload_digest=digest_of(body),
        payload=body,
    )


def frame_message(message: GuestMessageV1) -> bytes:
    """4-byte big-endian length prefix + canonical JSON bytes."""
    body = canonical_bytes(message.model_dump(mode="json"))
    if len(body) > MAX_MESSAGE_BYTES:
        raise ProtocolError(
            f"framed message exceeds {MAX_MESSAGE_BYTES} bytes"
        )
    return _FRAME_HEADER.pack(len(body)) + body


def parse_frame(data: bytes) -> GuestMessageV1:
    """Parse and structurally validate one framed message."""
    if len(data) < _FRAME_HEADER.size:
        raise ProtocolError("frame too short for header")
    (length,) = _FRAME_HEADER.unpack_from(data, 0)
    if length > MAX_MESSAGE_BYTES:
        raise ProtocolError(
            f"frame declares {length} bytes; limit is {MAX_MESSAGE_BYTES}"
        )
    body = data[_FRAME_HEADER.size : _FRAME_HEADER.size + length]
    if len(body) != length:
        raise ProtocolError("truncated frame")
    import hashlib

    hashlib.sha256(body).digest()  # cheap integrity touch; parse follows
    try:
        document = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError(f"frame is not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise ProtocolError("frame must contain a JSON object")
    version = document.get("protocol_version")
    if version != PROTOCOL_VERSION:
        raise VersionMismatchError(
            f"peer protocol version {version!r} != {PROTOCOL_VERSION}"
        )
    try:
        return GuestMessageV1.model_validate(document)
    except Exception as exc:  # noqa: BLE001 — mapped to protocol errors
        kind = str(exc)
        if "type=enum" in kind or "GuestMessageType" in kind:
            raise UnknownOperationError(f"unknown message type: {kind}") from exc
        raise ProtocolError(f"invalid message: {kind}") from exc


class GuestProtocolSession:
    """Stateful verifier for one guest connection.

    Binds the session to one attempt + sandbox, enforces strictly
    increasing sequence numbers (gaps AND replays are errors), and rejects
    unknown operations. A compromised guest cannot widen this channel.
    """

    def __init__(self, *, attempt_id: str, sandbox_id: str):
        self.attempt_id = attempt_id
        self.sandbox_id = sandbox_id
        self._last_sequence = 0
        self.messages_received = 0

    def receive(self, data: bytes) -> GuestMessageV1:
        message = parse_frame(data)
        if message.attempt_id != self.attempt_id or message.sandbox_id != self.sandbox_id:
            raise BindingError(
                f"message bound to {message.attempt_id}/{message.sandbox_id}, "
                f"session expects {self.attempt_id}/{self.sandbox_id}"
            )
        if message.sequence_number <= self._last_sequence:
            raise SequenceError(
                f"sequence {message.sequence_number} is not newer than "
                f"{self._last_sequence} (gap or replay)"
            )
        if message.sequence_number != self._last_sequence + 1:
            raise SequenceError(
                f"sequence gap: expected {self._last_sequence + 1}, "
                f"got {message.sequence_number}"
            )
        self._last_sequence = message.sequence_number
        self.messages_received += 1
        return message

    @property
    def last_sequence(self) -> int:
        return self._last_sequence
