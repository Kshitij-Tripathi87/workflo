"""Receipt attack suite (R-1..R-17, spec §11.1) — the authoritative
verifier matrix.

Runs every mutation class against one golden signed receipt + real
evidence bundle and asserts the DISTINCT verifier state (F-7):
VALID / INVALID / UNSUPPORTED_VERSION / CORRUPT / INCOMPLETE.
"""

from __future__ import annotations

import json
from datetime import datetime, UTC
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization

from sandbox_isolation import generate_keypair
from sandbox_isolation.verify_receipts import VerifyStatus, verify_receipt
from workflo_schema.sandbox import (
    CanaryCheckResult,
    RunReport,
    SandboxLifecycleEvent,
    SignedReceipt,
    TeardownProof,
)


def _build_evidence(tmp_path: Path, sandbox_id: str) -> Path:
    from sandbox_runtime.evidence import EvidenceCollector

    evidence_dir = tmp_path / "runs" / sandbox_id / "evidence"
    collector = EvidenceCollector(evidence_dir)
    collector.write_event("created", {"sandbox_id": sandbox_id})
    collector.write_event("tests_completed", {"total": 3, "passed": 3})
    collector.write_event("destroyed", {"teardown_verified": True})
    collector.write_artifact("test_stdout.txt", b"3 passed")
    collector.finalize([], sandbox_id, sandbox_id)
    return evidence_dir


def _golden_receipt(sandbox_id: str, evidence_dir: Path) -> SignedReceipt:
    from sandbox_runtime.evidence import EvidenceCollector
    from workflo_schema.sandbox import LandlockAttestation, SecurityAttestation

    collector = EvidenceCollector(evidence_dir)
    binding = collector.build_binding()
    return SignedReceipt(
        sandbox_id=sandbox_id,
        receipt_version=4,
        issued_at=datetime.now(UTC),
        run_report=RunReport(sandbox_id=sandbox_id, total=3, passed=3, failed=0),
        teardown_proof=TeardownProof(
            sandbox_id=sandbox_id,
            runtime_type="namespaces",
            destroyed_at=datetime.now(UTC),
            processes_terminated=True,
            cgroup_removed=True,
            network_namespace_removed=True,
            workspace_removed=True,
            container_removed=True,
            filesystem_removed=True,
            no_snapshot_retained=True,
        ),
        canary_check=CanaryCheckResult(
            sandbox_id=sandbox_id,
            attempted_at=datetime.now(UTC),
            target_host="8.8.8.8:53",
            request_succeeded=False,
            error="blocked",
        ),
        lifecycle_events=[
            SandboxLifecycleEvent(sandbox_id=sandbox_id, event="created",
                                  timestamp=datetime.now(UTC)),
            SandboxLifecycleEvent(sandbox_id=sandbox_id, event="destroyed",
                                  timestamp=datetime.now(UTC)),
            SandboxLifecycleEvent(sandbox_id=sandbox_id, event="receipt_signed",
                                  timestamp=datetime.now(UTC)),
        ],
        evidence_binding=binding,
        security_attestation=SecurityAttestation(
            security_mode="compatible",
            landlock=LandlockAttestation(requested=True, applied=True,
                                         abi_version=3),
        ),
    )


def _write_receipt(tmp_path: Path, receipt_dict: dict, name="receipt.json") -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(receipt_dict, default=str))
    return p


def _pubkey_file(tmp_path: Path, signer) -> str:
    f = tmp_path / "public.pem"
    f.write_bytes(signer.public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ))
    return str(f)


@pytest.fixture()
def golden(tmp_path):
    """A signed golden receipt + real evidence bundle + pubkey."""
    sandbox_id = "sbx-attack"
    evidence_dir = _build_evidence(tmp_path, sandbox_id)
    receipt = _golden_receipt(sandbox_id, evidence_dir)
    signer = generate_keypair()
    signer.sign(receipt)
    receipt_dict = json.loads(receipt.model_dump_json())
    return {
        "receipt": receipt, "signer": signer, "dict": receipt_dict,
        "evidence": evidence_dir,
        "pubkey": _pubkey_file(tmp_path, signer),
        "tmp": tmp_path,
    }


def _verify(golden, mutated_dict, pubkey: str | None = None):
    path = _write_receipt(golden["tmp"], mutated_dict, name="mutated.json")
    return verify_receipt(
        str(path), pubkey_path=pubkey,
        evidence_dir=str(golden["evidence"]),
    )


