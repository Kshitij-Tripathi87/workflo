#!/usr/bin/env python3
"""Fail closed when Gate 5 evidence is incomplete or contains unsafe text."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

REQUIRED_FILES = (
    "configuration-validation.json",
    "manifest-verification.json",
    "model-artifacts.json",
    "run-identity.json",
    "commit.txt",
    "python-version.txt",
    "manifest.sha256",
    "deep-image-digest.txt",
    "deep-image-binding.json",
    "environment-setup.json",
    "llamacpp-worker-smoke.json",
    "reporting-smoke.json",
    "container-isolation.json",
    "gateway-smoke.json",
    "model-benchmark-1.json",
    "model-benchmark-1.md",
    "model-benchmark-2.json",
    "model-benchmark-2.md",
    "model-benchmark-3.json",
    "model-benchmark-3.md",
    "cost-report.json",
    "failure-evidence.json",
    "sandbox-receipt/receipt.json",
    "sandbox-receipt/receipt-key.pub.pem",
    "sandbox-receipt/evidence/manifest.json",
    "sandbox-receipt/evidence/events.jsonl",
    "previous-model-artifacts.json",
    "previous-manifest-verification.json",
    "rollback-image-binding.json",
    "rollback-smoke/llamacpp-worker-smoke.json",
    "rollback-smoke/reporting-smoke.json",
    "rollback-smoke/container-isolation.json",
    "rollback.json",
    "teardown-check.json",
)

TEXT_PATTERNS = (
    re.compile(rb"Authorization\s*:\s*(?:Bearer|Basic)\s+\S+", re.IGNORECASE),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"https?://[^\s/:]+:[^\s/@]+@", re.IGNORECASE),
    re.compile(rb"https?://[^\s]+[?&](?:token|sig|signature|api[_-]?key|credential)=", re.IGNORECASE),
    re.compile(rb"WORKFLO-P4-SOURCE-CANARY-DO-NOT-ECHO"),
    re.compile(rb"WFSECRET-P4-DO-NOT-FORWARD"),
    re.compile(rb'"(?:messages|raw_prompt|source_code|file_content)"\s*:', re.IGNORECASE),
    re.compile(rb"(?m)^\s*(?:async\s+)?def\s+[A-Za-z_][A-Za-z0-9_]*\s*\("),
    re.compile(rb"(?m)^\s*class\s+[A-Za-z_][A-Za-z0-9_]*\s*[:(]"),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--secret-env", action="append", default=[])
    args = parser.parse_args()

    missing = [
        name for name in REQUIRED_FILES
        if not (args.root / name).is_file() or not (args.root / name).stat().st_size
    ]
    secrets = [os.environ[name].encode() for name in args.secret_env if os.environ.get(name)]
    scanned: list[str] = []
    rejected: list[str] = []
    secret_files: list[str] = []
    output = args.out.resolve()
    if args.root.is_dir():
        for path in sorted(args.root.rglob("*")):
            if not path.is_file() or path.resolve() == output:
                continue
            relative = path.relative_to(args.root).as_posix()
            scanned.append(relative)
            if path.is_symlink():
                rejected.append(relative)
                continue
            try:
                data = path.read_bytes()
            except OSError:
                rejected.append(relative)
                continue
            contains_secret = any(secret in data for secret in secrets)
            if contains_secret:
                secret_files.append(relative)
            if contains_secret or any(pattern.search(data) for pattern in TEXT_PATTERNS):
                rejected.append(relative)

    report = {
        "passed": not missing and not rejected,
        "files_scanned_count": len(scanned),
        "files_scanned": scanned,
        "missing_files": missing,
        "rejected_files": rejected,
        "staging_secrets_present": bool(secret_files),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not report["passed"]:
        print("P4 evidence completeness/redaction scan failed", file=sys.stderr)
        return 1
    print(f"P4 evidence scan passed for {len(scanned)} source-free files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
