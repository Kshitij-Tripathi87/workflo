"""Sprint 4 exit-gate acceptance matrix — run against a real run directory.

Usage (Linux, after a golden run):
    python scripts/linux/exit_gate_check.py /path/to/.workflo/runs/<sandbox_id>

Every row of the matrix must hold:

    intact receipt+evidence              -> VALID
    modified receipt                     -> INVALID
    modified evidence                    -> INVALID
    revoked signing key                  -> INVALID   (stub directory)
    missing transparency proof           -> INCOMPLETE (when required)
    transparency proof present           -> VALID
    missing exit-gate artifact files     -> FAIL the gate

(Cross-tenant read/revoke -> NOT FOUND is proven by the control-plane
suites: apps/control-plane/tests/test_audit.py and test_orgs.py.)

Exit 0 when every case matches expectation; 1 otherwise.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

EXIT_GATE_FILES = (
    "provenance.json", "run_state.json", "observations.jsonl",
    "tool_calls.jsonl", "findings.json", "agent_activity.json",
    "teardown_attestation.json", "receipt.json", "receipt.sig",
)

_results: list[tuple[str, bool, str]] = []


def _record(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}")


def _verify(receipt_path: Path, **kwargs):
    from sandbox_isolation.verify_receipts import VerifyStatus, verify_receipt

    return verify_receipt(str(receipt_path), **kwargs)


class _KeyDirectory(BaseHTTPRequestHandler):
    """Stub provisioning directory: every key reports as REVOKED."""

    def do_GET(self):
        body = json.dumps({
            "status": "revoked",
            "revoked_at": "2026-01-01T00:00:00Z",
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def _start_stub_directory() -> tuple[HTTPServer, str]:
    httpd = HTTPServer(("127.0.0.1", 0), _KeyDirectory)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def _signed_receipt_with_key_id(pubkey_path: Path, key_id: str) -> Path:
    """Build a fresh signed receipt carrying a directory-tracked key_id —
    the revocation case needs a key the directory knows about."""
    from datetime import UTC, datetime

    from sandbox_isolation import generate_keypair
    from workflo_schema.sandbox import (
        CanaryCheckResult, RunReport, SandboxLifecycleEvent, SignedReceipt,
        TeardownProof,
    )
    from cryptography.hazmat.primitives import serialization

    signer = generate_keypair()
    receipt = SignedReceipt(
        sandbox_id="exit-gate-revoke",
        issued_at=datetime.now(UTC),
        run_report=RunReport(sandbox_id="exit-gate-revoke", total=1,
                             passed=1, failed=0, duration_seconds=0.1),
        teardown_proof=TeardownProof(
            sandbox_id="exit-gate-revoke", container_id="c",
            container_removed=True, filesystem_removed=True,
            no_snapshot_retained=True, destroyed_at=datetime.now(UTC)),
        canary_check=CanaryCheckResult(
            sandbox_id="exit-gate-revoke", attempted_at=datetime.now(UTC),
            target_host="https://example.com", request_succeeded=False,
            error="blocked"),
        key_id=key_id,
    )
    receipt.lifecycle_events = [
        SandboxLifecycleEvent(sandbox_id="exit-gate-revoke", event=e,
                              timestamp=datetime.now(UTC))
        for e in ("created", "destroyed", "receipt_signed")
    ]
    signer.sign(receipt)
    path = pubkey_path.parent / "revoked-receipt.json"
    path.write_text(receipt.model_dump_json())
    pubkey_path.write_bytes(signer.public_key.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    return path


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: exit_gate_check.py <run_dir>")
        return 2
    run_dir = Path(sys.argv[1])
    receipt_path = run_dir / "receipt.json"
    evidence_dir = run_dir / "evidence"
    if not receipt_path.exists():
        print(f"FATAL: no receipt at {receipt_path}")
        return 2

    print("== Exit-gate artifact set ==")
    missing = [f for f in EXIT_GATE_FILES if not (run_dir / f).exists()]
    # agent_activity.json is only written for agent tiers; for --test-only
    # runs it is legitimately absent (the receipt's agent_activity is null).
    import json as _json
    _receipt_doc = _json.loads(receipt_path.read_text())
    if _receipt_doc.get("agent_activity") is None:
        missing = [f for f in missing if f != "agent_activity.json"]
    _record("artifact set complete", not missing,
            f"missing={missing}" if missing else "")

    # Where does the receipt's signing key live? (local keystore layout)
    import os
    pubkey = None
    fp = _receipt_doc.get("public_key_fingerprint")
    if fp:
        candidate = Path(os.path.expanduser(
            f"~/.config/workflo/keys/{fp}.pub.pem"))
        if candidate.exists():
            pubkey = candidate

    print("== Acceptance matrix ==")
    # 1. intact -> VALID
    r = _verify(receipt_path, pubkey_path=str(pubkey) if pubkey else None,
                evidence_dir=str(evidence_dir))
    _record("intact receipt verifies (VALID)", r.status.value == "VALID",
            r.status.value)

    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)

        # 2. modified receipt -> INVALID
        tampered = json.loads(receipt_path.read_text())
        tampered["run_report"]["passed"] = 9999
        tampered_path = tdp / "tampered.json"
        tampered_path.write_text(json.dumps(tampered))
        r = _verify(tampered_path, pubkey_path=str(pubkey) if pubkey else None)
        _record("modified receipt -> INVALID", r.status.value == "INVALID",
                r.status.value)

        # 3. modified evidence -> INVALID
        ev_copy = tdp / "evidence"
        shutil.copytree(evidence_dir, ev_copy)
        events = ev_copy / "events.jsonl"
        events.write_text(events.read_text() + '{"event":"forged"}\n')
        r = _verify(receipt_path, pubkey_path=str(pubkey) if pubkey else None,
                    evidence_dir=str(ev_copy))
        _record("modified evidence -> INVALID", r.status.value == "INVALID",
                r.status.value)

        # 4. revoked signing key -> INVALID (stub provisioning directory)
        httpd, directory = _start_stub_directory()
        try:
            key_pub = tdp / "revoked-key.pub.pem"
            revoked_receipt = _signed_receipt_with_key_id(key_pub, "k-revoked")
            r = _verify(revoked_receipt, pubkey_path=str(key_pub),
                        key_directory=directory)
            _record("revoked signing key -> INVALID",
                    r.status.value == "INVALID", r.status.value)
        finally:
            httpd.shutdown()

        # 5. transparency: required-but-missing -> INCOMPLETE
        r = _verify(receipt_path, pubkey_path=str(pubkey) if pubkey else None,
                    require_transparency=True)
        _record("missing transparency proof -> INCOMPLETE",
                r.status.value == "INCOMPLETE", r.status.value)

        # 6. transparency proof present -> VALID
        # Append this run's canonical fingerprint to a fresh log, take the
        # inclusion proof, and verify the receipt against it.
        from sandbox_isolation.transparency import (
            LocalTransparencyLog,
            receipt_fingerprint,
        )
        from workflo_schema.sandbox import SignedReceipt

        log = LocalTransparencyLog(tdp / "transparency.log")
        receipt_obj = SignedReceipt(**_receipt_doc.get("receipt", _receipt_doc))
        leaf = receipt_fingerprint(receipt_obj.canonical_payload())
        log.append(leaf)
        proof = log.proof_inclusion(leaf)
        proof_path = tdp / "transparency_proof.json"
        proof_path.write_text(json.dumps(proof))
        r = _verify(receipt_path, pubkey_path=str(pubkey) if pubkey else None,
                    evidence_dir=str(evidence_dir),
                    transparency_proof=str(proof_path))
        _record("transparency proof present -> VALID",
                r.status.value == "VALID", r.status.value)

        # 6b. proof for a DIFFERENT receipt -> INVALID (fold mismatch)
        other = SignedReceipt(**_receipt_doc.get("receipt", _receipt_doc))
        other.run_report.total += 1  # un-signed change: leaf differs
        from sandbox_isolation.transparency import receipt_fingerprint as _rf
        log2 = LocalTransparencyLog(tdp / "transparency2.log")
        log2.append(_rf(other.canonical_payload()))
        proof2 = log2.proof_inclusion(_rf(other.canonical_payload()))
        proof2_path = tdp / "transparency_proof2.json"
        proof2_path.write_text(json.dumps(proof2))
        r = _verify(receipt_path, pubkey_path=str(pubkey) if pubkey else None,
                    evidence_dir=str(evidence_dir),
                    transparency_proof=str(proof2_path))
        _record("wrong receipt's proof -> INVALID",
                r.status.value == "INVALID", r.status.value)

    print()
    failed = [n for n, ok, _ in _results if not ok]
    if failed:
        print(f"EXIT GATE: FAIL ({len(failed)} case(s)): {failed}")
        return 1
    print("EXIT GATE: PASS — all acceptance cases verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
