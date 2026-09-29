"""Outside-verifier script — checks a signed receipt WITHOUT trusting workflo.

An outside observer (someone who didn't build workflo) runs this against
a receipt JSON file produced by `workflo run`. It checks the claims
that can be verified from the receipt (and, when provided, the evidence):

  - Claim #2: sandbox provably gone (TeardownProof; Docker or namespaces)
  - Claim #3: canary request failed (egress blocked)
  - Claim #4: signature verifies against the published public key
  - Claim #5: evidence binding digests match the recomputed bundle (--evidence)
  - Claim #6: report is human-readable (findings present, structure sensible)
  - Claim #7: signing key is not revoked in the provisioning directory
              (--key-directory; skips when the receipt has no key_id)
  - Claim #8: transparency-log inclusion proof verifies against a checkpoint
              root (--transparency-proof; --require-transparency makes its
              absence an INCOMPLETE proof obligation)

Verification states (F-7): the verifier distinguishes WHY a receipt
failed, because "tampered", "malformed", "too new", and "proof
obligations unmet" demand different responses:

    VALID                signature + evidence binding + claims all hold
    INVALID              cryptographically wrong (tampered) or signed
                         claims provably false
    UNSUPPORTED_VERSION  receipt_version outside the supported set
    CORRUPT              unparseable / malformed / schema-invalid
    INCOMPLETE           parseable and not proven wrong, but proof
                         obligations are unmet (no pubkey, evidence
                         bundle missing, audit trail too thin)
    VERIFICATION_FAILED  the verifier itself could not perform a check

Usage:
    python -m sandbox_isolation.verify_receipts receipt.json --pubkey public.pem

Or:
    python -m sandbox_isolation.verify_receipts receipt.json --fingerprint <sha256-hex>

With evidence:
    python -m sandbox_isolation.verify_receipts receipt.json --pubkey public.pem --evidence <dir>

With key-revocation check (provenance — the signing key must not be revoked):
    python -m sandbox_isolation.verify_receipts receipt.json --pubkey public.pem \
        --key-directory https://cp.workflo.dev
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives import serialization


class VerifyStatus(str, Enum):
    """Deterministic verifier states (spec §11.2)."""

    VALID = "VALID"
    INVALID = "INVALID"
    UNSUPPORTED_VERSION = "UNSUPPORTED_VERSION"
    CORRUPT = "CORRUPT"
    INCOMPLETE = "INCOMPLETE"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"


@dataclass
class VerifyResult:
    """Structured outcome of a verification attempt."""

    status: VerifyStatus
    checks_passed: list[str] = field(default_factory=list)
    checks_failed: list[str] = field(default_factory=list)
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status == VerifyStatus.VALID


def verify_receipt(
    receipt_path: str,
    pubkey_path: Optional[str] = None,
    fingerprint: Optional[str] = None,
    evidence_dir: Optional[str] = None,
    key_directory: Optional[str] = None,
    transparency_proof: Optional[str] = None,
    require_transparency: bool = False,
) -> VerifyResult:
    """Verify a receipt file and return the structured result.

    Classification priority (highest first): CORRUPT >
    UNSUPPORTED_VERSION > VERIFICATION_FAILED > INVALID > INCOMPLETE >
    VALID.
    """
    from workflo_schema.sandbox import SignedReceipt
    from sandbox_isolation import verify_receipt_signature, fingerprint_public_key

    # -- parse ---------------------------------------------------------------
    try:
        data = json.loads(Path(receipt_path).read_text())
    except (OSError, UnicodeDecodeError) as e:
        return VerifyResult(
            VerifyStatus.CORRUPT, detail=f"cannot read receipt file: {e}")
    except json.JSONDecodeError as e:
        return VerifyResult(
            VerifyStatus.CORRUPT, detail=f"receipt is not valid JSON: {e}")

    receipt_data = data.get("receipt", data)

    # Duplicate JSON keys parse silently in stdlib — a receipt carrying
    # them is structurally suspect. Reject via the strict hook (R-3).
    try:
        raw = Path(receipt_path).read_text()
        json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except ValueError as e:
        return VerifyResult(VerifyStatus.CORRUPT, detail=str(e))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        pass  # already classified above

    try:
        receipt = SignedReceipt(**receipt_data)
    except Exception as e:
        if "UNSUPPORTED_RECEIPT_VERSION" in str(e):
            return VerifyResult(
                VerifyStatus.UNSUPPORTED_VERSION,
                detail=f"{e} — this receipt uses a protocol version this "
                       "verifier does not support",
            )
        return VerifyResult(
            VerifyStatus.CORRUPT, detail=f"receipt does not match schema: {e}")

    checks_passed: list[str] = []
    checks_failed: list[str] = []

    print(f"Sandbox ID:      {receipt.sandbox_id}")
    print(f"Receipt version: {receipt.receipt_version}")
    print(f"Issued at:       {receipt.issued_at}")
    print(f"Total tests:     {receipt.run_report.total}")
    print(f"Passed:          {receipt.run_report.passed}")
    print(f"Failed:          {receipt.run_report.failed}")

    # -- checks (a verifier crash is itself a classified outcome) ------------
    try:
        _run_checks(
            receipt, checks_passed, checks_failed,
            pubkey_path, fingerprint, evidence_dir, receipt_path,
            key_directory, transparency_proof, require_transparency,
        )
    except Exception as e:  # noqa: BLE001 — verifier crash is a state, not a traceback
        return VerifyResult(
            VerifyStatus.VERIFICATION_FAILED,
            checks_passed, checks_failed,
            detail=f"verifier could not complete a required check: {e}",
        )

    # -- classification --------------------------------------------------------
    return _classify(receipt, checks_passed, checks_failed)


def _reject_duplicate_keys(pairs):
    """object_pairs_hook that rejects duplicate keys (R-3)."""
    seen = set()
    for key, _ in pairs:
        if key in seen:
            raise ValueError(f"receipt contains duplicate field: {key!r}")
        seen.add(key)
    return dict(pairs)


def _run_checks(receipt, checks_passed, checks_failed,
                pubkey_path, fingerprint, evidence_dir, receipt_path,
                key_directory=None, transparency_proof=None,
                require_transparency=False) -> None:
    """All claim checks. Raises on verifier-internal failure (classified
    as VERIFICATION_FAILED by the caller)."""
    from sandbox_isolation import verify_receipt_signature, fingerprint_public_key

    # Claim #2: sandbox provably gone — branch on runtime type
    tp = receipt.teardown_proof
    if getattr(tp, "runtime_type", None) == "namespaces":
        print(f"Runtime:         namespaces (bwrap + cgroups v2 + netns)")
        print(f"Processes gone:  {tp.processes_terminated}")
        print(f"Cgroup gone:     {tp.cgroup_removed}")
        print(f"Netns gone:      {tp.network_namespace_removed}")
        print(f"Workspace gone:  {tp.workspace_removed}")

        namespace_claims = [
            ("processes_terminated", tp.processes_terminated),
            ("cgroup_removed", tp.cgroup_removed),
            ("network_namespace_removed", tp.network_namespace_removed),
            ("workspace_removed", tp.workspace_removed),
        ]
        for name, value in namespace_claims:
            if value is True:
                checks_passed.append(f"Claim #2: {name} is True")
            else:
                checks_failed.append(f"Claim #2: {name} is {value} — sandbox state may persist!")
    else:
        print(f"Container gone:  {tp.container_removed}")
        print(f"Filesystem gone: {tp.filesystem_removed}")

        if tp.container_removed:
            checks_passed.append("Claim #2a: container_removed is True")
        else:
            checks_failed.append("Claim #2a: container_removed is False — container may persist!")

        if tp.filesystem_removed:
            checks_passed.append("Claim #2b: filesystem_removed is True")
        else:
            checks_failed.append("Claim #2b: filesystem_removed is False — tmpfs may persist!")

    if tp.no_snapshot_retained:
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
                checks_failed.append(
                    f"Claim #4: fingerprint mismatch (expected {fingerprint}, got {actual_fp})")
            else:
                checks_passed.append("Claim #4: public key fingerprint matches")

        if verify_receipt_signature(receipt, public_key):
            checks_passed.append("Claim #4: signature verifies against published public key")
        else:
            checks_failed.append("Claim #4: signature INVALID — receipt is tampered or signed by a different key!")
    else:
        checks_failed.append("Claim #4: no --pubkey provided, cannot verify signature")

    # Claim #5: evidence binding — the signed digests must match the
    # independently recomputed evidence bundle (when the bundle is available).
    if receipt.evidence_binding is not None:
        from sandbox_isolation import (
            verify_evidence_binding,
            resolve_evidence_dir,
        )

        ev_dir = Path(evidence_dir) if evidence_dir else resolve_evidence_dir(
            Path(receipt_path), receipt
        )
        if ev_dir is None:
            checks_failed.append(
                "Claim #5: receipt has an evidence binding but the evidence directory "
                "was not found — pass --evidence to verify it"
            )
        else:
            binding_ok, binding_checks = verify_evidence_binding(receipt, ev_dir)
            for line in binding_checks:
                if line.startswith("OK"):
                    checks_passed.append(f"Claim #5: {line}")
                else:
                    checks_failed.append(f"Claim #5: {line}")
    # Legacy Docker receipts have no evidence binding — not a failure,
    # just noted (their audit trail is the signed lifecycle events).

    # Claim #6: report is human-readable (findings exist if anything failed)
    if receipt.run_report.failed > 0 and not receipt.run_report.findings:
        checks_failed.append("Claim #6: report has failures but no findings — not human-readable")
    else:
        checks_passed.append("Claim #6: report structure is human-readable")

    # Claim #7: provenance — the signing key must not be REVOKED in the
    # provisioning directory. Only meaningful when the receipt carries a
    # key_id (locally-generated keys are anonymous by design) AND the
    # caller opted into the directory check. Skipping silently would make
    # revoked-key receipts look valid, so "checked nothing" says nothing.
    key_id = getattr(receipt, "key_id", None)
    if key_directory and key_id:
        from sandbox_isolation.key_directory import check_key_status

        status = check_key_status(key_directory, key_id)
        if status.is_usable:
            checks_passed.append(f"Claim #7: signing key active in directory ({key_id})")
        elif status.is_revoked:
            checks_failed.append(
                f"Claim #7: signing key is REVOKED ({status.detail}) — "
                "receipt provenance is void even though the signature verifies"
            )
        elif status.status == "not_found":
            checks_failed.append(
                f"Claim #7: signing key {key_id} is not registered in the directory — "
                "provenance unverifiable"
            )
        else:
            checks_failed.append(
                f"Claim #7: could not reach key directory ({status.detail}) — "
                "revocation check incomplete"
            )

    # Claim #8: transparency-log inclusion — the receipt's canonical
    # fingerprint must fold, with the supplied sibling path, into the
    # checkpoint root the log recorded. A folded mismatch is a HARD failure
    # (the receipt was never in that log); a missing proof when required is
    # a proof obligation (INCOMPLETE), like a missing evidence bundle.
    if transparency_proof:
        ok = False
        proof_doc = None
        try:
            proof_doc = json.loads(Path(transparency_proof).read_text())
            from sandbox_isolation.transparency import (
                receipt_fingerprint,
                verify_inclusion,
            )

            leaf = receipt_fingerprint(receipt.canonical_payload())
            ok = verify_inclusion(
                leaf,
                int(proof_doc["leaf_index"]),
                int(proof_doc["tree_size"]),
                list(proof_doc["proof"]),
                str(proof_doc["root"]),
            )
        except Exception:
            # Parse/shape errors are verifier-input problems; treat as a
            # mismatch rather than crashing the verifier.
            ok = False
        if ok:
            checks_passed.append(
                "Claim #8: transparency inclusion proof verifies "
                f"(tree_size={proof_doc['tree_size']}, index={proof_doc['leaf_index']})"
            )
        else:
            checks_failed.append(
                "Claim #8: transparency inclusion proof does NOT fold to the "
                "checkpoint root — the receipt is not in that log"
            )
    elif require_transparency:
        checks_failed.append(
            "Claim #8: transparency proof missing — pass --transparency-proof"
        )

    # Lifecycle events are present (audit trail)
    if len(receipt.lifecycle_events) >= 3:
        checks_passed.append(f"Audit trail: {len(receipt.lifecycle_events)} lifecycle events recorded")
    else:
        checks_failed.append("Audit trail: too few lifecycle events — auditability is compromised")


# Check categories used for classification. Hard failures mean the
# receipt (or the world it describes) is provably wrong. Soft failures
# mean a proof obligation could not be COMPLETED — surfaced, never hidden.
_HARD_FAILURE_MARKERS = (
    "signature INVALID",
    "fingerprint mismatch",
    "may persist",
    "may persist!",
    "canary SUCCEEDED",
    "snapshot was retained",
    "not human-readable",
    "signing key is REVOKED",
    "does NOT fold to the checkpoint root",
)
_SOFT_FAILURE_MARKERS = (
    "no --pubkey provided",
    "was not found — pass --evidence",
    "evidence directory not found",
    "Audit trail: too few",
    "not registered in the directory",
    "could not reach key directory",
    "transparency proof missing",
)


def _classify(receipt, checks_passed, checks_failed) -> VerifyResult:
    hard = [c for c in checks_failed
            if any(m in c for m in _HARD_FAILURE_MARKERS)]
    soft = [c for c in checks_failed
            if c not in hard and any(m in c for m in _SOFT_FAILURE_MARKERS)]
    # Anything unrecognized is treated as hard — never silently downgrade.
    other = [c for c in checks_failed if c not in hard and c not in soft]
    hard.extend(other)

    if hard:
        return VerifyResult(VerifyStatus.INVALID, checks_passed, checks_failed)
    if soft:
        return VerifyResult(VerifyStatus.INCOMPLETE, checks_passed, checks_failed,
                            detail="proof obligations unmet (see checks)")
    return VerifyResult(VerifyStatus.VALID, checks_passed, checks_failed)


def verify_receipt_file(
    receipt_path: str,
    pubkey_path: Optional[str] = None,
    fingerprint: Optional[str] = None,
    evidence_dir: Optional[str] = None,
    key_directory: Optional[str] = None,
    transparency_proof: Optional[str] = None,
    require_transparency: bool = False,
) -> int:
    """Verify a receipt file. Returns 0 on success, 1 on failure.

    Kept as the CLI entry point; the structured API is verify_receipt().
    """
    result = verify_receipt(
        receipt_path, pubkey_path, fingerprint, evidence_dir, key_directory,
        transparency_proof, require_transparency,
    )
    return _summarize(result)


def _summarize(result: VerifyResult) -> int:
    """Print a summary of all checks and return exit code."""
    print("\n--- Verification Summary ---")
    for c in result.checks_passed:
        print(f"  PASS  {c}")
    for c in result.checks_failed:
        print(f"  FAIL  {c}")

    print(f"\nTotal: {len(result.checks_passed)} passed, {len(result.checks_failed)} failed")
    if result.status == VerifyStatus.VALID:
        print("\nRESULT: VERIFICATION PASSED — all claims verified.")
        return 0
    print(f"\nRESULT: {result.status.value} — {result.detail or 'see failed checks above'}",
          file=sys.stderr)
    return 1


def main():
    parser = argparse.ArgumentParser(
        description="Verify a workflo receipt's claims without trusting workflo itself.",
    )
    parser.add_argument("receipt", help="Path to receipt JSON file")
    parser.add_argument("--pubkey", help="Path to public key PEM file")
    parser.add_argument("--fingerprint", help="Expected public key fingerprint (SHA-256 hex)")
    parser.add_argument("--evidence", dest="evidence_dir", default=None,
                        help="Path to the evidence bundle directory (verifies the receipt's evidence binding)")
    parser.add_argument("--key-directory", dest="key_directory", default=None,
                        help="Control-plane base URL for signing-key status (revocation) checks")
    parser.add_argument("--transparency-proof", dest="transparency_proof", default=None,
                        help="Inclusion proof JSON ({leaf_index, tree_size, root, proof}) "
                             "from the transparency log")
    parser.add_argument("--require-transparency", action="store_true",
                        help="Fail INCOMPLETE when no transparency proof is supplied")
    args = parser.parse_args()

    sys.exit(verify_receipt_file(
        args.receipt, args.pubkey, args.fingerprint, args.evidence_dir,
        args.key_directory, args.transparency_proof, args.require_transparency,
    ))


if __name__ == "__main__":
    main()
