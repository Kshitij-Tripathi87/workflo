"""Execution policy bundle v1 (ADR-0019).

Admission requires a validated, immutable bundle: exactly twelve
components, each versioned and digest-verified, plus a bundle digest that
binds them together.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from workflo_schema.contracts.canonical import (
    CanonicalizationError,
    canonical_json,
    digest_of,
    model_canonical_dump,
)
from workflo_schema.contracts.common import (
    CanonicalTimestamp,
    DigestString,
    IdString,
    SCHEMA_VERSION,
)
from workflo_schema.contracts.runspec import RunCreatorV1

__all__ = [
    "PolicyComponentId",
    "PolicyComponentV1",
    "ExecutionPolicyBundleV1",
]


class PolicyComponentId(str, Enum):
    SOURCE = "source"
    RUNTIME = "runtime"
    RESOURCE = "resource"
    COMMAND = "command"
    FILESYSTEM = "filesystem"
    NETWORK = "network"
    AGENT_CAPABILITY = "agent_capability"
    MODEL = "model"
    ARTIFACT = "artifact"
    EVIDENCE = "evidence"
    RETENTION = "retention"
    TEARDOWN = "teardown"


#: Every bundle must contain each component exactly once.
REQUIRED_POLICY_COMPONENTS: frozenset[PolicyComponentId] = frozenset(PolicyComponentId)


def _component_digest_body(component: "PolicyComponentV1") -> dict[str, Any]:
    return {
        "component": component.component.value,
        "version": component.version,
        "schema_version": component.schema_version,
        "authority": component.authority,
        "payload": component.payload,
    }


class PolicyComponentV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    component: PolicyComponentId
    version: str = Field(min_length=1, max_length=64)
    schema_version: str = SCHEMA_VERSION
    authority: str = Field(
        min_length=1,
        max_length=200,
        description="Who owns changes to this component (role/permission name)",
    )
    payload: dict[str, Any]
    digest: DigestString

    @model_validator(mode="after")
    def _payload_and_digest(self) -> "PolicyComponentV1":
        try:
            canonical_json(self.payload)
        except CanonicalizationError as exc:
            raise ValueError(f"policy payload is not canonicalizable: {exc}") from exc
        expected = digest_of(_component_digest_body(self))
        if self.digest != expected:
            raise ValueError(
                f"policy component digest mismatch for {self.component.value}: "
                f"stored {self.digest}, recomputed {expected}"
            )
        return self

    @classmethod
    def build(
        cls,
        *,
        component: PolicyComponentId,
        version: str,
        authority: str,
        payload: dict[str, Any],
    ) -> "PolicyComponentV1":
        """Construct a component with its digest computed, not asserted."""
        draft = {
            "component": component.value,
            "version": version,
            "schema_version": SCHEMA_VERSION,
            "authority": authority,
            "payload": payload,
        }
        return cls(digest=digest_of(draft), **draft)


class ExecutionPolicyBundleV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = SCHEMA_VERSION
    bundle_id: IdString
    organization_id: IdString
    version: str = Field(min_length=1, max_length=64)
    created_by: RunCreatorV1
    created_at: CanonicalTimestamp
    effective_from: CanonicalTimestamp | None = None
    components: tuple[PolicyComponentV1, ...] = Field(min_length=12, max_length=12)

    @model_validator(mode="after")
    def _complete_and_unique(self) -> "ExecutionPolicyBundleV1":
        present = [component.component for component in self.components]
        if len(set(present)) != len(present):
            raise ValueError("policy bundle contains duplicate components")
        missing = REQUIRED_POLICY_COMPONENTS - set(present)
        if missing:
            names = ", ".join(sorted(component.value for component in missing))
            raise ValueError(f"policy bundle missing components: {names}")
        return self

    def digest(self) -> str:
        """Bundle digest binding component identities and their digests."""
        body = [
            {
                "component": component.component.value,
                "version": component.version,
                "digest": component.digest,
            }
            for component in sorted(self.components, key=lambda c: c.component.value)
        ]
        return digest_of(body)

    def canonical_dump(self) -> Any:
        return model_canonical_dump(self)
