"""Claim #7 tests — signing-key revocation checks in the verifier.

A revoked signing key must void provenance even when the Ed25519 signature
is mathematically valid: key compromise is precisely the case "valid
signature, worthless claim". The directory call itself is faked at the
urllib seam (the verifier stays stdlib-only).
"""

from __future__ import annotations

import io
import json
from datetime import datetime, UTC
from pathlib import Path
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives import serialization

from sandbox_isolation import generate_keypair
from sandbox_isolation.verify_receipts import VerifyStatus, verify_receipt
from sandbox_isolation.key_directory import check_key_status
from workflo_schema.sandbox import (
    CanaryCheckResult,
    RunReport,
    SandboxLifecycleEvent,
    SignedReceipt,
    TeardownProof,
)


def _signed_receipt_with_key(key_id: str | None) -> tuple[SignedReceipt, object]:
    signer = generate_keypair()
    receipt = SignedReceipt(
        sandbox_id="revocation-test",
        issued_at=datetime.now(UTC),
        run_report=RunReport(
            sandbox_id="revocation-test", total=1, passed=1, failed=0,
            duration_seconds=0.1,
        ),
        teardown_proof=TeardownProof(
            sandbox_id="revocation-test", container_id="c1",
            container_removed=True, filesystem_removed=True,
            no_snapshot_retained=True, destroyed_at=datetime.now(UTC),
        ),
        canary_check=CanaryCheckResult(
            sandbox_id="revocation-test", attempted_at=datetime.now(UTC),
            target_host="https://example.com", request_succeeded=False, error="blocked",
        ),
        key_id=key_id,
    )
    # Claim #6 needs findings when failed>0 — failed=0 here, fine.
    receipt.lifecycle_events = [
        SandboxLifecycleEvent(sandbox_id="revocation-test", event=e,
                              timestamp=datetime.now(UTC))
        for e in ("created", "destroyed", "receipt_signed")
    ]
    signer.sign(receipt)
    return receipt, signer


class _FakeResponse:
    def __init__(self, payload: dict, code: int = 200):
        self._payload = payload
        self.status = code

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, n: int = -1) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


def _verify_with_status(tmp_path, key_status: dict, *, key_id="key-1", http_code=200):
    receipt, signer = _signed_receipt_with_key(key_id)
    path = tmp_path / "receipt.json"
    path.write_text(receipt.model_dump_json())
    pub = tmp_path / "pub.pem"
    pub.write_bytes(signer.public_key.public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ))

    def _fake_urlopen(req, timeout=0):
        if http_code != 200:
            import urllib.error
            raise urllib.error.HTTPError(req.full_url, http_code, "nf", {}, None)
        return _FakeResponse(key_status)

    with patch("urllib.request.urlopen", _fake_urlopen):
        return verify_receipt(str(path), pubkey_path=str(pub),
                              key_directory="http://cp.test")


class TestKeyStatusClient:
    def test_active(self):
        with patch("urllib.request.urlopen",
                   lambda req, timeout=0: _FakeResponse({"status": "active"})):
            s = check_key_status("http://cp.test", "k1")
        assert s.is_usable and not s.is_revoked

    def test_revoked(self):
        with patch("urllib.request.urlopen",
                   lambda req, timeout=0: _FakeResponse(
                       {"status": "revoked", "revoked_at": "2026-01-01T00:00:00Z"})):
            s = check_key_status("http://cp.test", "k1")
        assert s.is_revoked

    def test_not_found(self):
        import urllib.error
        with patch("urllib.request.urlopen",
                   lambda req, timeout=0: (_ for _ in ()).throw(
                       urllib.error.HTTPError("u", 404, "nf", {}, None))):
            s = check_key_status("http://cp.test", "k1")
        assert s.status == "not_found"

    def test_unreachable(self):
        import urllib.error
        with patch("urllib.request.urlopen",
                   lambda req, timeout=0: (_ for _ in ()).throw(
                       urllib.error.URLError("down"))):
            s = check_key_status("http://cp.test", "k1")
        assert s.status == "unreachable"


class TestClaim7Classification:
    def test_revoked_key_is_INVALID_even_with_valid_signature(self, tmp_path):
        result = _verify_with_status(tmp_path, {"status": "revoked"})
        assert result.status == VerifyStatus.INVALID
        assert any("key is REVOKED" in c for c in result.checks_failed)
        # Signature still verified — the failure is provenance, not crypto.
        assert any("signature verifies" in c for c in result.checks_passed)

    def test_active_key_passes_claim(self, tmp_path):
        result = _verify_with_status(tmp_path, {"status": "active"})
        assert result.status == VerifyStatus.VALID
        assert any("signing key active" in c for c in result.checks_passed)

    def test_unregistered_key_is_INCOMPLETE(self, tmp_path):
        result = _verify_with_status(tmp_path, {}, http_code=404)
        assert result.status == VerifyStatus.INCOMPLETE
        assert any("not registered in the directory" in c for c in result.checks_failed)

    def test_unreachable_directory_is_INCOMPLETE(self, tmp_path):
        import urllib.error

        receipt, signer = _signed_receipt_with_key("key-1")
        path = tmp_path / "receipt.json"
        path.write_text(receipt.model_dump_json())
        pub = tmp_path / "pub.pem"
        pub.write_bytes(signer.public_key.public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ))
        with patch("urllib.request.urlopen",
                   lambda req, timeout=0: (_ for _ in ()).throw(
                       urllib.error.URLError("down"))):
            result = verify_receipt(str(path), pubkey_path=str(pub),
                                    key_directory="http://cp.test")
        assert result.status == VerifyStatus.INCOMPLETE
        assert any("could not reach key directory" in c for c in result.checks_failed)

    def test_no_key_directory_means_claim_skipped(self, tmp_path):
        """Backwards compatibility: without --key-directory, no Claim #7."""
        receipt, signer = _signed_receipt_with_key("key-1")
        path = tmp_path / "receipt.json"
        path.write_text(receipt.model_dump_json())
        pub = tmp_path / "pub.pem"
        pub.write_bytes(signer.public_key.public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ))
        result = verify_receipt(str(path), pubkey_path=str(pub))
        assert result.status == VerifyStatus.VALID
        assert not any("Claim #7" in c for c in result.checks_passed + result.checks_failed)
