#!/usr/bin/env python3
"""Independently verify a receipt bundle and retain metadata-only outcome."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import sys
from pathlib import Path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--pubkey", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    # The verifier process must not inherit staging credentials.
    sensitive_names = (
        "WORKFLO_MODEL_API_KEY",
        "WORKFLO_GATEWAY_API_KEY",
        "WORKFLO_LLM_API_KEY",
    )
    inherited_secrets = [name for name in sensitive_names if os.environ.get(name)]

    # The outside verifier has legacy console output. Suppress it here so the
    # protected job retains only the structured status/count report below.
    try:
        if inherited_secrets:
            raise RuntimeError("independent verifier inherited staging credentials")
        from sandbox_isolation.verify_receipts import verify_receipt

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = verify_receipt(
                str(args.receipt),
                pubkey_path=str(args.pubkey),
                evidence_dir=str(args.evidence),
            )
        report = {
            "passed": result.status.value == "VALID",
            "status": result.status.value,
            "checks_passed_count": len(result.checks_passed),
            "checks_failed_count": len(result.checks_failed),
            "staging_secrets_present": False,
            "receipt_sha256": _sha(args.receipt),
            "public_key_sha256": _sha(args.pubkey),
            "evidence_manifest_sha256": _sha(args.evidence / "manifest.json"),
            "evidence_events_sha256": _sha(args.evidence / "events.jsonl"),
        }
    except Exception as exc:  # noqa: BLE001 - classify verifier failure
        report = {
            "passed": False,
            "status": "VERIFICATION_FAILED",
            "checks_passed_count": 0,
            "checks_failed_count": 1,
            "staging_secrets_present": bool(inherited_secrets),
            "failure_class": type(exc).__name__,
        }

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if not report["passed"]:
        print(f"independent receipt verification failed: {report['status']}", file=sys.stderr)
        return 1
    print("independent receipt verification returned VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
