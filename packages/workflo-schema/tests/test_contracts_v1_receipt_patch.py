"""Tests for receipt v5 and the patch proposal/approval contract."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from workflo_schema.contracts import (
    ApprovalState,
    ComponentVerificationStatus,
    DsseEnvelopeV1,
    DsseSignatureV1,
    ExecutionStatus,
    PatchApprovalV1,
    PatchProposalV1,
    PatchState,
    PatchValidationCheckV1,
    PatchValidationRecordV1,
    ProducerComponent,
    ProducerIdentityV1,
    QaVerdict,
    ReceiptV5Payload,
    RunOutcomeV1,
    RuntimeIdentityV1,
    RuntimeType,
    SignerIdentityV1,
    SourceProvider,
    SourceProvenanceV1,
    SourceSpecV1,
    CapabilityId,
    RetentionSpecV1,
    RunCreatorV1,
    RunSpecV1,
    TeardownCheckId,
    TeardownCheckV1,
    TeardownVerificationV1,
    TrustVerificationStatus,
    approval_matches,
    can_transition_patch,
    check_receipt_binding,
    decode_dsse_payload,
    default_limitations,
    digest_of,
    encode_dsse_payload,
    extract_diff_paths,
    is_safe_relative_path,
    sha256_digest,
    utc_now_ms,
)

DIGEST = "sha256:" + "ab" * 32
DIGEST_2 = "sha256:" + "cd" * 32


def make_run_spec(**overrides: object) -> RunSpecV1:
    values: dict[str, object] = {
        "organization_id": "org_1",
        "project_id": "prj_1",
        "run_id": "run_1",
        "idempotency_key": "idem-key-00000001",
        "source": SourceSpecV1(
            provider=SourceProvider.GITHUB,
            url="https://github.com/example/repo.git",
            ref="main",
            commit="abc1234",
        ),
        "profile_id": "profile_standard",
        "policy_digest": DIGEST,
        "runtime_image_digest": DIGEST_2,
        "resource_profile": "standard",
        "capabilities": (CapabilityId.TESTS_EXECUTE,),
        "retention": RetentionSpecV1(retention_policy_id="retention_standard"),
        "created_by": RunCreatorV1(user_id="usr_1", organization_id="org_1"),
        "created_at": utc_now_ms(),
    }
    values.update(overrides)
    return RunSpecV1(**values)  # type: ignore[arg-type]


def make_teardown(**overrides: object) -> TeardownVerificationV1:
    checks = tuple(
        TeardownCheckV1(check_id=check_id, passed=True)
        for check_id in TeardownCheckId
    )
    values: dict[str, object] = {
        "verification_id": "tdv_1",
        "outcome": TrustVerificationStatus.VERIFIED_CLEAN,
        "verifier": ProducerIdentityV1(
            component=ProducerComponent.HOST_WORKER,
            instance_id="worker-1",
            version="0.1.0",
        ),
        "checks": checks,
        "observed_at": utc_now_ms(),
    }
    values.update(overrides)
    return TeardownVerificationV1(**values)  # type: ignore[arg-type]


def make_outcome(**overrides: object) -> RunOutcomeV1:
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


def make_receipt_payload(**overrides: object) -> ReceiptV5Payload:
    values: dict[str, object] = {
        "receipt_id": "rcpt_1",
        "organization_id": "org_1",
        "project_id": "prj_1",
        "run_id": "run_1",
        "attempt_id": "attempt_1",
        "sandbox_id": "sbx_1",
        "source": SourceProvenanceV1(
            provider=SourceProvider.GITHUB,
            url="https://github.com/example/repo.git",
            ref="main",
            commit="abc1234",
            snapshot_digest=DIGEST,
        ),
        "execution_policy_digest": DIGEST,
        "runtime": RuntimeIdentityV1(
            runtime_type=RuntimeType.MICROVM,
            runtime_image_digest=DIGEST_2,
            guest_kernel_digest=DIGEST,
            guest_rootfs_digest=DIGEST_2,
        ),
        "execution_started_at": utc_now_ms(),
        "execution_completed_at": utc_now_ms(),
        "outcome": make_outcome(),
        "finding_summary_digest": DIGEST,
        "evidence_manifest_digest": DIGEST_2,
        "evidence_ledger_root": DIGEST,
        "evidence_chain_version": 2,
        "teardown_verification": make_teardown(),
        "limitations": default_limitations(),
        "signer_identity": SignerIdentityV1(
            signer_id="signer_1",
            key_id="key_1",
            provider="file-dev",
            public_key_fingerprint=DIGEST,
        ),
        "issued_at": utc_now_ms(),
    }
    values.update(overrides)
    return ReceiptV5Payload(**values)  # type: ignore[arg-type]


class TestTeardownVerification:
    def test_verified_clean_requires_every_check(self) -> None:
        checks = list(make_teardown().checks)
        checks[0] = TeardownCheckV1(
            check_id=TeardownCheckId.VMM_EXITED, passed=False
        )
        with pytest.raises(ValidationError):
            make_teardown(checks=tuple(checks))

    def test_non_clean_outcome_with_all_checks_passing_is_contradictory(self) -> None:
        with pytest.raises(ValidationError):
            make_teardown(outcome=TrustVerificationStatus.VERIFICATION_FAILED)

    def test_all_eight_checks_required(self) -> None:
        with pytest.raises(ValidationError):
            make_teardown(checks=make_teardown().checks[:-1])

    def test_duplicate_checks_rejected(self) -> None:
        checks = list(make_teardown().checks)
        checks[1] = checks[0]
        with pytest.raises(ValidationError):
            make_teardown(checks=tuple(checks))


class TestReceiptV5:
    def test_payload_round_trips_through_envelope(self) -> None:
        payload = make_receipt_payload()
        envelope = DsseEnvelopeV1(
            payload=encode_dsse_payload(payload),
            signatures=(DsseSignatureV1(keyid="key_1", sig="c2ln"),),
        )
        decoded = decode_dsse_payload(envelope)
        assert decoded.payload_digest() == payload.payload_digest()
        assert decoded.receipt_version == 5

    def test_payload_digest_is_stable(self) -> None:
        payload = make_receipt_payload()
        assert payload.payload_digest() == payload.payload_digest()

    def test_signing_unvalidated_outcome_is_not_representable(self) -> None:
        # execution=completed with failed teardown contradicts the machine,
        # so a receipt cannot even be constructed around it.
        with pytest.raises(ValidationError):
            make_outcome(
                teardown_verification=ComponentVerificationStatus.FAILED
            )

    def test_limitations_are_required_and_non_empty(self) -> None:
        with pytest.raises(ValidationError):
            make_receipt_payload(limitations=())
        assert len(default_limitations()) >= 3

    def test_binding_check_passes_for_matching_spec(self) -> None:
        spec = make_run_spec(
            source=SourceSpecV1(
                provider=SourceProvider.GITHUB,
                url="https://github.com/example/repo.git",
                ref="main",
                commit="abc1234",
                snapshot_digest=DIGEST,
            )
        )
        assert check_receipt_binding(make_receipt_payload(), spec) == []

    def test_binding_check_reports_mismatches(self) -> None:
        spec = make_run_spec(run_id="run_other")
        mismatches = check_receipt_binding(make_receipt_payload(), spec)
        assert any("run_id" in item for item in mismatches)


def make_diff(new_line: str = "new") -> str:
    return (
        "--- a/src/app.py\n"
        "+++ b/src/app.py\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        f"+{new_line}\n"
    )


def make_proposal(**overrides: object) -> PatchProposalV1:
    diff = make_diff()
    values: dict[str, object] = {
        "proposal_id": "patch_1",
        "organization_id": "org_1",
        "project_id": "prj_1",
        "origin_run_id": "run_1",
        "origin_attempt_id": "attempt_1",
        "finding_id": "find_1",
        "base_commit": "abc1234",
        "base_snapshot_digest": DIGEST,
        "target_ref": "refs/heads/main",
        "patch_digest": sha256_digest(diff.encode("utf-8")),
        "diff_text": diff,
        "allowed_files": ("src/app.py",),
        "generator": ProducerIdentityV1(
            component=ProducerComponent.AGENT_RUNTIME,
            instance_id="agent-1",
            version="0.1.0",
        ),
        "created_at": utc_now_ms(),
    }
    values.update(overrides)
    return PatchProposalV1(**values)  # type: ignore[arg-type]


def make_approval(proposal: PatchProposalV1, **overrides: object) -> PatchApprovalV1:
    values: dict[str, object] = {
        "approval_id": "approval_1",
        "proposal_id": proposal.proposal_id,
        "proposal_digest": proposal.proposal_digest(),
        "patch_digest": proposal.patch_digest,
        "base_commit": proposal.base_commit,
        "base_snapshot_digest": proposal.base_snapshot_digest,
        "target_ref": proposal.target_ref,
        "allowed_paths_digest": digest_of(list(proposal.allowed_files)),
        "approved_by": "usr_reviewer",
        "authorization_version": "authz-v1",
        "approved_at": utc_now_ms(),
        "nonce": "nonce-0123456789abcdef",
    }
    values.update(overrides)
    return PatchApprovalV1(**values)  # type: ignore[arg-type]


class TestPatchPathSafety:
    @pytest.mark.parametrize(
        "path",
        [
            "src/app.py",
            "docs/readme.md",
            ".github/workflows/ci.yml",
            "a_b/c-d/e.f",
        ],
    )
    def test_safe_paths(self, path: str) -> None:
        assert is_safe_relative_path(path)

    @pytest.mark.parametrize(
        "path",
        [
            "../outside.py",
            "/etc/passwd",
            "C:\\Windows\\system32",
            "src\\app.py",
            "a//b.py",
            "src/./app.py",
            "a/../../b.py",
            "src/ap p.py",
            "héllo.py",
            "",
            "..",
            "src/app.py\x00",
        ],
    )
    def test_unsafe_paths(self, path: str) -> None:
        assert not is_safe_relative_path(path)

    def test_diff_paths_extracted(self) -> None:
        assert extract_diff_paths(make_diff()) == ["src/app.py"]

    def test_dev_null_paths_ignored(self) -> None:
        diff = (
            "--- /dev/null\n"
            "+++ b/new_file.py\n"
            "@@ -0,0 +1 @@\n"
            "+content\n"
        )
        assert extract_diff_paths(diff) == ["new_file.py"]


class TestPatchProposal:
    def test_digest_must_match_exact_bytes(self) -> None:
        with pytest.raises(ValidationError):
            make_proposal(patch_digest=DIGEST)

    def test_diff_outside_allowed_files_rejected(self) -> None:
        with pytest.raises(ValidationError):
            make_proposal(allowed_files=("other.py",))

    def test_unsafe_allowed_files_rejected(self) -> None:
        with pytest.raises(ValidationError):
            make_proposal(allowed_files=("../escape.py", "src/app.py"))

    def test_proposal_digest_is_stable_across_state_changes(self) -> None:
        proposal = make_proposal()
        transitioned = proposal.model_copy(update={"state": PatchState.READY_FOR_REVIEW})
        assert transitioned.proposal_digest() == proposal.proposal_digest()

    def test_proposal_digest_changes_when_bytes_change(self) -> None:
        proposal = make_proposal()
        new_diff = make_diff("different")
        changed = proposal.model_copy(
            update={
                "diff_text": new_diff,
                "patch_digest": sha256_digest(new_diff.encode("utf-8")),
            }
        )
        assert changed.proposal_digest() != proposal.proposal_digest()


class TestApprovalBinding:
    def test_approval_matches_exact_proposal(self) -> None:
        proposal = make_proposal()
        approval = make_approval(proposal)
        assert approval_matches(proposal, approval)

    def test_changed_bytes_invalidate_approval(self) -> None:
        proposal = make_proposal()
        approval = make_approval(proposal)
        new_diff = make_diff("tampered")
        tampered = proposal.model_copy(
            update={
                "diff_text": new_diff,
                "patch_digest": sha256_digest(new_diff.encode("utf-8")),
            }
        )
        assert not approval_matches(tampered, approval)

    def test_changed_base_invalidates_approval(self) -> None:
        proposal = make_proposal()
        approval = make_approval(proposal)
        rebased = proposal.model_copy(update={"base_commit": "def5678"})
        assert not approval_matches(rebased, approval)

    def test_path_change_invalidates_approval(self) -> None:
        proposal = make_proposal()
        approval = make_approval(proposal)
        widened = proposal.model_copy(
            update={"allowed_files": ("src/app.py", "src/other.py")}
        )
        assert not approval_matches(widened, approval)

    def test_consumed_approval_never_matches(self) -> None:
        proposal = make_proposal()
        approval = make_approval(proposal, state=ApprovalState.CONSUMED)
        assert not approval_matches(proposal, approval)

    def test_revoked_approval_never_matches(self) -> None:
        proposal = make_proposal()
        approval = make_approval(proposal, state=ApprovalState.REVOKED)
        assert not approval_matches(proposal, approval)


class TestPatchStateMachine:
    def test_happy_path(self) -> None:
        chain = [
            PatchState.PROPOSED,
            PatchState.VALIDATING,
            PatchState.READY_FOR_REVIEW,
            PatchState.APPROVED,
            PatchState.APPLYING_IN_SANDBOX,
            PatchState.PATCH_APPLIED_IN_SANDBOX,
            PatchState.VERIFYING,
            PatchState.VERIFIED,
        ]
        for source, target in zip(chain, chain[1:]):
            assert can_transition_patch(source, target)

    def test_terminal_states_have_no_outgoing_edges(self) -> None:
        for state in (
            PatchState.REJECTED,
            PatchState.VERIFIED,
            PatchState.REGRESSION,
            PatchState.INCONCLUSIVE,
            PatchState.EXPIRED,
            PatchState.REVOKED,
        ):
            assert not any(
                can_transition_patch(state, target) for target in PatchState
            )

    def test_apply_cannot_skip_approval(self) -> None:
        assert not can_transition_patch(
            PatchState.READY_FOR_REVIEW, PatchState.APPLYING_IN_SANDBOX
        )

    def test_verifying_cannot_jump_to_approved(self) -> None:
        assert not can_transition_patch(PatchState.VERIFYING, PatchState.APPROVED)


class TestPatchValidationRecord:
    def test_ready_for_review_requires_validation_record(self) -> None:
        with pytest.raises(ValidationError):
            make_proposal(state=PatchState.READY_FOR_REVIEW)

    def test_ready_for_review_with_record(self) -> None:
        proposal = make_proposal()
        record = PatchValidationRecordV1(
            validator=ProducerIdentityV1(
                component=ProducerComponent.ORCHESTRATOR,
                instance_id="orch-1",
                version="0.1.0",
            ),
            validated_at=utc_now_ms(),
            diff_digest=proposal.patch_digest,
            files_touched=1,
            additions=1,
            deletions=1,
            checks=(
                PatchValidationCheckV1(check_id="paths", passed=True),
                PatchValidationCheckV1(check_id="size", passed=True),
            ),
        )
        ready = proposal.model_copy(
            update={"state": PatchState.READY_FOR_REVIEW, "validation": record}
        )
        assert ready.state is PatchState.READY_FOR_REVIEW
        assert ready.proposal_digest() == proposal.proposal_digest()

    def test_mismatched_validation_digest_rejected(self) -> None:
        proposal = make_proposal()
        record = PatchValidationRecordV1(
            validator=ProducerIdentityV1(
                component=ProducerComponent.ORCHESTRATOR,
                instance_id="orch-1",
                version="0.1.0",
            ),
            validated_at=utc_now_ms(),
            diff_digest=DIGEST,
            files_touched=1,
            additions=1,
            deletions=1,
            checks=(PatchValidationCheckV1(check_id="paths", passed=True),),
        )
        # Construct through the full validator (model_copy bypasses it).
        with pytest.raises(ValidationError):
            make_proposal(state=PatchState.READY_FOR_REVIEW, validation=record)
