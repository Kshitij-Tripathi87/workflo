"""Sandbox execution assignment v1 (ADR-0022, brief §3.2).

A versioned, authenticated, immutable assignment is the ONLY way a run
reaches a worker. The host never receives arbitrary user-provided VM
configuration. The assignment carries its own digest so both the control
plane and the worker can verify it was not altered in transit.
"""

from __future__ import annotations

import hmac
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from workflo_schema.contracts.canonical import digest_of
from workflo_schema.contracts.common import (
    CanonicalTimestamp,
    DigestString,
    IdString,
    SCHEMA_VERSION,
)
from workflo_schema.contracts.runspec import (
    CapabilityId,
    NetworkPolicySpecV1,
)

__all__ = [
    "ResourceLimitsV1",
    "GuestImageV1",
    "SandboxAssignmentV1",
    "AssignmentError",
]


class AssignmentError(Exception):
    """The assignment is structurally invalid or fails its binding.

    Deliberately not a ValueError: pydantic wraps ValueError from
    validators into ValidationError, and assignment violations must
    surface as this explicit type.
    """


class ResourceLimitsV1(BaseModel):
    """Enforceable per-run ceilings (brief §3.6)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    vcpus: int = Field(ge=1, le=64)
    memory_mib: int = Field(ge=256, le=262_144)
    disk_mib: int = Field(ge=512, le=1_048_576)
    wall_clock_seconds: int = Field(ge=10, le=86_400)
    max_processes: int = Field(default=256, ge=8, le=4096)
    max_artifact_bytes: int = Field(default=1_073_741_824, ge=0)
    max_log_bytes: int = Field(default=104_857_600, ge=0)


class GuestImageV1(BaseModel):
    """Digest-pinned guest artifacts; the worker refuses unpinned images."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kernel_path: str = Field(min_length=1, max_length=1024)
    kernel_sha256: DigestString
    rootfs_path: str = Field(min_length=1, max_length=1024)
    rootfs_sha256: DigestString


class SandboxAssignmentV1(BaseModel):
    """One run attempt's complete, immutable execution assignment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = SCHEMA_VERSION
    assignment_id: IdString
    run_id: IdString
    attempt_id: IdString
    sandbox_id: IdString

    policy_digest: DigestString
    runtime_image_digest: DigestString
    guest_image: GuestImageV1

    resource_limits: ResourceLimitsV1
    network_policy: NetworkPolicySpecV1
    capabilities: tuple[CapabilityId, ...] = Field(min_length=1)

    issued_by: IdString
    issued_at: CanonicalTimestamp
    # Authenticity: produced by the trusted side. The worker refuses to
    # provision from an unsigned assignment in production (manager flag).
    signature: str | None = Field(default=None, max_length=1024)

    @model_validator(mode="after")
    def _capabilities_unique(self) -> "SandboxAssignmentV1":
        if len(set(self.capabilities)) != len(self.capabilities):
            raise AssignmentError("capabilities must be unique")
        return self

    def digest(self) -> str:
        """Canonical digest binding every assignment field except the
        signature itself (the signature covers this digest)."""
        body = self.model_dump(mode="json")
        body.pop("signature", None)
        return digest_of(_plain(body))

    def verify_signature(
        self, verify: Callable[[str, bytes], bool], public_key_id: str = ""
    ) -> bool:
        """Verify the assignment signature over its canonical digest bytes.

        ``verify`` is injected by the trusted side (key directory / KMS);
        the worker never holds admission signing keys.
        """
        if not self.signature:
            return False
        message = self.digest().encode("utf-8")
        return bool(verify(public_key_id, message))


def _plain(value: Any) -> Any:
    """Normalize tuples -> lists so model_dump output is JSON-stable."""
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    return value


def constant_time_equals(left: str, right: str) -> bool:
    """Digest comparison that does not leak timing."""
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))
