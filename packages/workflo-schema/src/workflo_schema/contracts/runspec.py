"""Frozen RunSpec v1 (ADR-0017, brief appendix "RunSpec minimum").

The spec is immutable after admission. Anything that must change later
(stage progress, outcomes) is not part of this object; it is recorded in
events, attempts, and the outcome record.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from workflo_schema.contracts.common import (
    CanonicalTimestamp,
    DigestString,
    IdString,
    SCHEMA_VERSION,
)

__all__ = [
    "SourceProvider",
    "SourceSpecV1",
    "CapabilityId",
    "NetworkProtocol",
    "AllowedDestinationV1",
    "NetworkPolicySpecV1",
    "RetentionClass",
    "RetentionSpecV1",
    "ModelArtifactRole",
    "ModelArtifactRefV1",
    "RunCreatorV1",
    "RunSpecV1",
]


class SourceProvider(str, Enum):
    GITHUB = "github"
    GITLAB = "gitlab"
    BITBUCKET = "bitbucket"
    GENERIC_GIT = "generic_git"
    UPLOAD_ARCHIVE = "upload_archive"


class SourceSpecV1(BaseModel):
    """Exact source identity. The snapshot digest is bound after acquisition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: SourceProvider
    url: str | None = Field(default=None, max_length=2048)
    ref: str = Field(min_length=1, max_length=255)
    commit: str = Field(
        pattern=r"^[0-9a-f]{7,64}$",
        description="Exact revision (lowercase hex); never a moving ref",
    )
    snapshot_digest: DigestString | None = Field(
        default=None,
        description="Populated once the guest has materialized the snapshot",
    )

    @field_validator("url")
    @classmethod
    def _url_allowed_schemes(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not value.startswith(("https://", "ssh://", "git://")):
            raise ValueError("source url must use https://, ssh://, or git://")
        return value


class CapabilityId(str, Enum):
    SOURCE_ACQUIRE = "source.acquire"
    TESTS_EXECUTE = "tests.execute"
    PROBES_EXECUTE = "probes.execute"
    BROWSER_PROBES_EXECUTE = "browser_probes.execute"
    AGENT_EXPLORE = "agent.explore"
    EVIDENCE_SUBMIT = "evidence.submit"


class NetworkProtocol(str, Enum):
    TCP = "tcp"
    UDP = "udp"


class AllowedDestinationV1(BaseModel):
    """One explicitly allowed egress destination (default-deny otherwise)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    host: str = Field(min_length=1, max_length=253)
    port: int = Field(ge=1, le=65535)
    protocol: NetworkProtocol = NetworkProtocol.TCP
    purpose: str | None = Field(default=None, max_length=200)


class NetworkPolicySpecV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    default: str = Field(default="deny", pattern=r"^deny$")
    allowed_destinations: tuple[AllowedDestinationV1, ...] = ()
    max_bandwidth_kbps: int | None = Field(default=None, ge=1)


class RetentionClass(str, Enum):
    EPHEMERAL = "ephemeral"
    RUN_LIFETIME = "run_lifetime"
    DAYS_30 = "days_30"
    DAYS_90 = "days_90"
    DAYS_365 = "days_365"
    CONTRACTUAL = "contractual"


class RetentionSpecV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    retention_policy_id: IdString
    source_snapshot: RetentionClass = RetentionClass.EPHEMERAL
    logs: RetentionClass = RetentionClass.DAYS_30
    artifacts: RetentionClass = RetentionClass.DAYS_90
    receipts: RetentionClass = RetentionClass.DAYS_365


class ModelArtifactRole(str, Enum):
    BASE = "base"
    TEST_GEN = "test-gen"
    REASONING = "reasoning"
    REPORTING = "reporting"
    OTHER = "other"


class ModelArtifactRefV1(BaseModel):
    """Identity of one approved model artifact; digests are verified pre-load."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_id: IdString
    role: ModelArtifactRole
    digest: DigestString
    size_bytes: int | None = Field(default=None, ge=0)


class RunCreatorV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: IdString
    organization_id: IdString


class RunSpecV1(BaseModel):
    """The canonical admitted-run contract. Immutable after admission."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = SCHEMA_VERSION
    organization_id: IdString
    project_id: IdString
    run_id: IdString
    idempotency_key: str = Field(min_length=8, max_length=128)

    source: SourceSpecV1
    profile_id: IdString
    policy_digest: DigestString
    runtime_image_digest: DigestString
    model_artifacts: tuple[ModelArtifactRefV1, ...] = ()
    resource_profile: IdString
    network_policy: NetworkPolicySpecV1 = NetworkPolicySpecV1()
    capabilities: tuple[CapabilityId, ...] = Field(min_length=1)
    retention: RetentionSpecV1

    created_by: RunCreatorV1
    created_at: CanonicalTimestamp

    @field_validator("capabilities")
    @classmethod
    def _unique_capabilities(
        cls, value: tuple[CapabilityId, ...]
    ) -> tuple[CapabilityId, ...]:
        if len(set(value)) != len(value):
            raise ValueError("capabilities must be unique")
        return value

    @field_validator("model_artifacts")
    @classmethod
    def _unique_artifacts(
        cls, value: tuple[ModelArtifactRefV1, ...]
    ) -> tuple[ModelArtifactRefV1, ...]:
        ids = [artifact.artifact_id for artifact in value]
        if len(set(ids)) != len(ids):
            raise ValueError("model artifact ids must be unique")
        return value