class TestFieldMutations:
    def test_r1_field_mutation_invalid(self, golden):
        mutated = dict(golden["dict"])
        mutated["run_report"] = dict(mutated["run_report"], passed=999)
        assert _verify(golden, mutated, pubkey=golden["pubkey"]).status == VerifyStatus.INVALID

    def test_r2a_delete_required_field_corrupt(self, golden):
        mutated = dict(golden["dict"])
        del mutated["sandbox_id"]
        assert _verify(golden, mutated, pubkey=golden["pubkey"]).status == VerifyStatus.CORRUPT

    def test_r2b_optional_field_deletion_at_default_is_valid(self, golden):
        """Deleting an optional field that was ALREADY AT ITS DEFAULT
        does not change the canonical bytes — VALID (not tampering).
        This is the intended behavior: only non-default field deletion
        is detectable as tampering."""
        mutated = dict(golden["dict"])
        del mutated["datahub_writeback"]
        assert _verify(golden, mutated, pubkey=golden["pubkey"]).status == VerifyStatus.VALID

    def test_r4_field_reordering_is_neutralized(self, golden):
        """Canonical JSON is sort_keys — reordering cannot forge."""
        reordered = {k: golden["dict"][k]
                     for k in reversed(list(golden["dict"].keys()))}
        assert _verify(golden, reordered, pubkey=golden["pubkey"]).status == VerifyStatus.VALID

    def test_r5_type_mutation_invalid(self, golden):
        """Type mutation of a CANONICAL field: bool ← string 'true' flips
        the default False → True, changing the signed bytes."""
        mutated = dict(golden["dict"])
        mutated["dependency_install_had_network"] = "true"
        assert _verify(golden, mutated, pubkey=golden["pubkey"]).status == VerifyStatus.INVALID

    def test_r6_integer_overflow_invalid(self, golden):
        mutated = dict(golden["dict"])
        mutated["run_report"] = dict(mutated["run_report"], passed=2**63)
        assert _verify(golden, mutated, pubkey=golden["pubkey"]).status == VerifyStatus.INVALID

    def test_r7_timestamp_mutation_invalid(self, golden):
        mutated = dict(golden["dict"])
        mutated["issued_at"] = "2001-01-01T00:00:00Z"
        assert _verify(golden, mutated, pubkey=golden["pubkey"]).status == VerifyStatus.INVALID


class TestSignatureAttacks:
    def test_r8_digest_substitution_invalid(self, golden):
        mutated = dict(golden["dict"])
        mutated["evidence_binding"] = dict(
            mutated["evidence_binding"], bundle_sha256="f" * 64)
        assert _verify(golden, mutated, pubkey=golden["pubkey"]).status == VerifyStatus.INVALID

    def test_r9_signature_substitution_invalid(self, golden):
        """A valid signature from a DIFFERENT key must not verify."""
        other = generate_keypair()
        receipt = SignedReceipt(**golden["dict"])
        other.sign(receipt)
        assert _verify(golden, json.loads(receipt.model_dump_json()), pubkey=golden["pubkey"]).status \
            == VerifyStatus.INVALID

    def test_signature_deletion_invalid(self, golden):
        mutated = dict(golden["dict"])
        mutated["signature"] = None
        assert _verify(golden, mutated, pubkey=golden["pubkey"]).status == VerifyStatus.INVALID


class TestVersionConfusion:
    @pytest.mark.parametrize("version", [5, 0, -1, 99])
    def test_r10_unsupported_versions(self, golden, version):
        mutated = dict(golden["dict"])
        mutated["receipt_version"] = version
        assert _verify(golden, mutated, pubkey=golden["pubkey"]).status == VerifyStatus.UNSUPPORTED_VERSION

    def test_r11_legacy_v1_still_verifies(self, golden):
        """v1 byte-compat is a protected invariant (spec §11.1 R-11)."""
        receipt = SignedReceipt(
            sandbox_id="sbx-legacy",
            issued_at=datetime.now(UTC),
            run_report=RunReport(sandbox_id="sbx-legacy"),
            teardown_proof=TeardownProof(
                sandbox_id="sbx-legacy", destroyed_at=datetime.now(UTC),
                container_removed=True, filesystem_removed=True,
                no_snapshot_retained=True),
            canary_check=CanaryCheckResult(
                sandbox_id="sbx-legacy", attempted_at=datetime.now(UTC),
                request_succeeded=False),
            lifecycle_events=[
                SandboxLifecycleEvent(sandbox_id="sbx-legacy", event="created",
                                      timestamp=datetime.now(UTC)),
                SandboxLifecycleEvent(sandbox_id="sbx-legacy", event="destroyed",
                                      timestamp=datetime.now(UTC)),
                SandboxLifecycleEvent(sandbox_id="sbx-legacy", event="signed",
                                      timestamp=datetime.now(UTC)),
            ],
        )
        golden["signer"].sign(receipt)  # same trusted key
        path = _write_receipt(golden["tmp"],
                              json.loads(receipt.model_dump_json()),
                              name="legacy.json")
        result = verify_receipt(str(path), pubkey_path=golden["pubkey"])
        assert result.status == VerifyStatus.VALID


