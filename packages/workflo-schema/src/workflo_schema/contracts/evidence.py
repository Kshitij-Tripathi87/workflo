"""Canonical evidence contracts v1 (ADR-0020).

Every artifact is scoped to exactly one attempt; the manifest validator
rejects cross-run and cross-tenant references structurally. Corrections
supersede; finalized evidence is never mutated in place.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from workflo_schema.contracts.canonical import model_digest
from workflo_schema.contracts.common import (
    CanonicalTimestamp,
    DigestString,
    IdString,
    MEDIA_TYPE_PATTERN,
    SCHEMA_VERSION,
)
from workflo_schema.contracts.events import ProducerIdentityV1

__all__ = [
    "EvidenceArtifactType",
    "EvidenceClassification",
    "ValidationState",
    "EvidenceArtifactV1",
    "EvidenceManifestV1",
    "EvidenceScopeError",
]


class EvidenceArtifactType(str, Enum):
    LOG = "log"
    TEST_OUTPUT = "test_output"
    PROBE_OUTPUT = "probe_output"
    SCREENSHOT = "screenshot"
    TRACE = "trace"
    AGENT_ACTION_LEDGER = "agent_action_ledger"
    EVENT_LEDGER = "event_ledger"
    COVERAGE_REPORT = "coverage_report"
    BUILD_OUTPUT = "build_output"
    DEPENDENCY_MANIFEST = "dependency_manifest"
    MODEL_OUTPUT = "model_output"
    TEARDOWN_EVIDENCE = "teardown_evidence"
    MANIFEST = "manifest"
    OTHER = "other"


class EvidenceClassification(str, Enum):
    EXECUTION_EVIDENCE = "execution_evidence"
    AGENT_EVIDENCE = "agent_evidence"
    INFRASTRUCTURE_EVIDENCE = "infrastructure_evidence"
    ATTESTATION = "attestation"
    DERIVED_REPORT = "derived_report"


class ValidationState(str, Enum):
    RECEIVED = "received"
    VALIDATED = "validated"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class EvidenceScopeError(Exception):
    """A manifest or artifact crosses run/attempt/tenant scope.

    Deliberately not a ValueError subclass: pydantic wraps ValueError from
    validators into ValidationError, and scope violations must surface as
    this explicit type so every consumer treats them as security rejections.
    """


class EvidenceArtifactV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = SCHEMA_VERSION
    artifact_id: IdString
    organization_id: IdString
    project_id: IdString
    run_id: IdString
    attempt_id: IdString
    sandbox_id: IdString | None = None

    artifact_type: EvidenceArtifactType
    media_type: str = Field(pattern=MEDIA_TYPE_PATTERN, max_length=129)
    size_bytes: int = Field(ge=0)
    sha256: DigestString

    producer: ProducerIdentityV1
    stage: str = Field(
        min_length=1,
        max_length=64,
        description="Lifecycle stage / action that produced the artifact",
    )
    source_revision: str = Field(min_length=7, max_length=64)
    snapshot_digest: DigestString | None = None
    policy_digest: DigestString
    runtime_image_digest: DigestString | None = None

    classification: EvidenceClassification
    retention_policy_id: IdString
    validation_state: ValidationState
    object_ref: str = Field(
        min_length=1,
        max_length=512,
        description="Opaque immutable object-storage reference",
    )
    created_at: CanonicalTimestamp


class EvidenceManifestV1(BaseModel):
    """The trusted-side manifest for exactly one attempt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = SCHEMA_VERSION
    manifest_id: IdString
    organization_id: IdString
    project_id: IdString
    run_id: IdString
    attempt_id: IdString
    created_at: CanonicalTimestamp

    artifacts: tuple[EvidenceArtifactV1, ...] = ()
    ledger_chain_version: int = Field(ge=1)
    ledger_root: DigestString
    ledger_checkpoint: int | None = Field(default=None, ge=0)
    events_count: int = Field(ge=0)

    @model_validator(mode="after")
    def _scope_and_uniqueness(self) -> "EvidenceManifestV1":
        seen: set[str] = set()
        for artifact in self.artifacts:
            if artifact.artifact_id in seen:
                raise EvidenceScopeError(
                    f"duplicate artifact id {artifact.artifact_id}"
                )
            seen.add(artifact.artifact_id)
            if (
                artifact.organization_id != self.organization_id
                or artifact.project_id != self.project_id
                or artifact.run_id != self.run_id
                or artifact.attempt_id != self.attempt_id
            ):
                raise EvidenceScopeError(
                    "artifact "
                    f"{artifact.artifact_id} is scoped to "
                    f"{artifact.organization_id}/{artifact.project_id}/"
                    f"{artifact.run_id}/{artifact.attempt_id}, not "
                    f"{self.organization_id}/{self.project_id}/"
                    f"{self.run_id}/{self.attempt_id}"
                )
        return self

    def digest(self) -> str:
        """Digest binding the validated manifest (used by receipt v5)."""
        return model_digest(self)
