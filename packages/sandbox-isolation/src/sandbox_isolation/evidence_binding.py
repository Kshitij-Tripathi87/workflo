"""Evidence binding verification — recompute digests from an evidence bundle.

A receipt produced by the namespace runtime embeds an EvidenceBinding:
SHA-256 digests of its hash-chained event ledger, directories, and the
manifest file. The receipt's Ed25519 signature covers those digests.

This module lets an OUTSIDE verifier recompute every digest from the
evidence directory alone and compare against the (signed) binding —
proving the evidence was produced by the same run and was not altered
afterwards. It deliberately duplicates the chain format defined in
sandbox_runtime.evidence: the verifier must not import the code it is
verifying.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional

GENESIS_HASH = "0" * 64


def _hash_directory(dir_path: Path) -> str:
    """SHA-256 over all files in a directory (sorted, recursive)."""
    if not dir_path.exists():
        return GENESIS_HASH
    hasher = hashlib.sha256()
    for f in sorted(dir_path.rglob("*")):
        if f.is_file():
            hasher.update(f.read_bytes())
    return hasher.hexdigest()


def compute_evidence_digests(evidence_dir: Path) -> Optional[dict]:
    """Recompute all evidence bundle digests from the directory.

    Returns None when the bundle is incomplete or its internal hash
    chain is invalid (fail closed: a broken chain means no digests can
    be trusted). Recomputation follows the exact ledger format written
    by the sandbox runtime: each event record's hash covers
    event_id + timestamp + event_type + canonical-JSON data + prev_hash.
    """
    evidence_dir = Path(evidence_dir)
    manifest_path = evidence_dir / "manifest.json"
    events_file = evidence_dir / "events.jsonl"
    if not manifest_path.exists() or not events_file.exists():
        return None

    prev_hash = GENESIS_HASH
    events_hasher = hashlib.sha256()
    events_count = 0

    try:
        with open(events_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                required = ["event_id", "timestamp", "event_type", "data", "prev_hash", "event_hash"]
                if not all(field in record for field in required):
                    return None
                event_content = (
                    f"{record['event_id']}{record['timestamp']}{record['event_type']}"
                    f"{json.dumps(record['data'], sort_keys=True)}{prev_hash}"
                )
                expected_hash = hashlib.sha256(event_content.encode()).hexdigest()
                if record["event_hash"] != expected_hash:
                    return None
                if record["prev_hash"] != prev_hash:
                    return None
                events_hasher.update(record["event_hash"].encode())
                prev_hash = record["event_hash"]
                events_count += 1
    except (OSError, json.JSONDecodeError):
        return None

    events_sha256 = events_hasher.hexdigest()
    logs_sha256 = _hash_directory(evidence_dir / "logs")
    traces_sha256 = _hash_directory(evidence_dir / "traces")
    artifacts_sha256 = _hash_directory(evidence_dir / "artifacts")

    bundle_hasher = hashlib.sha256()
    for digest in (events_sha256, logs_sha256, traces_sha256, artifacts_sha256):
        bundle_hasher.update(digest.encode())
    bundle_sha256 = bundle_hasher.hexdigest()

    manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    return {
        "events_count": events_count,
        "events_sha256": events_sha256,
        "bundle_sha256": bundle_sha256,
        "manifest_sha256": manifest_sha256,
    }


def verify_evidence_binding(receipt, evidence_dir: Path) -> tuple[bool, list[str]]:
    """Verify a receipt's evidence binding against an evidence directory.

    Returns (ok, checks) where checks are human-readable results. Fails
    closed: missing binding, missing bundle, broken chain, or any digest
    mismatch all fail.
    """
    checks: list[str] = []
    binding = getattr(receipt, "evidence_binding", None)
    if binding is None:
        return False, ["receipt carries no evidence binding"]

    evidence_dir = Path(evidence_dir)
    if not evidence_dir.exists():
        return False, [f"evidence directory not found: {evidence_dir}"]

    digests = compute_evidence_digests(evidence_dir)
    if digests is None:
        return False, [f"evidence bundle at {evidence_dir} is incomplete or its hash chain is broken"]

    ok = True
    for field in ("events_count", "events_sha256", "bundle_sha256", "manifest_sha256"):
        expected = getattr(binding, field)
        actual = digests[field]
        if expected != actual:
            ok = False
            checks.append(f"MISMATCH {field}: receipt says {expected}, evidence recomputes {actual}")
        else:
            checks.append(f"OK {field} matches recomputed digest")
    return ok, checks


def resolve_evidence_dir(receipt_path: Path, receipt) -> Optional[Path]:
    """Locate the evidence directory for a receipt, or None.

    Resolution order:
      1. The binding's evidence_dir if it exists as-is (absolute or
         relative to CWD).
      2. The same path resolved relative to the receipt file's parent
         (receipts are written next to the run root).
    """
    binding = getattr(receipt, "evidence_binding", None)
    if binding is None:
        return None
    candidate = Path(binding.evidence_dir)
    if candidate.exists():
        return candidate
    receipt_path = Path(receipt_path)
    relative_to_receipt = receipt_path.parent / candidate
    if relative_to_receipt.exists():
        return relative_to_receipt
    # Receipts sit in <run_root>/receipt.json while evidence sits in
    # <run_root>/evidence — also try that sibling layout.
    sibling = receipt_path.parent / "evidence"
    if sibling.exists() and (sibling / "manifest.json").exists():
        return sibling
    return None