class TestStructuralAttacks:
    def test_r12_unknown_field_ignored_not_signed(self, golden):
        """Extra fields are ignored by the schema and are NOT part of the
        canonical payload — insertion cannot forge a signature. Strict
        rejection is deferred to a versioned schema change (spec §11.1)."""
        mutated = dict(golden["dict"])
        mutated["injected_backdoor_field"] = {"evil": True}
        assert _verify(golden, mutated, pubkey=golden["pubkey"]).status == VerifyStatus.VALID

    def test_r13a_invalid_utf8_corrupt(self, golden):
        p = golden["tmp"] / "bad-utf8.json"
        p.write_bytes(b'{"receipt": {"sandbox_id": "\xff\xfe"}}')
        result = verify_receipt(str(p), pubkey_path=golden["pubkey"])
        assert result.status == VerifyStatus.CORRUPT

    def test_r13b_nul_bytes_corrupt(self, golden):
        p = golden["tmp"] / "nul.json"
        p.write_bytes(b'{"receipt": {"sandbox_id": "a\x00b"}}')
        result = verify_receipt(str(p), pubkey_path=golden["pubkey"])
        assert result.status == VerifyStatus.CORRUPT

    def test_r13c_bom_corrupt(self, golden):
        p = golden["tmp"] / "bom.json"
        p.write_bytes(b'\xef\xbb\xbf{"receipt": {}}')
        result = verify_receipt(str(p), pubkey_path=golden["pubkey"])
        assert result.status == VerifyStatus.CORRUPT

    def test_r14a_truncated_receipt_corrupt(self, golden):
        p = golden["tmp"] / "truncated.json"
        raw = json.dumps({"receipt": golden["dict"]}, default=str)
        p.write_text(raw[: len(raw) // 2])
        result = verify_receipt(str(p), pubkey_path=golden["pubkey"])
        assert result.status == VerifyStatus.CORRUPT

    def test_r15_event_reorder_invalid(self, golden):
        events = golden["evidence"] / "events.jsonl"
        lines = events.read_text().splitlines()
        lines[0], lines[1] = lines[1], lines[0]
        events.write_text("\n".join(lines) + "\n")
        result = verify_receipt(
            str(_write_receipt(golden["tmp"], golden["dict"], name="r15.json")),
            pubkey_path=golden["pubkey"],
            evidence_dir=str(golden["evidence"]),
        )
        assert result.status == VerifyStatus.INVALID

    def test_r16_event_deletion_invalid(self, golden):
        events = golden["evidence"] / "events.jsonl"
        lines = events.read_text().splitlines()
        events.write_text("\n".join(lines[:-1]) + "\n")
        result = verify_receipt(
            str(_write_receipt(golden["tmp"], golden["dict"], name="r16.json")),
            pubkey_path=golden["pubkey"],
            evidence_dir=str(golden["evidence"]),
        )
        assert result.status == VerifyStatus.INVALID

    def test_r17_empty_ledger_incomplete(self, golden):
        """A signed receipt with a thin audit trail proves nothing —
        INCOMPLETE, surfaced rather than hidden (spec §11.1 R-17)."""
        receipt = SignedReceipt(
            sandbox_id="sbx-thin",
            issued_at=datetime.now(UTC),
            run_report=RunReport(sandbox_id="sbx-thin"),
            teardown_proof=TeardownProof(
                sandbox_id="sbx-thin", destroyed_at=datetime.now(UTC),
                container_removed=True, filesystem_removed=True,
                no_snapshot_retained=True),
            canary_check=CanaryCheckResult(
                sandbox_id="sbx-thin", attempted_at=datetime.now(UTC),
                request_succeeded=False),
            lifecycle_events=[],  # no audit trail at all
        )
        golden["signer"].sign(receipt)
        path = _write_receipt(golden["tmp"],
                              json.loads(receipt.model_dump_json()),
                              name="thin.json")
        result = verify_receipt(str(path), pubkey_path=golden["pubkey"])
        assert result.status == VerifyStatus.INCOMPLETE


class TestProofObligationStates:
    def test_no_pubkey_incomplete(self, golden):
        result = _verify(golden, golden["dict"], pubkey=None)
        assert result.status == VerifyStatus.INCOMPLETE

    def test_missing_evidence_bundle_incomplete(self, golden, tmp_path):
        result = verify_receipt(
            str(_write_receipt(tmp_path, golden["dict"], name="noev.json")),
            pubkey_path=golden["pubkey"],
            evidence_dir=str(tmp_path / "missing-evidence"),
        )
        assert result.status == VerifyStatus.INCOMPLETE
