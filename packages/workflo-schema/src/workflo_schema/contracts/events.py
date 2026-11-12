"""Canonical run event contract v1 (ADR-0020).

Guest events are observations. Only trusted-control producers may drive
lifecycle transitions. Payloads are strict, canonical-hashable, and
chain-of-thought free by construction.
"""

from __future__ import annotations

from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator

from workflo_schema.contracts.canonical import (
    CanonicalizationError,
    canonical_json,
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
    "EventType",
    "ProducerComponent",
    "TrustClass",
    "ProducerIdentityV1",
    "RunEventV1",
    "PRODUCER_TRUST_CLASS",
    "producer_trust_class",
    "can_drive_lifecycle",
    "build_event_payload_digest",
]


class EventType(str, Enum):
    RUN_CREATED = "run.created"
    RUN_ADMITTED = "run.admitted"
    RUN_REJECTED = "run.rejected"
    POLICY_VALIDATED = "policy.validated"
    WORKER_ALLOCATED = "worker.allocated"
    SANDBOX_PROVISIONING_STARTED = "sandbox.provisioning_started"
    SANDBOX_READY = "sandbox.ready"
    SANDBOX_PROVISIONING_FAILED = "sandbox.provisioning_failed"
    SOURCE_ACQUISITION_STARTED = "source.acquisition_started"
    SOURCE_ACQUISITION_COMPLETED = "source.acquisition_completed"
    SOURCE_ACQUISITION_FAILED = "source.acquisition_failed"
    ENVIRONMENT_PREPARATION_STARTED = "environment.preparation_started"
    TEST_STARTED = "test.started"
    TEST_COMPLETED = "test.completed"
    PROBE_STARTED = "probe.started"
    PROBE_COMPLETED = "probe.completed"
    APP_STARTED = "app.started"
    APP_READY = "app.ready"
    AGENT_ACTION_PROPOSED = "agent.action_proposed"
    AGENT_ACTION_VALIDATED = "agent.action_validated"
    AGENT_ACTION_DENIED = "agent.action_denied"
    AGENT_ACTION_EXECUTED = "agent.action_executed"
    AGENT_OBSERVATION = "agent.observation"
    FINDING_CANDIDATE = "finding.candidate"
    FINDING_VERIFIED = "finding.verified"
    EVALUATION_STARTED = "evaluation.started"
    EVALUATION_COMPLETED = "evaluation.completed"
    EVIDENCE_BUNDLE_RECEIVED = "evidence.bundle_received"
    EVIDENCE_BUNDLE_VALIDATED = "evidence.bundle_validated"
    EVIDENCE_BUNDLE_REJECTED = "evidence.bundle_rejected"
    SANDBOX_TEARDOWN_STARTED = "sandbox.teardown_started"
    SANDBOX_TEARDOWN_VERIFIED = "sandbox.teardown_verified"
    SANDBOX_TEARDOWN_FAILED = "sandbox.teardown_failed"
    RECEIPT_VALIDATED = "receipt.validated"
    RECEIPT_SIGNED = "receipt.signed"
    RECEIPT_SIGNING_FAILED = "receipt.signing_failed"
    RUN_CANCELLATION_REQUESTED = "run.cancellation_requested"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"


class ProducerComponent(str, Enum):
    CONTROL_PLANE = "control_plane"
    ORCHESTRATOR = "orchestrator"
    HOST_WORKER = "host_worker"
    GUEST_SUPERVISOR = "guest_supervisor"
    QA_RUNTIME = "qa_runtime"
    AGENT_RUNTIME = "agent_runtime"
    TOOL_GATEWAY = "tool_gateway"
    EVIDENCE_SERVICE = "evidence_service"
    SIGNER = "signer"
    JUDGE = "judge"
    USER = "user"


class TrustClass(str, Enum):
    TRUSTED_CONTROL = "trusted_control"
    TRUSTED_GUEST = "trusted_guest"
    USER = "user"


