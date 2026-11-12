"""Tests for RunSpec, policy, events, findings, and evidence contracts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from workflo_schema.contracts import (
    CapabilityId,
    DetectorIdentityV1,
    EvidenceArtifactType,
    EvidenceArtifactV1,
    EvidenceClassification,
    EvidenceManifestV1,
    EvidenceScopeError,
    EventType,
    ExecutionPolicyBundleV1,
    FindingCategory,
    FindingV1,
    ModelArtifactRefV1,
    ModelArtifactRole,
    ModelProvenanceV1,
    NetworkPolicySpecV1,
    PolicyComponentId,
    PolicyComponentV1,
    ProducerComponent,
    ProducerIdentityV1,
    RetentionSpecV1,
    RunCreatorV1,
    RunEventV1,
    RunSpecV1,
    Severity,
    SourceProvider,
    SourceSpecV1,
    ValidationState,
    VerificationStampV1,
    build_event_payload_digest,
    can_drive_lifecycle,
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


class TestRunSpec:
    def test_valid_spec(self) -> None:
        spec = make_run_spec()
        assert spec.network_policy.default == "deny"
        assert spec.network_policy.allowed_destinations == ()

    def test_spec_is_immutable(self) -> None:
        spec = make_run_spec()
        with pytest.raises(ValidationError):
            spec.run_id = "run_2"  # type: ignore[misc]

    def test_url_scheme_restricted(self) -> None:
        with pytest.raises(ValidationError):
            SourceSpecV1(
                provider=SourceProvider.GITHUB,
                url="http://insecure.example.com/repo.git",
                ref="main",
                commit="abc1234",
            )

    def test_commit_must_be_hex_not_a_ref(self) -> None:
        with pytest.raises(ValidationError):
            SourceSpecV1(
                provider=SourceProvider.GITHUB,
                url="https://example.com/repo.git",
                ref="main",
                commit="main",
            )

    def test_capabilities_must_be_unique_and_non_empty(self) -> None:
        with pytest.raises(ValidationError):
            make_run_spec(capabilities=())
        with pytest.raises(ValidationError):
            make_run_spec(
                capabilities=(
                    CapabilityId.TESTS_EXECUTE,
                    CapabilityId.TESTS_EXECUTE,
                )
            )

    def test_model_artifacts_unique(self) -> None:
        artifact = ModelArtifactRefV1(
            artifact_id="art_1", role=ModelArtifactRole.BASE, digest=DIGEST
        )
        with pytest.raises(ValidationError):
            make_run_spec(model_artifacts=(artifact, artifact))

    def test_idempotency_key_bounds(self) -> None:
        with pytest.raises(ValidationError):
            make_run_spec(idempotency_key="short")


def make_component(component: PolicyComponentId) -> PolicyComponentV1:
    return PolicyComponentV1.build(
        component=component,
        version="1.0",
        authority="organization:security",
        payload={"mode": "default", "component": component.value},
    )


class TestPolicyBundle:
    def _bundle(self) -> ExecutionPolicyBundleV1:
        return ExecutionPolicyBundleV1(
            bundle_id="policy_1",
            organization_id="org_1",
            version="1",
            created_by=RunCreatorV1(user_id="usr_1", organization_id="org_1"),
            created_at=utc_now_ms(),
            components=tuple(make_component(c) for c in PolicyComponentId),
        )

    def test_bundle_requires_all_twelve_components(self) -> None:
        components = [make_component(c) for c in PolicyComponentId]
        with pytest.raises(ValidationError):
            ExecutionPolicyBundleV1(
                bundle_id="policy_1",
                organization_id="org_1",
                version="1",
                created_by=RunCreatorV1(user_id="usr_1", organization_id="org_1"),
                created_at=utc_now_ms(),
                components=tuple(components[:11]),
            )

    def test_duplicate_components_rejected(self) -> None:
        components = [make_component(c) for c in PolicyComponentId]
        components[-1] = components[0]
        with pytest.raises(ValidationError):
            ExecutionPolicyBundleV1(
                bundle_id="policy_1",
                organization_id="org_1",
                version="1",
                created_by=RunCreatorV1(user_id="usr_1", organization_id="org_1"),
                created_at=utc_now_ms(),
                components=tuple(components),
            )

    def test_component_digest_is_verified(self) -> None:
        component = make_component(PolicyComponentId.NETWORK)
        body = component.model_dump()
        body["digest"] = DIGEST  # tampered
        with pytest.raises(ValidationError):
            PolicyComponentV1(**body)

    def test_bundle_digest_is_stable(self) -> None:
        bundle = self._bundle()
        assert bundle.digest() == bundle.digest()
        assert bundle.digest().startswith("sha256:")

    def test_bundle_digest_changes_when_a_component_changes(self) -> None:
        bundle = self._bundle()
        changed = list(bundle.components)
        changed[0] = PolicyComponentV1.build(
            component=PolicyComponentId.SOURCE,
            version="2.0",
            authority="organization:security",
            payload={"mode": "changed"},
        )
        rebuilt = bundle.model_copy(update={"components": tuple(changed)})
        assert rebuilt.digest() != bundle.digest()


def make_producer(component: ProducerComponent = ProducerComponent.GUEST_SUPERVISOR) -> ProducerIdentityV1:
    return ProducerIdentityV1(
        component=component, instance_id="inst-1", version="0.1.0"
    )


def make_event(**overrides: object) -> RunEventV1:
    values: dict[str, object] = {
        "event_id": "evt_0001",
        "organization_id": "org_1",
        "project_id": "prj_1",
        "run_id": "run_1",
        "attempt_id": "attempt_1",
        "sequence_number": 1,
        "event_type": EventType.SANDBOX_READY,
        "occurred_at": utc_now_ms(),
        "producer": make_producer(),
        "correlation_id": "corr_1",
        "payload": {"image_digest": DIGEST},
    }
    values.update(overrides)
    return RunEventV1.build(**values)  # type: ignore[arg-type]


class TestEvents:
    def test_build_computes_matching_payload_digest(self) -> None:
        event = make_event()
        assert event.payload_digest == build_event_payload_digest(event.payload)

    def test_mismatched_payload_digest_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RunEventV1(
                event_id="evt_1",
                organization_id="org_1",
                project_id="prj_1",
                run_id="run_1",
                attempt_id="attempt_1",
                sequence_number=1,
                event_type=EventType.SANDBOX_READY,
                occurred_at=utc_now_ms(),
                producer=make_producer(),
                correlation_id="corr_1",
                payload_digest=DIGEST,
                payload={"different": True},
            )

    def test_chain_of_thought_fields_rejected(self) -> None:
        for key in ("thought", "reasoning", "chain_of_thought", "scratchpad"):
            with pytest.raises(ValidationError):
                make_event(payload={key: "hidden reasoning"})

    def test_nested_cognition_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            make_event(payload={"steps": [{"internal": "x"}]})

    def test_floats_rejected_in_payload(self) -> None:
        # The digest helper canonicalizes first, so the failure surfaces as
        # a CanonicalizationError (a ValueError) rather than ValidationError.
        with pytest.raises(ValueError):
            make_event(payload={"duration": 1.5})

    def test_trust_classes(self) -> None:
        assert can_drive_lifecycle(
            make_producer(ProducerComponent.ORCHESTRATOR)
        )
        assert can_drive_lifecycle(make_producer(ProducerComponent.HOST_WORKER))
        assert not can_drive_lifecycle(
            make_producer(ProducerComponent.GUEST_SUPERVISOR)
        )
        assert not can_drive_lifecycle(
            make_producer(ProducerComponent.AGENT_RUNTIME)
        )

    def test_sequence_starts_at_one(self) -> None:
        with pytest.raises(ValidationError):
            make_event(sequence_number=0)


def make_stamp() -> VerificationStampV1:
    return VerificationStampV1(
        verifier=DetectorIdentityV1(
            component=ProducerComponent.JUDGE,
            version="1.0",
            ruleset_id="judge-rules-v1",
        ),
        criteria_id="reproduced-twice",
        procedure="same endpoint failed twice; control endpoint succeeded",
        verified_at=utc_now_ms(),
    )


def make_finding(**overrides: object) -> FindingV1:
    values: dict[str, object] = {
        "finding_id": "find_1",
        "organization_id": "org_1",
        "project_id": "prj_1",
        "run_id": "run_1",
        "attempt_id": "attempt_1",
        "source_revision": "abc1234",
        "title": "Endpoint returns 500 on duplicate input",
        "category": FindingCategory.VERIFIED_FAILURE,
        "severity": Severity.HIGH,
        "expected_behavior": "Duplicate input is rejected with 409",
        "observed_behavior": "Server error 500",
        "evidence_refs": ("art_1",),
        "detector": DetectorIdentityV1(
            component=ProducerComponent.JUDGE, version="1.0"
        ),
        "verified_by": make_stamp(),
        "created_at": utc_now_ms(),
    }
    values.update(overrides)
    return FindingV1(**values)  # type: ignore[arg-type]


class TestFindings:
    def test_verified_failure_requires_evidence_and_stamp(self) -> None:
        with pytest.raises(ValidationError):
            make_finding(evidence_refs=())
        with pytest.raises(ValidationError):
            make_finding(verified_by=None)

    def test_candidate_cannot_carry_a_verification_stamp(self) -> None:
        with pytest.raises(ValidationError):
            make_finding(category=FindingCategory.CANDIDATE)

    def test_only_the_judge_can_stamp_verification(self) -> None:
        with pytest.raises(ValidationError):
            VerificationStampV1(
                verifier=DetectorIdentityV1(
                    component=ProducerComponent.AGENT_RUNTIME,
                    version="1.0",
                    ruleset_id="model-said-so",
                ),
                criteria_id="model-confidence",
                procedure="the model said it was real",
                verified_at=utc_now_ms(),
            )

    def test_model_can_produce_candidate_with_provenance(self) -> None:
        finding = make_finding(
            category=FindingCategory.CANDIDATE,
            verified_by=None,
            detector=DetectorIdentityV1(
                component=ProducerComponent.AGENT_RUNTIME, version="1.0"
            ),
            model_provenance=ModelProvenanceV1(
                model_id="qwen3-4b",
                model_version="1",
                model_digest=DIGEST,
                runtime_version="llama.cpp-b4500",
                prompt_schema_version="explorer-v1",
            ),
        )
        assert finding.category is FindingCategory.CANDIDATE

    def test_infrastructure_failure_severity_capped(self) -> None:
        with pytest.raises(ValidationError):
            make_finding(
                category=FindingCategory.INFRASTRUCTURE_FAILURE,
                verified_by=None,
                severity=Severity.CRITICAL,
            )

    def test_evidence_refs_must_be_unique(self) -> None:
        with pytest.raises(ValidationError):
            make_finding(evidence_refs=("art_1", "art_1"))


def make_artifact(artifact_id: str = "art_1", **overrides: object) -> EvidenceArtifactV1:
    values: dict[str, object] = {
        "artifact_id": artifact_id,
        "organization_id": "org_1",
        "project_id": "prj_1",
        "run_id": "run_1",
        "attempt_id": "attempt_1",
        "artifact_type": EvidenceArtifactType.TEST_OUTPUT,
        "media_type": "text/plain",
        "size_bytes": 1234,
        "sha256": DIGEST,
        "producer": make_producer(ProducerComponent.QA_RUNTIME),
        "stage": "test.execution",
        "source_revision": "abc1234",
        "policy_digest": DIGEST_2,
        "classification": EvidenceClassification.EXECUTION_EVIDENCE,
        "retention_policy_id": "retention_standard",
        "validation_state": ValidationState.RECEIVED,
        "object_ref": "s3://artifacts/org_1/run_1/art_1",
        "created_at": utc_now_ms(),
    }
    values.update(overrides)
    return EvidenceArtifactV1(**values)  # type: ignore[arg-type]


class TestEvidence:
    def test_manifest_accepts_scoped_artifacts(self) -> None:
        manifest = EvidenceManifestV1(
            manifest_id="manifest_1",
            organization_id="org_1",
            project_id="prj_1",
            run_id="run_1",
            attempt_id="attempt_1",
            created_at=utc_now_ms(),
            artifacts=(make_artifact(), make_artifact("art_2")),
            ledger_chain_version=2,
            ledger_root=DIGEST,
            events_count=10,
        )
        assert manifest.digest().startswith("sha256:")

    def test_cross_run_reference_rejected(self) -> None:
        with pytest.raises(EvidenceScopeError):
            EvidenceManifestV1(
                manifest_id="manifest_1",
                organization_id="org_1",
                project_id="prj_1",
                run_id="run_1",
                attempt_id="attempt_1",
                created_at=utc_now_ms(),
                artifacts=(make_artifact(run_id="run_other"),),
                ledger_chain_version=2,
                ledger_root=DIGEST,
                events_count=10,
            )

    def test_cross_tenant_reference_rejected(self) -> None:
        with pytest.raises(EvidenceScopeError):
            EvidenceManifestV1(
                manifest_id="manifest_1",
                organization_id="org_1",
                project_id="prj_1",
                run_id="run_1",
                attempt_id="attempt_1",
                created_at=utc_now_ms(),
                artifacts=(make_artifact(organization_id="org_other"),),
                ledger_chain_version=2,
                ledger_root=DIGEST,
                events_count=10,
            )

    def test_duplicate_artifact_ids_rejected(self) -> None:
        with pytest.raises(EvidenceScopeError):
            EvidenceManifestV1(
                manifest_id="manifest_1",
                organization_id="org_1",
                project_id="prj_1",
                run_id="run_1",
                attempt_id="attempt_1",
                created_at=utc_now_ms(),
                artifacts=(make_artifact(), make_artifact()),
                ledger_chain_version=2,
                ledger_root=DIGEST,
                events_count=10,
            )

    def test_manifest_digest_is_stable(self) -> None:
        manifest = EvidenceManifestV1(
            manifest_id="manifest_1",
            organization_id="org_1",
            project_id="prj_1",
            run_id="run_1",
            attempt_id="attempt_1",
            created_at=utc_now_ms(),
            artifacts=(make_artifact(),),
            ledger_chain_version=2,
            ledger_root=DIGEST,
            events_count=10,
        )
        assert manifest.digest() == manifest.digest()
