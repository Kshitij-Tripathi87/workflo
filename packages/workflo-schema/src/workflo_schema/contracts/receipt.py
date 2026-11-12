"""Receipt v5: validated payload inside a DSSE-style envelope (ADR-0018).

The payload cannot exist without the teardown verification record, the
evidence manifest digest, the finding summary digest, and the outcome —
so "sign now, validate later" is not representable. Signing itself lives
in the evidence/signing service; this module owns only the structures,
the canonical payload encoding, and binding checks.
"""

from __future__ import annotations

import base64
import binascii
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from workflo_schema.contracts.canonical import model_digest
from workflo_schema.contracts.common import (
    CanonicalTimestamp,
    DigestString,
    IdString,
    SCHEMA_VERSION,
)
from workflo_schema.contracts.constants import (
    DEFAULT_RECEIPT_LIMITATIONS,
    DSSE_PAYLOAD_TYPE,
    RECEIPT_VERSION_V5,
)
from workflo_schema.contracts.events import ProducerIdentityV1
from workflo_schema.contracts.outcomes import RunOutcomeV1, TrustVerificationStatus
from workflo_schema.contracts.runspec import ModelArtifactRefV1, SourceProvider

__all__ = [
    "TeardownCheckId",
    "TeardownCheckV1",
    "TeardownVerificationV1",
    "RuntimeType",
    "RuntimeIdentityV1",
    "SignerIdentityV1",
    "SourceProvenanceV1",
    "ReceiptV5Payload",
    "DsseSignatureV1",
    "DsseEnvelopeV1",
    "SignedReceiptV5",
    "encode_dsse_payload",
    "decode_dsse_payload",
    "check_receipt_binding",
    "default_limitations",
]


class TeardownCheckId(str, Enum):
    VMM_EXITED = "vmm_exited"
    VM_STOPPED = "vm_stopped"
    CGROUPS_REMOVED = "cgroups_removed"
    NETNS_REMOVED = "netns_removed"
    DISK_DESTROYED = "disk_destroyed"
    SOCKETS_CLOSED = "sockets_closed"
    CAPABILITIES_EXPIRED = "capabilities_expired"
    PROCESS_SCOPE_EMPTY = "process_scope_empty"


REQUIRED_TEARDOWN_CHECKS: frozenset[TeardownCheckId] = frozenset(TeardownCheckId)


class TeardownCheckV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    check_id: TeardownCheckId
    passed: bool
    detail: str | None = Field(default=None, max_length=500)


class TeardownVerificationV1(BaseModel):
    """The trusted host's independent teardown record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    verification_id: IdString
    outcome: TrustVerificationStatus
    verifier: ProducerIdentityV1
    checks: tuple[TeardownCheckV1, ...] = Field(min_length=8, max_length=8)
    observed_at: CanonicalTimestamp

    @model_validator(mode="after")
    def _outcome_rules(self) -> "TeardownVerificationV1":
        present = [check.check_id for check in self.checks]
        if len(set(present)) != len(present):
            raise ValueError("teardown checks must be unique")
        missing = REQUIRED_TEARDOWN_CHECKS - set(present)
        if missing:
            names = ", ".join(sorted(check.value for check in missing))
            raise ValueError(f"teardown verification missing checks: {names}")
        all_passed = all(check.passed for check in self.checks)
        if self.outcome is TrustVerificationStatus.VERIFIED_CLEAN and not all_passed:
            raise ValueError(
                "verified_clean requires every teardown check to pass"
            )
        if (
            self.outcome is not TrustVerificationStatus.VERIFIED_CLEAN
            and all_passed
        ):
            raise ValueError(
                "all checks passed; outcome must be verified_clean "
                "(a non-clean outcome with all checks passing is contradictory)"
            )
        return self

    def all_passed(self) -> bool:
        return all(check.passed for check in self.checks)


class RuntimeType(str, Enum):
    MICROVM = "microvm"
    DOCKER = "docker"
    NAMESPACES = "namespaces"


class RuntimeIdentityV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    runtime_type: RuntimeType
    runtime_image_digest: DigestString
    guest_kernel_digest: DigestString | None = None
    guest_rootfs_digest: DigestString | None = None


class SignerIdentityV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    signer_id: IdString
    key_id: IdString
    provider: str = Field(
        pattern=r"^(kms|hsm|file-dev)$",
        description="file-dev is explicitly a development-only provider",
    )
    algorithm: str = Field(default="ed25519", pattern=r"^ed25519$")
    public_key_fingerprint: DigestString = Field(
        description="sha256 of the raw subjectPublicKey bytes"
    )


class SourceProvenanceV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: SourceProvider
    url: str | None = Field(default=None, max_length=2048)
    ref: str = Field(min_length=1, max_length=255)
    commit: str = Field(pattern=r"^[0-9a-f]{7,64}$")
    snapshot_digest: DigestString


class ReceiptV5Payload(BaseModel):
    """Everything the receipt attests, bound into one canonical payload."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = SCHEMA_VERSION
    receipt_version: int = Field(default=RECEIPT_VERSION_V5, frozen=True)
    receipt_id: IdString

    organization_id: IdString
    project_id: IdString
    run_id: IdString
    attempt_id: IdString
    sandbox_id: IdString

    source: SourceProvenanceV1
    execution_policy_digest: DigestString
    runtime: RuntimeIdentityV1
    model_artifacts: tuple[ModelArtifactRefV1, ...] = ()

    execution_started_at: CanonicalTimestamp
    execution_completed_at: CanonicalTimestamp
    outcome: RunOutcomeV1

    finding_summary_digest: DigestString
    evidence_manifest_digest: DigestString
    evidence_ledger_root: DigestString
    evidence_ledger_checkpoint: int | None = Field(default=None, ge=0)
    evidence_chain_version: int = Field(ge=1)

    teardown_verification: TeardownVerificationV1
    limitations: tuple[str, ...] = Field(min_length=1)
    signer_identity: SignerIdentityV1
    issued_at: CanonicalTimestamp

    @model_validator(mode="after")
    def _version_literal(self) -> "ReceiptV5Payload":
        if self.receipt_version != RECEIPT_VERSION_V5:
            raise ValueError(
                f"receipt_version must be {RECEIPT_VERSION_V5} for this contract"
            )
        return self

    def payload_digest(self) -> str:
        """Canonical digest of the payload (the value a verifier re-derives)."""
        return model_digest(self)


