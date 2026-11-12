"""Tests for canonical serialization, lifecycle, and outcomes (ADR-0016/0017)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from workflo_schema.contracts import (
    CANCELLABLE_STATES,
    TERMINAL_STATES,
    CanonicalizationError,
    ComponentVerificationStatus,
    ExecutionStatus,
    IllegalTransitionError,
    LifecycleState,
    QaVerdict,
    RunOutcomeV1,
    TransitionAuthority,
    TrustVerificationStatus,
    can_transition,
    canonical_json,
    digest_of,
    execution_status_for_terminal_state,
    format_utc_ms,
    is_clean_success,
    is_full_pass,
    is_terminal,
    required_authority,
    sha256_digest,
)


class TestCanonicalJson:
    def test_sorted_keys_and_compact_form(self) -> None:
        assert canonical_json({"b": 1, "a": [1, 2]}) == '{"a":[1,2],"b":1}'

    def test_non_ascii_values_stay_raw(self) -> None:
        assert canonical_json({"k": "héllo"}) == '{"k":"héllo"}'

    def test_key_order_does_not_change_digest(self) -> None:
        assert digest_of({"a": 1, "b": 2}) == digest_of({"b": 2, "a": 1})

    def test_null_is_preserved(self) -> None:
        assert canonical_json({"k": None}) == '{"k":null}'

    def test_floats_are_forbidden(self) -> None:
        with pytest.raises(CanonicalizationError):
            canonical_json({"v": 1.5})

    def test_non_ascii_keys_are_forbidden(self) -> None:
        with pytest.raises(CanonicalizationError):
            canonical_json({"clé": 1})

    def test_non_string_keys_are_forbidden(self) -> None:
        with pytest.raises(CanonicalizationError):
            canonical_json({1: "x"})

    def test_lone_surrogates_are_forbidden(self) -> None:
        with pytest.raises(CanonicalizationError):
            canonical_json({"k": "\ud800"})

    def test_digest_format_is_self_describing(self) -> None:
        digest = digest_of({"x": 1})
        assert digest.startswith("sha256:")
        assert len(digest) == len("sha256:") + 64

    def test_sha256_digest_of_raw_bytes(self) -> None:
        assert sha256_digest(b"") == "sha256:" + "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


class TestTimestamps:
    def test_format_utc_ms_truncates_to_milliseconds(self) -> None:
        dt = datetime(2026, 11, 11, 12, 0, 5, 123456, tzinfo=timezone.utc)
        assert format_utc_ms(dt) == "2026-11-11T12:00:05.123Z"

    def test_format_requires_aware_datetime(self) -> None:
        with pytest.raises(ValueError):
            format_utc_ms(datetime(2026, 11, 11, 12, 0, 5))

    def test_format_converts_to_utc(self) -> None:
        from datetime import timedelta

        tz = timezone(timedelta(hours=5))
        dt = datetime(2026, 11, 11, 17, 0, 0, 0, tzinfo=tz)
        assert format_utc_ms(dt) == "2026-11-11T12:00:00.000Z"


class TestLifecycleMachine:
    def test_authority_assignment(self) -> None:
        assert (
            required_authority(LifecycleState.CREATED, LifecycleState.ADMITTED)
            is TransitionAuthority.ADMISSION
        )
        assert (
            required_authority(LifecycleState.ADMITTED, LifecycleState.REJECTED)
            is TransitionAuthority.ADMISSION
        )
        assert (
            required_authority(LifecycleState.ADMITTED, LifecycleState.PROVISIONING)
            is TransitionAuthority.ORCHESTRATOR
        )
        assert (
            required_authority(
                LifecycleState.EXECUTING, LifecycleState.CANCEL_REQUESTED
            )
            is TransitionAuthority.USER
        )

    def test_illegal_transition_raises(self) -> None:
        with pytest.raises(IllegalTransitionError):
            required_authority(LifecycleState.CREATED, LifecycleState.EXECUTING)
        with pytest.raises(IllegalTransitionError):
            required_authority(LifecycleState.COMPLETED, LifecycleState.SIGNING)

    def test_cancellation_only_from_the_four_drawn_states(self) -> None:
        assert CANCELLABLE_STATES == {
            LifecycleState.PROVISIONING,
            LifecycleState.SOURCE_ACQUISITION,
            LifecycleState.PREPARING,
            LifecycleState.EXECUTING,
        }
        for state in LifecycleState:
            if state in CANCELLABLE_STATES:
                assert can_transition(state, LifecycleState.CANCEL_REQUESTED)
            elif state is not LifecycleState.CANCEL_REQUESTED:
                assert not can_transition(state, LifecycleState.CANCEL_REQUESTED)

    def test_cancelled_run_flows_through_teardown_to_completion(self) -> None:
        assert can_transition(
            LifecycleState.CANCEL_REQUESTED, LifecycleState.TEARDOWN
        )
        assert can_transition(LifecycleState.TEARDOWN, LifecycleState.VERIFYING_TEARDOWN)
        assert can_transition(LifecycleState.VERIFYING_TEARDOWN, LifecycleState.SIGNING)
        assert can_transition(LifecycleState.SIGNING, LifecycleState.COMPLETED)

    def test_terminal_states_have_no_outgoing_edges(self) -> None:
        for state in TERMINAL_STATES:
            assert is_terminal(state)
            assert not any(
                can_transition(state, target) for target in LifecycleState
            )
        assert LifecycleState.CANCEL_REQUESTED not in TERMINAL_STATES

    def test_teardown_failure_blocks_signing(self) -> None:
        assert can_transition(
            LifecycleState.VERIFYING_TEARDOWN, LifecycleState.TEARDOWN_FAILED
        )
        assert not can_transition(
            LifecycleState.TEARDOWN_FAILED, LifecycleState.SIGNING
        )
        assert is_terminal(LifecycleState.TEARDOWN_FAILED)

    def test_execution_status_mapping(self) -> None:
        assert (
            execution_status_for_terminal_state(LifecycleState.COMPLETED)
            is ExecutionStatus.COMPLETED
        )
        assert (
            execution_status_for_terminal_state(LifecycleState.TEARDOWN_FAILED)
            is ExecutionStatus.TEARDOWN_FAILED
        )
        with pytest.raises(ValueError):
            execution_status_for_terminal_state(LifecycleState.EXECUTING)


def _clean_outcome(**overrides: object) -> RunOutcomeV1:
    values: dict[str, object] = {
        "execution_status": ExecutionStatus.COMPLETED,
        "qa_verdict": QaVerdict.PASS,
        "trust_status": TrustVerificationStatus.VERIFIED_CLEAN,
        "evidence_validation": ComponentVerificationStatus.VERIFIED,
        "teardown_verification": ComponentVerificationStatus.VERIFIED,
        "receipt_status": ComponentVerificationStatus.VERIFIED,
    }
    values.update(overrides)
    return RunOutcomeV1(**values)  # type: ignore[arg-type]


class TestOutcomes:
    def test_clean_success_definition(self) -> None:
        assert is_clean_success(_clean_outcome())

    def test_cancelled_run_is_not_clean_success(self) -> None:
        outcome = _clean_outcome(cancelled=True)
        assert not is_clean_success(outcome)

    def test_tests_fail_is_a_clean_run_with_a_failing_verdict(self) -> None:
        # The verification process is clean; the QA verdict reports the
        # defect. The strict "everything passed" predicate is is_full_pass.
        outcome = _clean_outcome(qa_verdict=QaVerdict.FAIL)
        assert outcome.execution_status is ExecutionStatus.COMPLETED
        assert is_clean_success(outcome)
        assert not is_full_pass(outcome)

    def test_full_pass_requires_a_passing_verdict(self) -> None:
        assert is_full_pass(_clean_outcome(qa_verdict=QaVerdict.PASS))
        assert not is_full_pass(_clean_outcome(qa_verdict=QaVerdict.INCONCLUSIVE))
        assert not is_full_pass(_clean_outcome(cancelled=True))
        assert not is_full_pass(_clean_outcome(qa_verdict=QaVerdict.WARN))

    def test_completed_requires_verified_teardown(self) -> None:
        with pytest.raises(ValidationError):
            _clean_outcome(
                teardown_verification=ComponentVerificationStatus.FAILED
            )

    def test_completed_requires_verified_receipt(self) -> None:
        with pytest.raises(ValidationError):
            _clean_outcome(receipt_status=ComponentVerificationStatus.INCOMPLETE)

    def test_teardown_failed_status_contradicts_verified_teardown(self) -> None:
        with pytest.raises(ValidationError):
            _clean_outcome(execution_status=ExecutionStatus.TEARDOWN_FAILED)

    def test_infrastructure_failure_is_not_a_qa_failure(self) -> None:
        outcome = RunOutcomeV1(
            execution_status=ExecutionStatus.INFRASTRUCTURE_FAILED,
            qa_verdict=QaVerdict.NOT_APPLICABLE,
            trust_status=TrustVerificationStatus.UNKNOWN,
            evidence_validation=ComponentVerificationStatus.INCOMPLETE,
            teardown_verification=ComponentVerificationStatus.FAILED,
            receipt_status=ComponentVerificationStatus.NOT_APPLICABLE,
        )
        assert not is_clean_success(outcome)

    def test_outcome_is_frozen(self) -> None:
        outcome = _clean_outcome()
        with pytest.raises(ValidationError):
            outcome.qa_verdict = QaVerdict.FAIL  # type: ignore[misc]
