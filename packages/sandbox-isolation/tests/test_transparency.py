"""Transparency-log tests (SOC 2 CC6.8/CC7.2).

The load-bearing property: any history mutation (edit, delete, reorder)
must flip every later checkpoint root, and an inclusion proof must verify
ONLY against the true root of the tree that actually contains the leaf.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sandbox_isolation.transparency import (
    LocalTransparencyLog,
    merkle_root,
    receipt_fingerprint,
    verify_inclusion,
)


def _log(tmp_path, leaves):
    log = LocalTransparencyLog(tmp_path / "receipts.log")
    for leaf in leaves:
        log.append(leaf)
    return log


LEAVES = [f"{i:064x}" for i in range(1, 9)]  # 8 deterministic 32-byte hex leaves


class TestMerkleMath:
    def test_empty_and_single_roots(self):
        from hashlib import sha256
        assert merkle_root([]) == sha256(b"").digest()
        single = merkle_root(LEAVES[:1])
        assert single == sha256(b"\x00" + bytes.fromhex(LEAVES[0])).digest()

    def test_root_changes_with_membership(self):
        base = merkle_root(LEAVES[:4]).hex()
        assert merkle_root(LEAVES[:5]).hex() != base
        tampered = list(LEAVES[:4])
        tampered[2] = "ff" * 32
        assert merkle_root(tampered).hex() != base

    def test_order_matters(self):
        swapped = [LEAVES[1], LEAVES[0]] + LEAVES[2:4]
        assert merkle_root(swapped).hex() != merkle_root(LEAVES[:4]).hex()


class TestInclusionProofs:
    @pytest.mark.parametrize("count", [1, 2, 3, 4, 5, 8])
    def test_every_leaf_proves_against_current_root(self, tmp_path, count):
        log = _log(tmp_path, LEAVES[:count])
        root = log.checkpoint_root()
        for leaf in LEAVES[:count]:
            proof = log.proof_inclusion(leaf)
            assert proof is not None
            assert verify_inclusion(
                leaf, proof["leaf_index"], proof["tree_size"], proof["proof"], proof["root"]
            ), f"leaf {leaf[:8]} failed to verify at size {count}"
            assert proof["root"] == root

    def test_proof_fails_for_absent_leaf(self, tmp_path):
        log = _log(tmp_path, LEAVES[:4])
        assert log.proof_inclusion("ab" * 32) is None

    def test_proof_fails_against_wrong_root(self, tmp_path):
        log = _log(tmp_path, LEAVES[:4])
        proof = log.proof_inclusion(LEAVES[0])
        other_root = merkle_root(LEAVES[:5]).hex()
        assert not verify_inclusion(
            LEAVES[0], proof["leaf_index"], proof["tree_size"], proof["proof"], other_root
        )

    def test_proof_fails_at_wrong_index(self, tmp_path):
        log = _log(tmp_path, LEAVES[:8])
        proof = log.proof_inclusion(LEAVES[3])
        assert not verify_inclusion(
            LEAVES[3], 0, proof["tree_size"], proof["proof"], proof["root"]
        )

    def test_truncated_or_extended_proof_rejected(self, tmp_path):
        log = _log(tmp_path, LEAVES[:8])
        proof = log.proof_inclusion(LEAVES[5])
        p = proof["proof"]
        assert not verify_inclusion(LEAVES[5], 5, 8, p[:-1], proof["root"])
        assert not verify_inclusion(LEAVES[5], 5, 8, p + ["00" * 32], proof["root"])


class TestAppendOnlyStore:
    def test_persistence_reload_consistent(self, tmp_path):
        log = _log(tmp_path, LEAVES[:5])
        root_before = log.checkpoint_root()
        reopened = LocalTransparencyLog(tmp_path / "receipts.log")
        assert reopened.tree_size == 5
        assert reopened.checkpoint_root() == root_before

    def test_tampered_history_fails_closed_on_load(self, tmp_path):
        _log(tmp_path, LEAVES[:4])
        lines = (tmp_path / "receipts.log").read_text().splitlines()
        record = json.loads(lines[-1])
        record["leaf_sha256"] = "ee" * 32  # rewrite history
        lines[-1] = json.dumps(record, sort_keys=True)
        (tmp_path / "receipts.log").write_text("\n".join(lines) + "\n")
        with pytest.raises(ValueError, match="integrity"):
            LocalTransparencyLog(tmp_path / "receipts.log")

    def test_records_carry_monotonic_checkpoints(self, tmp_path):
        log = _log(tmp_path, LEAVES[:3])
        lines = [json.loads(l) for l in (tmp_path / "receipts.log").read_text().splitlines()]
        assert [r["tree_size"] for r in lines] == [1, 2, 3]
        assert len({r["root_sha256"] for r in lines}) == 3  # every root distinct


class TestVerifierClaim8:
    """Claim #8 in the outside verifier: transparency inclusion proof."""

    def _receipt_and_key(self, tmp_path):
        from datetime import datetime, UTC
        from cryptography.hazmat.primitives import serialization
        from sandbox_isolation import generate_keypair
        from workflo_schema.sandbox import (
            CanaryCheckResult, RunReport, SandboxLifecycleEvent,
            SignedReceipt, TeardownProof,
        )

        receipt = SignedReceipt(
            sandbox_id="claim8", issued_at=datetime.now(UTC),
            run_report=RunReport(sandbox_id="claim8", total=1, passed=1,
                                 failed=0, duration_seconds=0.1),
            teardown_proof=TeardownProof(
                sandbox_id="claim8", container_id="c", container_removed=True,
                filesystem_removed=True, no_snapshot_retained=True,
                destroyed_at=datetime.now(UTC)),
            canary_check=CanaryCheckResult(
                sandbox_id="claim8", attempted_at=datetime.now(UTC),
                target_host="https://example.com", request_succeeded=False,
                error="blocked"),
        )
        receipt.lifecycle_events = [
            SandboxLifecycleEvent(sandbox_id="claim8", event=e,
                                  timestamp=datetime.now(UTC))
            for e in ("created", "destroyed", "receipt_signed")
        ]
        signer = generate_keypair()
        signer.sign(receipt)
        rpath = tmp_path / "receipt.json"
        rpath.write_text(receipt.model_dump_json())
        pub = tmp_path / "pub.pem"
        pub.write_bytes(signer.public_key.public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo))
        return receipt, rpath, pub

    def test_proof_present_and_valid_is_VALID(self, tmp_path):
        from sandbox_isolation.verify_receipts import VerifyStatus, verify_receipt

        receipt, rpath, pub = self._receipt_and_key(tmp_path)
        log = LocalTransparencyLog(tmp_path / "t.log")
        leaf = receipt_fingerprint(receipt.canonical_payload())
        log.append(leaf)
        proof = log.proof_inclusion(leaf)
        ppath = tmp_path / "proof.json"
        ppath.write_text(json.dumps(proof))

        result = verify_receipt(str(rpath), pubkey_path=str(pub),
                                transparency_proof=str(ppath))
        assert result.status == VerifyStatus.VALID, result.checks_failed
        assert any("Claim #8" in c and "verifies" in c
                   for c in result.checks_passed)

    def test_valid_receipt_with_FOREIGN_proof_is_INVALID(self, tmp_path):
        from sandbox_isolation.verify_receipts import VerifyStatus, verify_receipt

        receipt, rpath, pub = self._receipt_and_key(tmp_path)
        other = receipt.model_copy(deep=True)
        other.run_report.total += 1
        log = LocalTransparencyLog(tmp_path / "t2.log")
        leaf = receipt_fingerprint(other.canonical_payload())
        log.append(leaf)
        proof = log.proof_inclusion(leaf)
        ppath = tmp_path / "foreign_proof.json"
        ppath.write_text(json.dumps(proof))

        result = verify_receipt(str(rpath), pubkey_path=str(pub),
                                transparency_proof=str(ppath))
        assert result.status == VerifyStatus.INVALID
        assert any("does NOT fold" in c for c in result.checks_failed)

    def test_required_but_missing_is_INCOMPLETE(self, tmp_path):
        from sandbox_isolation.verify_receipts import VerifyStatus, verify_receipt

        _receipt, rpath, pub = self._receipt_and_key(tmp_path)
        result = verify_receipt(str(rpath), pubkey_path=str(pub),
                                require_transparency=True)
        assert result.status == VerifyStatus.INCOMPLETE
        assert any("transparency proof missing" in c
                   for c in result.checks_failed)


