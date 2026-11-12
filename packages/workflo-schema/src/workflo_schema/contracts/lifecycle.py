"""Frozen run lifecycle state machine (ADR-0017).

The states and edges are taken verbatim from the Product Engineering Brief.
Guest components never advance product state; every transition has exactly
one authority. Cancellation is a request that still flows through teardown,
verification, and signing.
"""

from __future__ import annotations

from enum import Enum
from types import MappingProxyType
from typing import Mapping


class LifecycleState(str, Enum):
    CREATED = "CREATED"
    ADMITTED = "ADMITTED"
    PROVISIONING = "PROVISIONING"
    SOURCE_ACQUISITION = "SOURCE_ACQUISITION"
    PREPARING = "PREPARING"
    EXECUTING = "EXECUTING"
    EVALUATING = "EVALUATING"
    COLLECTING_EVIDENCE = "COLLECTING_EVIDENCE"
    TEARDOWN = "TEARDOWN"
    VERIFYING_TEARDOWN = "VERIFYING_TEARDOWN"
    SIGNING = "SIGNING"
    COMPLETED = "COMPLETED"
    INFRASTRUCTURE_FAILED = "INFRASTRUCTURE_FAILED"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    TEARDOWN_FAILED = "TEARDOWN_FAILED"
    ATTESTATION_FAILED = "ATTESTATION_FAILED"
    REJECTED = "REJECTED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"


class TransitionAuthority(str, Enum):
    """Who owns a legal transition."""

    ADMISSION = "admission"          # control plane admission decision
    ORCHESTRATOR = "orchestrator"    # durable orchestration / lifecycle owner
    USER = "user"                    # cancellation request only


class IllegalTransitionError(ValueError):
    """Raised when a transition is not part of the frozen machine."""


TERMINAL_STATES: frozenset[LifecycleState] = frozenset(
    {
        LifecycleState.COMPLETED,
        LifecycleState.INFRASTRUCTURE_FAILED,
        LifecycleState.EXECUTION_FAILED,
        LifecycleState.TEARDOWN_FAILED,
        LifecycleState.ATTESTATION_FAILED,
        LifecycleState.REJECTED,
    }
)

_LEGAL: dict[LifecycleState, frozenset[LifecycleState]] = {
    LifecycleState.CREATED: frozenset({LifecycleState.ADMITTED}),
    LifecycleState.ADMITTED: frozenset(
        {LifecycleState.PROVISIONING, LifecycleState.REJECTED}
    ),
    LifecycleState.PROVISIONING: frozenset(
        {
            LifecycleState.SOURCE_ACQUISITION,
            LifecycleState.INFRASTRUCTURE_FAILED,
            LifecycleState.CANCEL_REQUESTED,
        }
    ),
    LifecycleState.SOURCE_ACQUISITION: frozenset(
        {
            LifecycleState.PREPARING,
            LifecycleState.EXECUTION_FAILED,
            LifecycleState.CANCEL_REQUESTED,
        }
    ),
    LifecycleState.PREPARING: frozenset(
        {
            LifecycleState.EXECUTING,
            LifecycleState.EXECUTION_FAILED,
            LifecycleState.CANCEL_REQUESTED,
        }
    ),
    LifecycleState.EXECUTING: frozenset(
        {
            LifecycleState.EVALUATING,
            LifecycleState.EXECUTION_FAILED,
            LifecycleState.CANCEL_REQUESTED,
        }
    ),
    LifecycleState.EVALUATING: frozenset({LifecycleState.COLLECTING_EVIDENCE}),
    LifecycleState.COLLECTING_EVIDENCE: frozenset({LifecycleState.TEARDOWN}),
    LifecycleState.TEARDOWN: frozenset({LifecycleState.VERIFYING_TEARDOWN}),
    LifecycleState.VERIFYING_TEARDOWN: frozenset(
        {LifecycleState.SIGNING, LifecycleState.TEARDOWN_FAILED}
    ),
    LifecycleState.SIGNING: frozenset(
        {LifecycleState.COMPLETED, LifecycleState.ATTESTATION_FAILED}
    ),
    LifecycleState.CANCEL_REQUESTED: frozenset({LifecycleState.TEARDOWN}),
}

LEGAL_TRANSITIONS: Mapping[LifecycleState, frozenset[LifecycleState]] = (
    MappingProxyType(_LEGAL)
)

# Cancellation may be requested only from these four active states, exactly
# as drawn in the frozen baseline machine.
CANCELLABLE_STATES: frozenset[LifecycleState] = frozenset(
    {
        LifecycleState.PROVISIONING,
        LifecycleState.SOURCE_ACQUISITION,
        LifecycleState.PREPARING,
        LifecycleState.EXECUTING,
    }
)


def is_terminal(state: LifecycleState) -> bool:
    """Whether ``state`` is a terminal lifecycle state."""
    return state in TERMINAL_STATES


def can_transition(source: LifecycleState, target: LifecycleState) -> bool:
    """Whether ``source -> target`` is a legal transition."""
    return target in LEGAL_TRANSITIONS.get(source, frozenset())


def required_authority(
    source: LifecycleState, target: LifecycleState
) -> TransitionAuthority:
    """Authority that owns the ``source -> target`` transition.

    Raises :class:`IllegalTransitionError` when the transition is not legal.
    """
    if not can_transition(source, target):
        raise IllegalTransitionError(f"illegal transition {source.value} -> {target.value}")
    if source is LifecycleState.CREATED and target is LifecycleState.ADMITTED:
        return TransitionAuthority.ADMISSION
    if source is LifecycleState.ADMITTED and target is LifecycleState.REJECTED:
        return TransitionAuthority.ADMISSION
    if target is LifecycleState.CANCEL_REQUESTED:
        return TransitionAuthority.USER
    return TransitionAuthority.ORCHESTRATOR
