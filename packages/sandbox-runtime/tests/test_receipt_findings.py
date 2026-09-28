"""Day 11 integration — findings, mission, and repo provenance on a signed,
verified receipt (and tamper detection).

This exercises the receipt contract that the 14-day golden run depends on:
the Judged findings, the user's mission, and the pinned repository
provenance all ride INSIDE the signed payload.
"""

from __future__ import annotations

from datetime import datetime, UTC

from sandbox_isolation import generate_keypair, verify_receipt_signature
from workflo_schema.sandbox import SignedReceipt


def _receipt_payload() -> dict:
    return {
        "receipt_version": 4,
        "sandbox_id": "golden-01",
        "issued_at": datetime.now(UTC).isoformat(),
        "run_report": {
            "sandbox_id": "golden-01",
            "run_id": "golden-01",
            "total": 1,
            "passed": 1,
            "failed": 0,
            "skipped": 0,
            "duration_seconds": 1.2,
            "findings": [
                {
                    "finding_id": "wf-fnd-" + "ab" * 8,
                    "title": "POST /checkout fails (HTTP 500)",
                    "severity": "medium",
                    "status": "confirmed",
                    "summary": "POST /checkout failed 2 time(s) as HTTP 500; reproduced",
                    "evidence_refs": ["evt_00000007", "evt_00000011"],
                    "reproduction": {
                        "method": "POST",
                        "url": "http://app.workflo.internal:3000/checkout",
                        "observed_failures": 2,
                        "failure_class": "5xx",
                        "attempt_seqs": [7, 11],
                    },
                }
            ],
        },
        "teardown_proof": {
            "sandbox_id": "golden-01",
            "runtime_type": "namespaces",
            "destroyed_at": datetime.now(UTC).isoformat(),
            "container_removed": True,
            "filesystem_removed": True,
            "no_snapshot_retained": True,
            "session_duration_seconds": 3.5,
            "events_count": 12,
        },
        "canary_check": {
            "sandbox_id": "golden-01",
            "attempted_at": datetime.now(UTC).isoformat(),
            "target_host": "example.com",
            "request_succeeded": False,
        },
        "repository": {
            "provider": "github",
            "repository": "acme/shop",
            "ref": "main",
            "commit": "a" * 40,
            "snapshot_digest": "b" * 64,
        },
        "agent_activity": {
            "tool_calls": 12,
            "tools_used": ["http_get", "http_post", "read_log"],
            "steps_total": 8,
            "steps_completed": 6,
            "steps_failed": 2,
            "denied_attempts": 1,
            "errors": 0,
            "planner": "llm",
            "mission": "Test authentication and checkout",
        },
        "signature_algorithm": "ed25519",
    }


def test_findings_provenance_mission_sign_and_verify():
    signer = generate_keypair()
    receipt = SignedReceipt(**_receipt_payload())
    signed = signer.sign(receipt)

    assert signed.repository.commit == "a" * 40
    assert signed.agent_activity.mission == "Test authentication and checkout"
    assert signed.run_report.findings[0]["status"] == "confirmed"

    assert verify_receipt_signature(signed, signer.public_key)


def test_tampered_finding_breaks_verification():
    signer = generate_keypair()
    receipt = SignedReceipt(**_receipt_payload())
    signed = signer.sign(receipt)

    tampered = signed.model_copy(deep=True)
    tampered.run_report.findings[0]["status"] = "informational"
    assert not verify_receipt_signature(tampered, signer.public_key)


def test_tampered_provenance_breaks_verification():
    signer = generate_keypair()
    receipt = SignedReceipt(**_receipt_payload())
    signed = signer.sign(receipt)

    tampered = signed.model_copy(deep=True)
    tampered.repository.commit = "c" * 40
    assert not verify_receipt_signature(tampered, signer.public_key)


def test_legacy_receipt_without_repository_still_verifies():
    """Byte-compat: the optional repository key never appears on old runs."""
    signer = generate_keypair()
    payload = _receipt_payload()
    del payload["repository"]
    payload["receipt_version"] = 4
    receipt = SignedReceipt(**payload)
    signed = signer.sign(receipt)
    assert signed.repository is None
    assert verify_receipt_signature(signed, signer.public_key)
