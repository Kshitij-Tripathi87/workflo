"""Receipt protocol versioning — the deliberate compatibility boundary."""

import json
from datetime import datetime, UTC

import pytest

from workflo_schema.sandbox import (
    SUPPORTED_RECEIPT_VERSIONS,
    CURRENT_RECEIPT_VERSION,
    EvidenceBinding,
    RunReport,
    SignedReceipt,
    TeardownProof,
    CanaryCheckResult,
)


def _binding():
    return EvidenceBinding(
        evidence_dir="/runs/sbx/evidence",
        events_count=2,
        events_sha256="a" * 64,
        bundle_sha256="b" * 64,
        manifest_sha256="c" * 64,
    )


def _receipt(**overrides) -> SignedReceipt:
    fields = dict(
        sandbox_id="sbx-v",
        issued_at=datetime.now(UTC),
        run_report=RunReport(sandbox_id="sbx-v"),
        teardown_proof=TeardownProof(
            sandbox_id="sbx-v", destroyed_at=datetime.now(UTC)
        ),
        canary_check=CanaryCheckResult(
            sandbox_id="sbx-v",
            attempted_at=datetime.now(UTC),
            request_succeeded=False,
        ),
    )
    fields.update(overrides)
    return SignedReceipt(**fields)


class TestVersionInference:
    def test_legacy_receipt_infers_v1(self):
        """No receipt_version, no evidence binding -> v1 (legacy Docker)."""
        receipt = _receipt()
        assert receipt.receipt_version == 1

    def test_binding_without_version_infers_v2(self):
        """Evidence binding present, no explicit version -> v2 (interim
        dev receipts from before the field existed)."""
        receipt = _receipt(evidence_binding=_binding())
        assert receipt.receipt_version == 2

    def test_explicit_version_wins(self):
        receipt = _receipt(receipt_version=1, evidence_binding=_binding())
        assert receipt.receipt_version == 1

    def test_unsupported_version_rejected(self):
        with pytest.raises(ValueError, match="UNSUPPORTED_RECEIPT_VERSION"):
            _receipt(receipt_version=99)

    def test_current_version_is_4(self):
        assert CURRENT_RECEIPT_VERSION == 4
        assert 4 in SUPPORTED_RECEIPT_VERSIONS
        assert 3 in SUPPORTED_RECEIPT_VERSIONS
        assert 2 in SUPPORTED_RECEIPT_VERSIONS


