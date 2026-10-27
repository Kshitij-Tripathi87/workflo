"""Workflo crew contracts (S02).

Typed handoffs between the product agents (Analyst, Explorer, Judge,
Reporter) and the deterministic services (Orchestrator, ToolGateway,
Evidence ledger). Rules from docs/contracts.md:

- pydantic v2, ``extra="forbid"`` — a handoff may not carry undeclared data.
- every model carries ``schema_version``.
- invariants are enforced by validators, not by convention:
    * a Confirmed Finding needs >= 2 repro evidence refs and 1 control ref;
    * a ReportDraft may only cite evidence ids that exist on its Finding;
    * a ModelCallRecord never stores prompt or response bodies;
    * canary results are tri-state: blocked | leaked | not_run.
- StageResult cannot claim ok=True while carrying a failure stage
  (fail-closed mirror of the run contract).

This package must never import from crew or sandbox packages.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Backend = Literal["docker", "namespaces"]
PrivacyMode = Literal["local-only", "hybrid", "observation-only"]
CanaryResult = Literal["blocked", "leaked", "not_run"]

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
NonEmpty = Annotated[str, Field(min_length=1)]
ReqId = Annotated[str, Field(pattern=r"^REQ-[0-9]{3,}$")]
Port = Annotated[int, Field(ge=1, le=65535)]


class WorkfloContract(BaseModel):
    """Base for every crew contract: closed world + explicit schema version."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1)


# ---------------------------------------------------------------------------
# Run lifecycle
# ---------------------------------------------------------------------------


class RunInput(WorkfloContract):
    """Everything a run needs before the sandbox exists."""

    run_id: NonEmpty
    repo_ref: NonEmpty
    commit: NonEmpty
    snapshot_sha256: Sha256
    backend: Backend
    privacy_mode: PrivacyMode
    config: dict[str, Any]
    requirements_path: str | None = None


class SandboxHandle(WorkfloContract):
    """What a sealed sandbox looks like once it is up."""

    run_id: NonEmpty
    backend: Backend
    app_url: Annotated[str, Field(pattern=r"^https?://")]
    image_digest: str | None = None
    network_profile: NonEmpty
    canary_result: CanaryResult
    started_at: datetime


class StageResult(WorkfloContract):
    """Outcome of one orchestrator stage."""

    stage: Literal[
        "snapshot",
        "sandbox_ready",
        "analyze",
        "explore_baseline",
        "judge",
        "explore_llm",
        "report",
        "teardown",
    ]
    ok: bool
    failure_stage: str | None = None
    failure_reason: str | None = None
    duration_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def _ok_and_failure_are_exclusive(self) -> "StageResult":
        if self.ok and (self.failure_stage is not None or self.failure_reason is not None):
            raise ValueError("a successful StageResult must not carry failure_stage/failure_reason")
        if not self.ok and not self.failure_reason:
            raise ValueError("a failed StageResult must state failure_reason")
        return self


class EventRecord(WorkfloContract):
    """One append-only lifecycle event; bodies live behind payload_hash."""

    run_id: NonEmpty
    seq: int = Field(ge=0)
    ts: datetime
    stage: NonEmpty
    kind: NonEmpty
    payload_hash: Sha256


# ---------------------------------------------------------------------------
# Analyst outputs
# ---------------------------------------------------------------------------


class Route(WorkfloContract):
    method: NonEmpty
    path: NonEmpty
    source: Literal["parsed", "inferred"]


class ProjectMap(WorkfloContract):
    stack: NonEmpty
    entry_points: list[str]
    run_commands: list[str]
    ports: list[Port]
    routes: list[Route]
    deps_manifest_hashes: dict[NonEmpty, Sha256]


class Requirement(WorkfloContract):
    req_id: ReqId
    text: NonEmpty
    source_file: NonEmpty
    source_line: int = Field(ge=1)
    priority: int = Field(ge=0)


class RequirementSet(WorkfloContract):
    items: list[Requirement]


# ---------------------------------------------------------------------------
# Explorer outputs
# ---------------------------------------------------------------------------


class Probe(WorkfloContract):
    probe_id: NonEmpty
    kind: NonEmpty
    request: dict[str, Any]
    expected: NonEmpty
    req_id: ReqId | None = None


class ProbePlan(WorkfloContract):
    probes: list[Probe]


