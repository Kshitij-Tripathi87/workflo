"""Outside-verifier script — checks a signed receipt WITHOUT trusting workflo.

An outside observer (someone who didn't build workflo) runs this against
a receipt JSON file produced by `workflo run`. It checks the four claims
that can be verified from the receipt alone:

  - Claim #2: container + tmpfs are gone (proven via TeardownProof)
  - Claim #3: canary request failed (egress blocked)
  - Claim #4: signature verifies against the published public key
  - Claim #6: report is human-readable (findings present, structure sensible)

Usage:
    python -m sandbox_isolation.verify_receipts receipt.json --pubkey public.pem

Or:
    python -m sandbox_isolation.verify_receipts receipt.json --fingerprint <sha256-hex>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives import serialization


def verify_receipt_file(
    receipt_path: str,
    pubkey_path: Optional[str] = None,
    fingerprint: Optional[str] = None,
) -> int:
    """Verify a receipt file. Returns 0 on success, 1 on failure."""

    from workflo_schema.sandbox import SignedReceipt
    from sandbox_isolation import verify_receipt_signature, fingerprint_public_key

    try:
        data = json.loads(Path(receipt_path).read_text())
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"FAILED: cannot read receipt file: {e}", file=sys.stderr)
        return 1

    receipt_data = data.get("receipt", data)

    try:
        receipt = SignedReceipt(**receipt_data)
    except Exception as e:
        print(f"FAILED: receipt does not match schema: {e}", file=sys.stderr)
        return 1

    print(f"Sandbox ID:      {receipt.sandbox_id}")
    print(f"Issued at:       {receipt.issued_at}")
    print(f"Total tests:     {receipt.run_report.total}")
    print(f"Passed:          {receipt.run_report.passed}")
    print(f"Failed:          {receipt.run_report.failed}")
    print(f"Container gone:  {receipt.teardown_proof.container_removed}")
    print(f"Filesystem gone: {receipt.teardown_proof.filesystem_removed}")
    print(f"Canary blocked:  {not receipt.canary_check.request_succeeded}")

    checks_passed = []
    checks_failed = []

    # Claim #2: container + tmpfs provably gone
    if receipt.teardown_proof.container_removed:
        checks_passed.append("Claim #2a: container_removed is True")
    else:
        checks_failed.append("Claim #2a: container_removed is False — container may persist!")

    if receipt.teardown_proof.filesystem_removed:
        checks_passed.append("Claim #2b: filesystem_removed is True")
    else:
        checks_failed.append("Claim #2b: filesystem_removed is False — tmpfs may persist!")

    if receipt.teardown_proof.no_snapshot_retained:
        checks_passed.append("Claim #2c: no_snapshot_retained is True")
    else:
        checks_failed.append("Claim #2c: snapshot was retained — privacy violation!")

    # Claim #3: canary request must fail
    if not receipt.canary_check.request_succeeded:
        checks_passed.append("Claim #3: canary shows egress is blocked")
    else:
        checks_failed.append("Claim #3: canary SUCCEEDED — network isolation is broken!")

    # Claim #4: signature must verify
    if pubkey_path:
        pubkey_bytes = Path(pubkey_path).read_bytes()
        public_key = serialization.load_pem_public_key(pubkey_bytes)

        if fingerprint:
            actual_fp = fingerprint_public_key(public_key)
            if actual_fp != fingerprint:
                checks_failed.append(f"Claim #4: fingerprint mismatch (expected {fingerprint}, got {actual_fp})")
                return _summarize(checks_passed, checks_failed)

        if verify_receipt_signature(receipt, public_key):
            checks_passed.append("Claim #4: signature verifies against published public key")
        else:
            checks_failed.append("Claim #4: signature INVALID — receipt is tampered or signed by a different key!")
    else:
        checks_failed.append("Claim #4: no --pubkey provided, cannot verify signature")

    # Claim #6: report is human-readable (findings exist if anything failed)
    if receipt.run_report.failed > 0 and not receipt.run_report.findings:
        checks_failed.append("Claim #6: report has failures but no findings — not human-readable")
    else:
        checks_passed.append("Claim #6: report structure is human-readable")

    # Lifecycle events are present (audit trail)
    if len(receipt.lifecycle_events) >= 3:
        checks_passed.append(f"Audit trail: {len(receipt.lifecycle_events)} lifecycle events recorded")
    else:
        checks_failed.append("Audit trail: too few lifecycle events — auditability is compromised")

    return _summarize(checks_passed, checks_failed)


def _summarize(checks_passed, checks_failed) -> int:
    """Print a summary of all checks and return exit code."""
    print("\n--- Verification Summary ---")
    for c in checks_passed:
        print(f"  PASS  {c}")
    for c in checks_failed:
        print(f"  FAIL  {c}")

    print(f"\nTotal: {len(checks_passed)} passed, {len(checks_failed)} failed")
    if checks_failed:
        print(f"\nRESULT: VERIFICATION FAILED — {len(checks_failed)} check(s) failed.", file=sys.stderr)
        return 1
    print("\nRESULT: VERIFICATION PASSED — all claims verified.")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Verify a workflo receipt's claims without trusting workflo itself.",
    )
    parser.add_argument("receipt", help="Path to receipt JSON file")
    parser.add_argument("--pubkey", help="Path to public key PEM file")
    parser.add_argument("--fingerprint", help="Expected public key fingerprint (SHA-256 hex)")
    args = parser.parse_args()

    sys.exit(verify_receipt_file(args.receipt, args.pubkey, args.fingerprint))


if __name__ == "__main__":
    main()
