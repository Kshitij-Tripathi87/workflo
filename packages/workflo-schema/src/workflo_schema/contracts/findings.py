"""Canonical finding contract v1 (ADR-0020).

Four finding categories plus a scope record. A model can produce
candidates; only deterministic verification (the Judge component) can
produce a verified failure, and only with evidence references.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from workflo_schema.contracts.common import (
    CanonicalTimestamp,
    DigestString,
    IdString,
    SCHEMA_VERSION,
)
from workflo_schema.contracts.events import ProducerComponent

__all__ = [
    "FindingCategory",
    "Severity",
    "DetectorIdentityV1",
    "ModelProvenanceV1",
    "VerificationStampV1",
    "FindingV1",
]


class FindingCategory(str, Enum):
    VERIFIED_FAILURE = "verified_failure"
    CANDIDATE = "candidate"
    INCONCLUSIVE = "inconclusive"
    INFRASTRUCTURE_FAILURE = "infrastructure_failure"
    NOT_TESTED = "not_tested"


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DetectorIdentityV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    component: ProducerComponent
    version: str = Field(min_length=1, max_length=64)
    ruleset_id: str | None = Field(default=None, max_length=128)


class ModelProvenanceV1(BaseModel):
    """Identity of the model involvement, for traceability only."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: IdString
    model_version: str = Field(min_length=1, max_length=64)
    model_digest: DigestString
    adapter_digests: tuple[DigestString, ...] = ()
    runtime_version: str = Field(min_length=1, max_length=64)
    prompt_schema_version: str = Field(min_length=1, max_length=64)


class VerificationStampV1(BaseModel):
    """The deterministic verification that promoted a candidate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    verifier: DetectorIdentityV1
    criteria_id: str = Field(min_length=1, max_length=128)
    procedure: str = Field(min_length=1, max_length=1000)
    verified_at: CanonicalTimestamp

    @model_validator(mode="after")
    def _deterministic_only(self) -> "VerificationStampV1":
        if self.verifier.component is not ProducerComponent.JUDGE:
            raise ValueError(
                "only the deterministic Judge component may stamp verification "
                "(model output never verifies a finding)"
            )
        if not self.verifier.ruleset_id:
            raise ValueError("verification requires a versioned ruleset_id")
        return self


class FindingV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = SCHEMA_VERSION
    finding_id: IdString
    organization_id: IdString
    project_id: IdString
    run_id: IdString
    attempt_id: IdString
    source_revision: str = Field(min_length=7, max_length=64)
    snapshot_digest: DigestString | None = None

    title: str = Field(min_length=1, max_length=500)
    category: FindingCategory
    severity: Severity
    expected_behavior: str = Field(min_length=1, max_length=2000)
    observed_behavior: str = Field(min_length=1, max_length=2000)
    reproduction_reference: str | None = Field(default=None, max_length=500)
    evidence_refs: tuple[IdString, ...] = ()
    detector: DetectorIdentityV1
    model_provenance: ModelProvenanceV1 | None = None
    uncertainty: str | None = Field(default=None, max_length=500)
    verified_by: VerificationStampV1 | None = None
    created_at: CanonicalTimestamp

    @model_validator(mode="after")
    def _category_rules(self) -> "FindingV1":
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("evidence_refs must be unique")
        if self.category is FindingCategory.VERIFIED_FAILURE:
            if not self.evidence_refs:
                raise ValueError(
                    "verified_failure requires at least one evidence reference"
                )
            if self.verified_by is None:
                raise ValueError(
                    "verified_failure requires a deterministic verification stamp"
                )
        else:
            if self.verified_by is not None:
                raise ValueError(
                    f"category={self.category.value} cannot carry a "
                    "verification stamp"
                )
        if (
            self.category is FindingCategory.INFRASTRUCTURE_FAILURE
            and self.severity in (Severity.HIGH, Severity.CRITICAL)
        ):
            # Infrastructure failures are never product defects; severity
            # beyond medium would let them read as one.
            raise ValueError(
                "infrastructure_failure severity is capped at medium "
                "(it is not a product defect)"
            )
        return self
