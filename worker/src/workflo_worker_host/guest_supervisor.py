"""Workflo guest supervisor — runs INSIDE the microVM (brief §2.4, §3).

The guest side of the narrow protocol. Responsibilities, deliberately few:

- verify its own execution identity (a host-delivered capability bound to
  the attempt + sandbox) before announcing readiness;
- send GUEST_READY as the FIRST message — no project work starts before
  the host has verified the supervisor (brief §3.1);
- heartbeat while work runs;
- honour cancellation and shutdown: stop NEW guest actions immediately and
  record the request (cancellation is a request, not proof — brief §5);
- report guest failures honestly;
- build evidence manifests with digests from the frozen contract.

The supervisor NEVER touches the host: no host filesystem, no host shell,
no Docker. Its entire world is the transport seam (vsock in production)
and the workspace the host provisioned inside the VM. Model/tool policies
arrive through the admitted assignment — the guest cannot widen them.
"""

from __future__ import annotations

import enum
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from workflo_schema.contracts.canonical import digest_of
from workflo_schema.contracts.common import (
    CanonicalTimestamp,
    DigestString,
    IdString,
    SCHEMA_VERSION,
    utc_now_ms,
)
from workflo_worker_host.protocol import (
    GuestMessageType,
    ProtocolError,
    build_guest_message,
    frame_message,
)

__all__ = [
    "GuestCapabilityV1",
    "GuestSupervisor",
    "SupervisorState",
    "GuestIdentityError",
]


class GuestIdentityError(RuntimeError):
    """The capability does not bind this guest to the attempt; refuse."""


class GuestCapabilityV1(BaseModel):
    """The one-time run capability the host delivers into the guest.

    Narrowly scoped, attempt-bound, expiring. Possession of this file is
    what lets a supervisor announce itself; anything else is unidentified.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = SCHEMA_VERSION
    capability_id: IdString
    attempt_id: IdString
    sandbox_id: IdString
    policy_digest: DigestString
    allowed_operations: tuple[str, ...] = Field(min_length=1)
    issued_at: CanonicalTimestamp
    expires_at: CanonicalTimestamp

    @model_validator(mode="after")
    def _expiry(self) -> "GuestCapabilityV1":
        if self.expires_at <= self.issued_at:
            raise GuestIdentityError("capability expires before it is issued")
        return self

    def digest(self) -> str:
        return digest_of(self.model_dump(mode="json"))


class SupervisorState(str, enum.Enum):
    BOOTING = "BOOTING"
    READY = "READY"
    WORKING = "WORKING"
    CANCELLATION_RECEIVED = "CANCELLATION_RECEIVED"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


class GuestSupervisor:
    """Lifecycle controller inside the guest. Transport is injected."""

    def __init__(
        self,
        *,
        capability: GuestCapabilityV1,
        send_frame: Callable,
        supervisor_instance_id: str = "guest-supervisor-1",
        supervisor_version: str = "0.1.0",
    ):
        self._capability = capability
        self._send = send_frame
        self._instance = supervisor_instance_id
        self._version = supervisor_version
        self.state = SupervisorState.BOOTING
        self._sequence = 0
        self.cancellation_received_at: str | None = None
        self.failure_reported: dict | None = None
        self.evidence_manifests: list = []

    # -- identity ---------------------------------------------------------

    def verify_identity(self, attempt_id: str, sandbox_id: str) -> None:
        """Refuse to run under a mismatched identity. Fail closed."""
        if self._capability.attempt_id != attempt_id or (
            self._capability.sandbox_id != sandbox_id
        ):
            raise GuestIdentityError(
                "guest capability does not bind this attempt/sandbox; "
                "refusing to announce readiness"
            )
        if utc_now_ms() > self._capability.expires_at:
            raise GuestIdentityError("guest capability has expired")

    # -- messaging --------------------------------------------------------

    def _emit(self, message_type: GuestMessageType, payload: dict | None = None) -> dict:
        self._sequence += 1
        message = build_guest_message(
            message_id=f"guest-{self._sequence:08d}",
            attempt_id=self._capability.attempt_id,
            sandbox_id=self._capability.sandbox_id,
            sequence_number=self._sequence,
            message_type=message_type,
            sent_at=utc_now_ms(),
            payload=payload or {},
        )
        self._send(frame_message(message))
        return message.model_dump(mode="json")

    def announce_ready(self) -> dict:
        """FIRST message. Identity must already be verified."""
        if self.state is not SupervisorState.BOOTING:
            raise ProtocolError("guest_ready may only be sent while BOOTING")
        message = self._emit(
            GuestMessageType.GUEST_READY,
            {
                "supervisor_version": self._version,
                "capability_digest": self._capability.digest(),
                "policy_digest": self._capability.policy_digest,
            },
        )
        self.state = SupervisorState.READY
        return message

    def heartbeat(self, detail: dict | None = None) -> dict:
        return self._emit(
            GuestMessageType.LIFECYCLE_HEARTBEAT, detail or {"state": self.state.value}
        )

    # -- inbound (host -> guest) ------------------------------------------

    def receive_host_message(self, frame: bytes) -> str:
        """Process one inbound host message. Unknown operations raise —
        the guest never widens its own authority."""
        from workflo_worker_host.protocol import parse_frame

        message = parse_frame(frame)
        if message.message_type is GuestMessageType.SHUTDOWN_REQUESTED:
            self.state = SupervisorState.STOPPING
            return "shutdown_requested"
        if message.message_type is GuestMessageType.RUN_CANCELLATION_RECEIVED:
            self.state = SupervisorState.CANCELLATION_RECEIVED
            self.cancellation_received_at = utc_now_ms()
            # Stop new guest actions immediately; the record is honest.
            return "cancellation_recorded"
        raise ProtocolError(
            f"guest cannot accept {message.message_type.value} from the host"
        )

    # -- failure + evidence -----------------------------------------------

    def report_failure(self, error_class: str, detail: str) -> dict:
        self.failure_reported = {"error_class": error_class, "detail": detail[:500]}
        message = self._emit(
            GuestMessageType.GUEST_FAILURE_REPORTED, dict(self.failure_reported)
        )
        self.state = SupervisorState.FAILED
        return message

    def build_evidence_manifest(self, artifacts: list) -> dict:
        """A bounded manifest of digests — never raw source or prompts."""
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "attempt_id": self._capability.attempt_id,
            "sandbox_id": self._capability.sandbox_id,
            "capability_digest": self._capability.digest(),
            "policy_digest": self._capability.policy_digest,
            "artifacts": artifacts,
            "built_at": utc_now_ms(),
        }
        entry = {
            "manifest": manifest,
            "manifest_digest": digest_of(manifest),
        }
        self.evidence_manifests.append(entry)
        self._emit(
            GuestMessageType.EVIDENCE_MANIFEST_SUBMITTED,
            {"manifest_digest": entry["manifest_digest"]},
        )
        return entry
