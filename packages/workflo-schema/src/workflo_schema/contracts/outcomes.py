"""Three independent run outcomes (ADR-0017).

Execution status, QA verdict, and trust status are stored and reported
separately. A clean success is a defined predicate, never an inference.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator

from workflo_schema.contracts.common import SCHEMA_VERSION
from workflo_schema.contracts.lifecycle import LifecycleState

__all__ = [
    "ExecutionStatus",
    "QaVerdict",
    "TrustVerificationStatus",
    "ComponentVerificationStatus",
    "RunOutcomeV1",
    "EXECUTION_STATUS_BY_TERMINAL_STATE",
    "execution_status_for_terminal_state",
    "is_clean_success",
    "is_full_pass",
]


class ExecutionStatus(str, Enum):
    """What happened to the run workflow itself."""

    COMPLETED = "completed"
    REJECTED = "rejected"
    INFRASTRUCTURE_FAILED = "infrastructure_failed"
    EXECUTION_FAILED = "execution_failed"
    TEARDOWN_FAILED = "teardown_failed"
    ATTESTATION_FAILED = "attestation_failed"


class QaVerdict(str, Enum):
    """What the QA checks found (independent of execution and trust)."""

    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    INCONCLUSIVE = "inconclusive"
    NOT_APPLICABLE = "not_applicable"


class TrustVerificationStatus(str, Enum):
    """Teardown verification outcomes; only VERIFIED_CLEAN is clean."""

    VERIFIED_CLEAN = "verified_clean"
    VERIFICATION_FAILED = "verification_failed"
    CLEANUP_INCOMPLETE = "cleanup_incomplete"
    UNKNOWN = "unknown"


class ComponentVerificationStatus(str, Enum):
    VERIFIED = "verified"
    FAILED = "failed"
    INCOMPLETE = "incomplete"
    NOT_APPLICABLE = "not_applicable"


EXECUTION_STATUS_BY_TERMINAL_STATE: dict[LifecycleState, ExecutionStatus] = {
    LifecycleState.COMPLETED: ExecutionStatus.COMPLETED,
    LifecycleState.REJECTED: ExecutionStatus.REJECTED,
    LifecycleState.INFRASTRUCTURE_FAILED: ExecutionStatus.INFRASTRUCTURE_FAILED,
    LifecycleState.EXECUTION_FAILED: ExecutionStatus.EXECUTION_FAILED,
    LifecycleState.TEARDOWN_FAILED: ExecutionStatus.TEARDOWN_FAILED,
    LifecycleState.ATTESTATION_FAILED: ExecutionStatus.ATTESTATION_FAILED,
}


def execution_status_for_terminal_state(state: LifecycleState) -> ExecutionStatus:
    """Map a terminal lifecycle state onto its execution status."""
    try:
        return EXECUTION_STATUS_BY_TERMINAL_STATE[state]
    except KeyError as exc:
        raise ValueError(f"{state.value} is not a terminal state") from exc


class RunOutcomeV1(BaseModel):
    """The frozen outcome record; all three dimensions are explicit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = SCHEMA_VERSION
    execution_status: ExecutionStatus
    cancelled: bool = False
    qa_verdict: QaVerdict
    trust_status: TrustVerificationStatus
    evidence_validation: ComponentVerificationStatus
    teardown_verification: ComponentVerificationStatus
    receipt_status: ComponentVerificationStatus

    @model_validator(mode="after")
    def _machine_consistency(self) -> "RunOutcomeV1":
        # The frozen machine reaches COMPLETED only through SIGNING, which is
        # reachable only after teardown verification passed. A "completed"
        # execution with failed/incomplete teardown or receipt is therefore
        # contradictory and must not be representable.
        if self.execution_status is ExecutionStatus.COMPLETED:
            if self.teardown_verification is not ComponentVerificationStatus.VERIFIED:
                raise ValueError(
                    "execution_status=completed requires verified teardown "
                    "(teardown failure prevents clean completion)"
                )
            if self.receipt_status is not ComponentVerificationStatus.VERIFIED:
                raise ValueError(
                    "execution_status=completed requires a verified receipt"
                )
            if self.trust_status is TrustVerificationStatus.UNKNOWN:
                raise ValueError(
                    "execution_status=completed cannot carry an unknown trust status"
                )
        if self.execution_status is ExecutionStatus.TEARDOWN_FAILED:
            if self.teardown_verification is ComponentVerificationStatus.VERIFIED:
                raise ValueError(
                    "execution_status=teardown_failed contradicts verified teardown"
                )
        return self

    def is_clean_success(self) -> bool:
        """The frozen definition of a clean success."""
        return is_clean_success(self)


def is_clean_success(outcome: RunOutcomeV1) -> bool:
    """Whether the verification process itself is clean.

    This is about the run's execution and trust dimensions only: the run
    completed, was not cancelled, and evidence/teardown/receipt all
    verified. The QA verdict is deliberately independent — a verified
    failing check is reported via ``qa_verdict``, not by downgrading trust
    (the brief: "tests may pass while teardown fails; that is not clean
    success" — the converse, a clean run that found real failures, is a
    successful verification run).
    """
    return (
        outcome.execution_status is ExecutionStatus.COMPLETED
        and not outcome.cancelled
        and outcome.trust_status is TrustVerificationStatus.VERIFIED_CLEAN
        and outcome.evidence_validation is ComponentVerificationStatus.VERIFIED
        and outcome.teardown_verification is ComponentVerificationStatus.VERIFIED
        and outcome.receipt_status is ComponentVerificationStatus.VERIFIED
    )


def is_full_pass(outcome: RunOutcomeV1) -> bool:
    """Clean verification *and* nothing failed: the strictest success.

    Use this (never ``is_clean_success``) anywhere a user-facing "checks
    passed" claim is being made.
    """
    return is_clean_success(outcome) and outcome.qa_verdict is QaVerdict.PASS