class TestCanonicalPayloadVersioning:
    def test_v1_canonical_excludes_version(self):
        """v1 canonical bytes are EXACTLY the legacy format — receipts
        signed by old code keep verifying against new code."""
        receipt = _receipt()
        payload = json.loads(receipt.canonical_payload())

        assert "receipt_version" not in payload
        assert "evidence_binding" in payload  # always present, None for v1

    def test_v2_canonical_includes_version(self):
        receipt = _receipt(receipt_version=2, evidence_binding=_binding())
        payload = json.loads(receipt.canonical_payload())

        assert payload["receipt_version"] == 2
        assert payload["evidence_binding"]["bundle_sha256"] == "b" * 64

    def test_v2_canonical_excludes_agent_activity(self):
        """v2 canonical bytes predate agent_activity — receipts signed by
        the v2 protocol keep verifying against v3 verifiers."""
        receipt = _receipt(receipt_version=2, evidence_binding=_binding())
        payload = json.loads(receipt.canonical_payload())

        assert "agent_activity" not in payload

    def test_v3_canonical_includes_agent_activity(self):
        from workflo_schema.sandbox import AgentActivity

        activity = AgentActivity(tool_calls=5, denied_attempts=1)
        receipt = _receipt(receipt_version=3, evidence_binding=_binding(),
                           agent_activity=activity)
        payload = json.loads(receipt.canonical_payload())

        assert payload["receipt_version"] == 3
        assert payload["agent_activity"]["tool_calls"] == 5
        assert payload["agent_activity"]["denied_attempts"] == 1

    def test_v3_canonical_includes_agent_activity_none(self):
        """v3 receipts without an agent tier canonicalize deterministically
        with agent_activity=None."""
        receipt = _receipt(receipt_version=3, evidence_binding=_binding())
        payload = json.loads(receipt.canonical_payload())

        assert payload["agent_activity"] is None

    def test_v3_signature_covers_agent_activity(self):
        """The signature covers agent_activity for v3 — a receipt whose
        agent summary is altered must break signature verification."""
        from workflo_schema.sandbox import AgentActivity
        from sandbox_isolation import generate_keypair

        signer = generate_keypair()
        receipt = _receipt(receipt_version=3, evidence_binding=_binding(),
                           agent_activity=AgentActivity(tool_calls=5))
        signer.sign(receipt)
        assert signer.verify(receipt)

        # Tamper the agent activity AFTER signing
        receipt.agent_activity.tool_calls = 999
        assert not signer.verify(receipt)

    def test_roundtrip_through_json(self):
        """receipt_version serializes and re-parses identically."""
        receipt = _receipt(receipt_version=2, evidence_binding=_binding())
        parsed = SignedReceipt(**json.loads(receipt.model_dump_json()))
        assert parsed.receipt_version == 2
        assert parsed.canonical_payload() == receipt.canonical_payload()

    def test_signature_covers_version(self):
        """The signature covers receipt_version for v2 — a receipt whose
        version is altered must break signature verification."""
        from sandbox_isolation import generate_keypair

        signer = generate_keypair()
        receipt = _receipt(receipt_version=2, evidence_binding=_binding())
        signer.sign(receipt)
        assert signer.verify(receipt)

        # Tamper the version AFTER signing
        receipt.receipt_version = 1
        assert not signer.verify(receipt)


class TestInferenceProvenanceVersioning:
    """v4 = hosted-inference receipts: provenance inside agent_activity."""

    def _provenance(self):
        from workflo_schema.sandbox import InferenceProvenance
        return InferenceProvenance(
            mode="gateway",
            gateway_url="https://gateway.workflo.dev",
            model="qa-model",
            requests=2,
            observations_sent=4,
            source_code_included=False,
            observation_sha256="d" * 64,
            response_sha256="e" * 64,
        )

    def _activity(self, **overrides):
        from workflo_schema.sandbox import AgentActivity
        return AgentActivity(tool_calls=3, **overrides)

    def test_provenance_without_version_infers_v4(self):
        receipt = _receipt(
            evidence_binding=_binding(),
            agent_activity=self._activity(inference_provenance=self._provenance()),
        )
        assert receipt.receipt_version == 4

    def test_v4_canonical_includes_provenance(self):
        receipt = _receipt(
            receipt_version=4,
            evidence_binding=_binding(),
            agent_activity=self._activity(inference_provenance=self._provenance()),
        )
        payload = json.loads(receipt.canonical_payload())

        assert payload["receipt_version"] == 4
        prov = payload["agent_activity"]["inference_provenance"]
        assert prov["mode"] == "gateway"
        assert prov["source_code_included"] is False
        assert prov["observation_sha256"] == "d" * 64

    def test_v4_signature_covers_provenance(self):
        from sandbox_isolation import generate_keypair

        signer = generate_keypair()
        receipt = _receipt(
            receipt_version=4,
            evidence_binding=_binding(),
            agent_activity=self._activity(inference_provenance=self._provenance()),
        )
        signer.sign(receipt)
        assert signer.verify(receipt)

        # Tamper the provenance AFTER signing
        receipt.agent_activity.inference_provenance.observations_sent = 999999
        assert not signer.verify(receipt)

    def test_v3_canonical_strips_provenance(self):
        """A v3 receipt carrying provenance would canonicalize WITHOUT it —
        v3 bytes predate the field, so old receipts keep verifying."""
        receipt = _receipt(
            receipt_version=3,
            evidence_binding=_binding(),
            agent_activity=self._activity(inference_provenance=self._provenance()),
        )
        payload = json.loads(receipt.canonical_payload())

        assert "inference_provenance" not in payload["agent_activity"]

    def test_v4_task_spec_run_has_no_provenance(self):
        """A v4 receipt without a model planner canonicalizes deterministically
        with inference_provenance=None."""
        receipt = _receipt(
            receipt_version=4,
            evidence_binding=_binding(),
            agent_activity=self._activity(),
        )
        payload = json.loads(receipt.canonical_payload())

        assert payload["agent_activity"]["inference_provenance"] is None

    def test_v4_roundtrip_through_json(self):
        receipt = _receipt(
            receipt_version=4,
            evidence_binding=_binding(),
            agent_activity=self._activity(inference_provenance=self._provenance()),
        )
        parsed = SignedReceipt(**json.loads(receipt.model_dump_json()))
        assert parsed.receipt_version == 4
        assert parsed.canonical_payload() == receipt.canonical_payload()


