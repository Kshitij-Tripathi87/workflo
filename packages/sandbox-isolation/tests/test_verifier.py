"""Tests for the outside-verifier script — the thing that checks claims without trusting workflo."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives import serialization

from sandbox_isolation import generate_keypair
from sandbox_isolation.verify_receipts import verify_receipt_file
from workflo_schema.sandbox import (
    CanaryCheckResult,
    RunReport,
    SandboxLifecycleEvent,
    SignedReceipt,
    TeardownProof,
)


def _make_signed_receipt(*, canary_succeeded=False, container_removed=True, fs_removed=True, tampered=False):
    """Build a valid signed receipt that can be tampered in specific ways."""
    signer = generate_keypair()

    receipt = SignedReceipt(
        sandbox_id="verifier-test-001",
        issued_at=datetime.utcnow(),
        run_report=RunReport(
            sandbox_id="verifier-test-001",
            total=5,
            passed=5,
            failed=0,
            duration_seconds=2.5,
            soc2_controls_covered=["CC6.1", "CC6.6"],
            findings=[],
        ),
        teardown_proof=TeardownProof(
            sandbox_id="verifier-test-001",
            container_id="fake-container-id",
            container_removed=container_removed,
            filesystem_removed=fs_removed,
            no_snapshot_retained=True,
            destroyed_at=datetime.utcnow(),
        ),
        canary_check=CanaryCheckResult(
            sandbox_id="verifier-test-001",
            attempted_at=datetime.utcnow(),
            target_host="https://example.com",
            request_succeeded=canary_succeeded,
            error=None if canary_succeeded else "blocked",
        ),
        lifecycle_events=[
            SandboxLifecycleEvent(
                sandbox_id="verifier-test-001",
                event="created",
                timestamp=datetime.utcnow(),
            ),
            SandboxLifecycleEvent(
                sandbox_id="verifier-test-001",
                event="destroyed",
                timestamp=datetime.utcnow(),
            ),
            SandboxLifecycleEvent(
                sandbox_id="verifier-test-001",
                event="receipt_signed",
                timestamp=datetime.utcnow(),
            ),
        ],
    )

    signer.sign(receipt)

    if tampered:
        receipt.run_report.passed = 999

    return receipt, signer


class TestVerifyReceipts:
    def test_valid_receipt_passes_all_checks(self, tmp_path):
        receipt, signer = _make_signed_receipt()
        receipt_file = tmp_path / "receipt.json"
        receipt_file.write_text(json.dumps({"receipt": receipt.model_dump(mode="json")}, default=str))

        pubkey_file = tmp_path / "public.pem"
        pubkey_bytes = signer.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        pubkey_file.write_bytes(pubkey_bytes)

        rc = verify_receipt_file(str(receipt_file), pubkey_path=str(pubkey_file))
        assert rc == 0

    def test_tampered_receipt_fails(self, tmp_path):
        from cryptography.hazmat.primitives import serialization

        receipt, signer = _make_signed_receipt(tampered=True)
        receipt_file = tmp_path / "receipt.json"
        receipt_file.write_text(json.dumps({"receipt": receipt.model_dump(mode="json")}, default=str))

        pubkey_file = tmp_path / "public.pem"
        pubkey_bytes = signer.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        pubkey_file.write_bytes(pubkey_bytes)

        rc = verify_receipt_file(str(receipt_file), pubkey_path=str(pubkey_file))
        assert rc == 1

    def test_canary_success_fails(self, tmp_path):
        from cryptography.hazmat.primitives import serialization

        receipt, signer = _make_signed_receipt(canary_succeeded=True)
        receipt_file = tmp_path / "receipt.json"
        receipt_file.write_text(json.dumps({"receipt": receipt.model_dump(mode="json")}, default=str))

        pubkey_file = tmp_path / "public.pem"
        pubkey_bytes = signer.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        pubkey_file.write_bytes(pubkey_bytes)

        rc = verify_receipt_file(str(receipt_file), pubkey_path=str(pubkey_file))
        assert rc == 1

    def test_container_not_removed_fails(self, tmp_path):
        from cryptography.hazmat.primitives import serialization

        receipt, signer = _make_signed_receipt(container_removed=False)
        receipt_file = tmp_path / "receipt.json"
        receipt_file.write_text(json.dumps({"receipt": receipt.model_dump(mode="json")}, default=str))

        pubkey_file = tmp_path / "public.pem"
        pubkey_bytes = signer.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        pubkey_file.write_bytes(pubkey_bytes)

        rc = verify_receipt_file(str(receipt_file), pubkey_path=str(pubkey_file))
        assert rc == 1

    def test_no_pubkey_flagged_as_incomplete(self, tmp_path):
        receipt, signer = _make_signed_receipt()
        receipt_file = tmp_path / "receipt.json"
        receipt_file.write_text(json.dumps({"receipt": receipt.model_dump(mode="json")}, default=str))

        rc = verify_receipt_file(str(receipt_file), pubkey_path=None)
        assert rc == 1