class Candidate(WorkfloContract):
    """Suspicious behavior — never a confirmed finding."""

    candidate_id: NonEmpty
    probe_id: NonEmpty
    observed: NonEmpty
    expected: NonEmpty
    evidence_refs: list[NonEmpty] = Field(min_length=1)
    req_id: ReqId | None = None
    origin: Literal["baseline", "llm"]


# ---------------------------------------------------------------------------
# Judge output
# ---------------------------------------------------------------------------


class Finding(WorkfloContract):
    finding_id: NonEmpty
    fingerprint: Sha256
    status: Literal["Confirmed", "Flaky", "Unconfirmed"]
    confidence: float = Field(ge=0.0, le=1.0)
    severity: NonEmpty
    repro_evidence_refs: list[NonEmpty]
    control_evidence_ref: NonEmpty | None = None
    req_id: ReqId | None = None

    @model_validator(mode="after")
    def _confirmed_needs_reproducibility(self) -> "Finding":
        if self.status == "Confirmed":
            if len(self.repro_evidence_refs) < 2:
                raise ValueError(
                    f"Confirmed requires >= 2 repro evidence refs, got {len(self.repro_evidence_refs)}"
                )
            if self.control_evidence_ref is None:
                raise ValueError("Confirmed requires a control_evidence_ref")
        return self


# ---------------------------------------------------------------------------
# Reporter inputs/outputs
# ---------------------------------------------------------------------------


class ReportDraft(WorkfloContract):
    """LLM-written prose for one finding; facts must come from the Finding."""

    finding_id: NonEmpty
    explanation: NonEmpty
    likely_cause_hypothesis: NonEmpty
    remediation_hint: NonEmpty
    cited_evidence_ids: list[NonEmpty]


def validate_report_draft(draft: ReportDraft, finding: Finding) -> None:
    """Invariant: cited evidence ids must be a subset of the finding's evidence."""
    allowed = set(finding.repro_evidence_refs)
    if finding.control_evidence_ref is not None:
        allowed.add(finding.control_evidence_ref)
    unknown = [e for e in draft.cited_evidence_ids if e not in allowed]
    if unknown:
        raise ValueError(
            f"cited_evidence_ids not in finding {finding.finding_id} evidence: {unknown}"
        )


class RunSummary(WorkfloContract):
    run_id: NonEmpty
    total: int = Field(ge=0)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    skipped: int = Field(ge=0)
    duration_seconds: float = Field(ge=0.0)


class RequirementStatus(WorkfloContract):
    req_id: ReqId
    status: Literal["verified", "failing", "uncovered", "inconclusive"]


class IsolationProof(WorkfloContract):
    backend: Backend
    canary_result: CanaryResult
    teardown_verified: bool


class ProviderProvenance(WorkfloContract):
    provider: NonEmpty
    model_id: NonEmpty
    privacy_mode: PrivacyMode
    calls: int = Field(ge=1)


class ReportBundle(WorkfloContract):
    run_summary: RunSummary
    findings: list[Finding]
    requirement_statuses: list[RequirementStatus]
    isolation_proof: IsolationProof
    model_stage_degraded: bool
    provider_provenance: list[ProviderProvenance]


# ---------------------------------------------------------------------------
# Model calls (provenance only — never bodies)
# ---------------------------------------------------------------------------


class ModelCallRecord(WorkfloContract):
    """Provenance of one model call. Prompt/response bodies are forbidden —
    only the prompt hash may be stored. extra=forbid makes any body field a
    validation error."""

    call_id: NonEmpty
    role: Literal["analyst", "explorer", "reporter"]
    provider: NonEmpty
    model_id: NonEmpty
    privacy_mode: PrivacyMode
    tokens_in: int = Field(ge=0)
    tokens_out: int = Field(ge=0)
    prompt_sha256: Sha256
    status: NonEmpty

    @field_validator("role")
    @classmethod
    def _judge_never_calls_models(cls, v: str) -> str:
        if v == "judge":
            raise ValueError("the Judge contains no LLM call; role 'judge' is invalid here")
        return v


__all__ = [
    "Backend",
    "CanaryResult",
    "Candidate",
    "EventRecord",
    "Finding",
    "IsolationProof",
    "ModelCallRecord",
    "PrivacyMode",
    "ProjectMap",
    "Probe",
    "ProbePlan",
    "ProviderProvenance",
    "ReportBundle",
    "ReportDraft",
    "Requirement",
    "RequirementSet",
    "RequirementStatus",
    "Route",
    "RunInput",
    "RunSummary",
    "SandboxHandle",
    "StageResult",
    "WorkfloContract",
    "validate_report_draft",
]