class TestSecurityAttestation:
    """Phase 6: security_attestation is included in the canonical payload
    only when set, so pre-Phase-6 receipts keep verifying byte-for-byte."""

    def test_absent_attestation_excluded_from_canonical(self):
        receipt = _receipt(receipt_version=4, evidence_binding=_binding())
        assert "security_attestation" not in json.loads(receipt.canonical_payload())

    def test_attestation_included_when_set(self):
        from workflo_schema.sandbox import LandlockAttestation, SecurityAttestation

        receipt = _receipt(
            receipt_version=4,
            evidence_binding=_binding(),
            security_attestation=SecurityAttestation(
                security_mode="hardened",
                landlock=LandlockAttestation(
                    requested=True, applied=True, abi_version=3,
                ),
            ),
        )
        payload = json.loads(receipt.canonical_payload())
        att = payload["security_attestation"]
        assert att["security_mode"] == "hardened"
        assert att["landlock"]["applied"] is True
        assert att["landlock"]["abi_version"] == 3
        assert att["source_code_included"] is False

    def test_attestation_is_signed(self):
        from sandbox_isolation import generate_keypair
        from workflo_schema.sandbox import SecurityAttestation

        signer = generate_keypair()
        receipt = _receipt(
            receipt_version=4,
            evidence_binding=_binding(),
            security_attestation=SecurityAttestation(security_mode="hardened"),
        )
        signer.sign(receipt)
        assert signer.verify(receipt)

        # Tamper: adversary downgrades the reported posture
        receipt.security_attestation.security_mode = "compatible"
        assert not signer.verify(receipt)

    def test_old_receipt_roundtrip_unchanged(self):
        """Round-tripping a pre-attestation receipt must not inject the key
        into its canonical bytes."""
        receipt = _receipt(receipt_version=4, evidence_binding=_binding())
        parsed = SignedReceipt(**json.loads(receipt.model_dump_json()))
        assert parsed.canonical_payload() == receipt.canonical_payload()


class TestPhase7RunStatus:
    """run_status / failure_stage (run_contract.md §5) — only when set."""

    def test_absent_status_excluded_from_canonical(self):
        receipt = _receipt(receipt_version=4, evidence_binding=_binding())
        assert "run_status" not in json.loads(receipt.canonical_payload())
        assert "failure_stage" not in json.loads(receipt.canonical_payload())

    def test_failed_run_carries_stage(self):
        receipt = _receipt(
            receipt_version=4, evidence_binding=_binding(),
            run_status="failed", failure_stage="agent")
        payload = json.loads(receipt.canonical_payload())
        assert payload["run_status"] == "failed"
        assert payload["failure_stage"] == "agent"

    def test_failed_run_status_is_signed(self):
        from sandbox_isolation import generate_keypair

        signer = generate_keypair()
        receipt = _receipt(
            receipt_version=4, evidence_binding=_binding(),
            run_status="failed", failure_stage="probes")
        signer.sign(receipt)
        assert signer.verify(receipt)

        # An adversary flipping a failed run to "completed" must not verify
        receipt.run_status = "completed"
        assert not signer.verify(receipt)