class DsseSignatureV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    keyid: IdString
    sig: str = Field(pattern=r"^[A-Za-z0-9+/=]+$", max_length=1024)


class DsseEnvelopeV1(BaseModel):
    """DSSE-style envelope over the canonical receipt payload bytes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    payload_type: str = Field(default=DSSE_PAYLOAD_TYPE, pattern=r"^application/vnd\.workflo\.receipt\.v5\+json$")
    payload: str = Field(pattern=r"^[A-Za-z0-9+/=]+$", max_length=1_000_000)
    signatures: tuple[DsseSignatureV1, ...] = Field(min_length=1)


class SignedReceiptV5(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    envelope: DsseEnvelopeV1


def encode_dsse_payload(payload: ReceiptV5Payload) -> str:
    """Base64-encode the canonical payload bytes."""
    from workflo_schema.contracts.canonical import canonical_bytes

    return base64.b64encode(canonical_bytes(payload.model_dump(mode="json"))).decode(
        "ascii"
    )


def decode_dsse_payload(envelope: DsseEnvelopeV1) -> ReceiptV5Payload:
    """Decode and validate a receipt payload from an envelope."""
    try:
        raw = base64.b64decode(envelope.payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"envelope payload is not valid base64: {exc}") from exc
    return ReceiptV5Payload.model_validate_json(raw)


def check_receipt_binding(payload: ReceiptV5Payload, run_spec: object) -> list[str]:
    """Return binding mismatches between a receipt payload and a RunSpec.

    Empty list means every comparable field agrees. The caller decides
    which mismatches are fatal for its context.
    """
    mismatches: list[str] = []

    def compare(name: str, left: object, right: object) -> None:
        if left != right:
            mismatches.append(f"{name}: receipt={left!r} spec={right!r}")

    compare("organization_id", payload.organization_id, getattr(run_spec, "organization_id", None))
    compare("project_id", payload.project_id, getattr(run_spec, "project_id", None))
    compare("run_id", payload.run_id, getattr(run_spec, "run_id", None))
    compare("execution_policy_digest", payload.execution_policy_digest, getattr(run_spec, "policy_digest", None))

    source = getattr(run_spec, "source", None)
    if source is not None:
        compare("source.commit", payload.source.commit, getattr(source, "commit", None))
        spec_snapshot = getattr(source, "snapshot_digest", None)
        if spec_snapshot is not None:
            compare(
                "source.snapshot_digest",
                payload.source.snapshot_digest,
                spec_snapshot,
            )
    return mismatches


def default_limitations() -> tuple[str, ...]:
    """The frozen baseline limitations list for new receipts."""
    return DEFAULT_RECEIPT_LIMITATIONS