PRODUCER_TRUST_CLASS: Mapping[ProducerComponent, TrustClass] = MappingProxyType(
    {
        ProducerComponent.CONTROL_PLANE: TrustClass.TRUSTED_CONTROL,
        ProducerComponent.ORCHESTRATOR: TrustClass.TRUSTED_CONTROL,
        ProducerComponent.HOST_WORKER: TrustClass.TRUSTED_CONTROL,
        ProducerComponent.EVIDENCE_SERVICE: TrustClass.TRUSTED_CONTROL,
        ProducerComponent.SIGNER: TrustClass.TRUSTED_CONTROL,
        ProducerComponent.JUDGE: TrustClass.TRUSTED_CONTROL,
        ProducerComponent.GUEST_SUPERVISOR: TrustClass.TRUSTED_GUEST,
        ProducerComponent.QA_RUNTIME: TrustClass.TRUSTED_GUEST,
        ProducerComponent.AGENT_RUNTIME: TrustClass.TRUSTED_GUEST,
        ProducerComponent.TOOL_GATEWAY: TrustClass.TRUSTED_GUEST,
        ProducerComponent.USER: TrustClass.USER,
    }
)


def producer_trust_class(component: ProducerComponent) -> TrustClass:
    return PRODUCER_TRUST_CLASS[component]


def can_drive_lifecycle(producer: "ProducerIdentityV1") -> bool:
    """Only trusted-control producers may cause lifecycle transitions."""
    return producer_trust_class(producer.component) is TrustClass.TRUSTED_CONTROL


COGNITION_FORBIDDEN_KEYS: frozenset[str] = frozenset(
    {
        "thought",
        "thoughts",
        "reasoning",
        "internal",
        "chain",
        "cot",
        "chain_of_thought",
        "scratchpad",
        "hidden",
    }
)


def _reject_cognition_keys(value: Any, path: str = "payload") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str) and key.lower() in COGNITION_FORBIDDEN_KEYS:
                raise ValueError(
                    f"forbidden chain-of-thought field at {path}.{key}"
                )
            _reject_cognition_keys(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_cognition_keys(item, f"{path}[{index}]")


def build_event_payload_digest(payload: Mapping[str, Any]) -> str:
    """Digest a payload exactly as :class:`RunEventV1` expects."""
    return digest_of(dict(payload))


class ProducerIdentityV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    component: ProducerComponent
    role: str | None = Field(default=None, max_length=64)
    instance_id: IdString
    version: str = Field(min_length=1, max_length=64)


class RunEventV1(BaseModel):
    """One canonical event in an attempt's ordered stream."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = SCHEMA_VERSION
    event_id: IdString
    organization_id: IdString
    project_id: IdString
    run_id: IdString
    attempt_id: IdString
    sandbox_id: IdString | None = None

    sequence_number: int = Field(ge=1)
    event_type: EventType
    occurred_at: CanonicalTimestamp
    producer: ProducerIdentityV1
    correlation_id: IdString
    payload_digest: DigestString
    payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _payload_rules(self) -> "RunEventV1":
        _reject_cognition_keys(self.payload)
        try:
            canonical_json(self.payload)
        except CanonicalizationError as exc:
            raise ValueError(f"event payload is not canonicalizable: {exc}") from exc
        if not digest_matches(self.payload_digest, self.payload):
            raise ValueError(
                "payload_digest does not match the canonical digest of payload"
            )
        return self

    @classmethod
    def build(
        cls,
        *,
        event_id: str,
        organization_id: str,
        project_id: str,
        run_id: str,
        attempt_id: str,
        sequence_number: int,
        event_type: EventType,
        occurred_at: str,
        producer: ProducerIdentityV1,
        correlation_id: str,
        payload: Mapping[str, Any] | None = None,
        sandbox_id: str | None = None,
    ) -> "RunEventV1":
        """Construct an event with its payload digest computed."""
        body = dict(payload or {})
        return cls(
            event_id=event_id,
            organization_id=organization_id,
            project_id=project_id,
            run_id=run_id,
            attempt_id=attempt_id,
            sandbox_id=sandbox_id,
            sequence_number=sequence_number,
            event_type=event_type,
            occurred_at=occurred_at,
            producer=producer,
            correlation_id=correlation_id,
            payload_digest=build_event_payload_digest(body),
            payload=body,
        )