class TestReceiptBinding:
    def test_fingerprint_is_canonical_payload_sha256(self):
        from hashlib import sha256
        payload = '{"canonical": true}'
        assert receipt_fingerprint(payload) == sha256(payload.encode()).hexdigest()

    def test_signed_receipt_round_trip(self, tmp_path):
        """End-to-end: sign a receipt, log its canonical fingerprint, prove
        inclusion, and verify the proof offline from just the receipt."""
        from datetime import datetime, UTC
        from sandbox_isolation import generate_keypair
        from workflo_schema.sandbox import (
            CanaryCheckResult, RunReport, SignedReceipt, TeardownProof,
        )

        receipt = SignedReceipt(
            sandbox_id="tl-test",
            issued_at=datetime.now(UTC),
            run_report=RunReport(sandbox_id="tl-test", total=1, passed=1,
                                 failed=0, duration_seconds=0.1),
            teardown_proof=TeardownProof(
                sandbox_id="tl-test", container_id="c", container_removed=True,
                filesystem_removed=True, no_snapshot_retained=True,
                destroyed_at=datetime.now(UTC)),
            canary_check=CanaryCheckResult(
                sandbox_id="tl-test", attempted_at=datetime.now(UTC),
                target_host="https://example.com", request_succeeded=False,
                error="blocked"),
        )
        signer = generate_keypair()
        signer.sign(receipt)

        log = LocalTransparencyLog(tmp_path / "r.log")
        leaf = receipt_fingerprint(receipt.canonical_payload())
        log.append(leaf)
        proof = log.proof_inclusion(leaf)
        assert proof is not None
        # Offline verifier: recompute leaf from the receipt, verify proof
        assert verify_inclusion(
            receipt_fingerprint(receipt.canonical_payload()),
            proof["leaf_index"], proof["tree_size"], proof["proof"], proof["root"],
        )
