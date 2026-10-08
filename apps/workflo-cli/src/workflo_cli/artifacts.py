"""Artifact analysis layer — read-only receipt and evidence readers.

Phase 7B: `workflo inspect` and `workflo explain` are a read-only artifact
analysis layer. Both commands share this module so neither implements its
own receipt/evidence parsing:

    receipt.wfrec ──► ReceiptReader ──┐
                                      ├──► TrustContext ──► inspect / explain
    evidence/     ──► EvidenceReader ─┘

Security properties (tested explicitly in the 7B suite):
  * the readers never execute anything
  * the readers never mutate the artifacts they read
  * the readers never invoke a model and never touch the network

Trust is explicit: every status distinguishes verified information from
untrusted or unavailable information, because `inspect` displays a
potentially attacker-controlled artifact. Digest recomputation deliberately
reuses sandbox_isolation.evidence_binding — the verifier must not import
the code it is verifying, and neither may the reporter.
"""

from __future__ import annotations

import hashlib
import json
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from sandbox_isolation import compute_evidence_digests, resolve_evidence_dir
from workflo_schema.sandbox import SUPPORTED_RECEIPT_VERSIONS, SignedReceipt

# Hard read limit — mirrors the CLI's receipt guard (main.py MAX_RECEIPT_BYTES)
MAX_RECEIPT_BYTES = 10 * 1024 * 1024  # 10 MB

# ---------------------------------------------------------------------------
# Trust statuses (7B.2) — explicit, never conflated
# ---------------------------------------------------------------------------

# Schema status
SCHEMA_VALID = "valid"
SCHEMA_CORRUPT = "corrupt"                  # unparseable / schema-invalid
SCHEMA_UNSUPPORTED = "unsupported_version"  # newer protocol than this CLI

# Signature status
SIG_VALID = "valid"
SIG_INVALID = "invalid"
SIG_UNSIGNED = "unsigned"  # no signature on the payload
SIG_UNKNOWN = "unknown"    # no public key available to verify with

# Evidence status
EVIDENCE_VALID = "valid"
EVIDENCE_INVALID = "invalid"  # chain broken or binding digests mismatch
EVIDENCE_MISSING = "missing"  # binding present, bundle not found
EVIDENCE_NONE = "none"        # legacy receipt, no binding
EVIDENCE_UNKNOWN = "unknown"  # receipt unreadable — no relationship at all

# Teardown status
TEARDOWN_VERIFIED = "verified"
TEARDOWN_UNVERIFIED = "unverified"  # signed claims show teardown incomplete
TEARDOWN_UNKNOWN = "unknown"

# Provenance status
PROVENANCE_PROVISIONED = "provisioned"  # key_id recorded; revocation NOT checked offline
PROVENANCE_LOCAL = "local"              # verified offline against a held key
PROVENANCE_UNKNOWN = "unknown"

# Overall artifact status
TRUSTED = "trusted"
UNTRUSTED = "untrusted"
UNVERIFIED = "unverified"

# Presentation statuses (the Status line / JSON "status" field)
STATUS_VERIFIED = "verified"
STATUS_UNTRUSTED = "untrusted"
STATUS_UNVERIFIED = "unverified"
STATUS_CORRUPT = "corrupt"
STATUS_UNSUPPORTED = "unsupported"

GENESIS_HASH = "0" * 64


# ---------------------------------------------------------------------------
# Views — normalized shapes for display
# ---------------------------------------------------------------------------

@dataclass
class LedgerEvent:
    """One event read out of the evidence ledger."""

    event_id: str
    timestamp: str
    event_type: str
    data: dict


@dataclass
class FindingView:
    """One finding normalized for display.

    Accepts BOTH the target Finding schema (run_contract.md §5: finding_id,
    title, severity, evidence_refs, agent_reasoning, confidence) and the
    legacy dict shape (test name + status + assertion) that receipts carry.
    """

    display_id: str
    finding_id: Optional[str]
    title: str
    severity: str
    status: str
    summary: str
    confidence: Optional[float]
    evidence_refs: list[str]
    reproduction: Optional[dict]
    agent_reasoning: Optional[str]
    # Filled in once the evidence ledger is available
    resolved_refs: list[str] = field(default_factory=list)
    missing_refs: list[str] = field(default_factory=list)


@dataclass
class EvidenceBundleView:
    """Outcome of evidence discovery + ledger verification (7B.10)."""

    status: str
    evidence_dir_recorded: Optional[str] = None
    binding: Optional[Any] = None
    chain_ok: bool = False
    chain_error: Optional[str] = None
    digest_checks: list[str] = field(default_factory=list)
    events: dict[str, LedgerEvent] = field(default_factory=dict)
    events_count: int = 0


@dataclass
class TrustContext:
    """Central trust object for inspect/explain (7B.2).

    Carries the parsed receipt plus one status per trust dimension, so the
    UI can always distinguish verified information from untrusted or
    unavailable information.
    """

    receipt: Optional[SignedReceipt] = None
    receipt_version: Optional[int] = None
    schema_status: str = SCHEMA_CORRUPT
    schema_detail: str = ""
    signature_status: str = SIG_UNKNOWN
    signature_detail: str = ""
    provenance_status: str = PROVENANCE_UNKNOWN
    teardown_status: str = TEARDOWN_UNKNOWN
    evidence: EvidenceBundleView = field(default_factory=EvidenceBundleView)
    findings: list[FindingView] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    artifact_status: str = UNTRUSTED

    @property
    def evidence_status(self) -> str:
        return self.evidence.status

    @property
    def status(self) -> str:
        """Overall presentation status (never a casual VERIFIED)."""
        return overall_status(self)

    def trusted(self) -> bool:
        return self.status == STATUS_VERIFIED


def overall_status(trust: TrustContext) -> str:
    """Derive the overall presentation status from the trust dimensions.

    Order matters: structural failure (corrupt/unsupported) dominates,
    then integrity failure (signature/evidence), then the fail-closed
    "could not verify" state.
    """
    if trust.schema_status == SCHEMA_CORRUPT:
        return STATUS_CORRUPT
    if trust.schema_status == SCHEMA_UNSUPPORTED:
        return STATUS_UNSUPPORTED
    if trust.signature_status in (SIG_INVALID, SIG_UNSIGNED):
        return STATUS_UNTRUSTED
    if trust.evidence.status == EVIDENCE_INVALID:
        return STATUS_UNTRUSTED
    if trust.signature_status == SIG_UNKNOWN:
        return STATUS_UNVERIFIED
    return STATUS_VERIFIED


# ---------------------------------------------------------------------------
# ReceiptReader (7B.1)
# ---------------------------------------------------------------------------

class ReceiptReader:
    """Loads a receipt, validates the schema, verifies the signature.

    Signature verification is OFFLINE by design: the key is resolved from
    an explicit --pubkey or the local key store only. There is no
    control-plane fetch — inspect must never touch the network.
    """

    def load(
        self,
        receipt_path: Path,
        pubkey_path: Optional[Path] = None,
    ) -> TrustContext:
        receipt_path = Path(receipt_path)
        if not receipt_path.exists():
            return TrustContext(
                schema_detail=f"receipt file not found: {receipt_path}",
            )

        try:
            size = receipt_path.stat().st_size
            if size > MAX_RECEIPT_BYTES:
                raise ValueError(
                    f"receipt file too large: {size} bytes (max {MAX_RECEIPT_BYTES})"
                )
            raw = receipt_path.read_bytes()
        except OSError as e:
            return TrustContext(
                schema_detail=f"cannot read receipt file: {e}",
            )

        try:
            text = raw.decode("utf-8")
            data = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
        except UnicodeDecodeError as e:
            return TrustContext(schema_detail=f"receipt is not valid UTF-8: {e}")
        except json.JSONDecodeError as e:
            return TrustContext(schema_detail=f"receipt is not valid JSON: {e}")
        except ValueError as e:
            return TrustContext(schema_detail=str(e))

        if not isinstance(data, dict):
            return TrustContext(
                schema_detail=(
                    f"receipt root must be a JSON object, got {type(data).__name__}"
                )
            )

        receipt_dict = data.get("receipt", data)

        try:
            receipt = SignedReceipt(**receipt_dict)
        except Exception as e:
            if "UNSUPPORTED_RECEIPT_VERSION" in str(e):
                version = receipt_dict.get("receipt_version")
                return TrustContext(
                    receipt_version=version if isinstance(version, int) else None,
                    schema_status=SCHEMA_UNSUPPORTED,
                    schema_detail=(
                        f"receipt_version={version} is not in supported set "
                        f"{list(SUPPORTED_RECEIPT_VERSIONS)} — this receipt was "
                        "produced by a newer protocol than this CLI understands"
                    ),
                )
            return TrustContext(
                schema_detail=f"receipt does not match schema: {e}",
            )

        trust = TrustContext(
            receipt=receipt,
            receipt_version=receipt.receipt_version,
            schema_status=SCHEMA_VALID,
            schema_detail=f"v{receipt.receipt_version}",
        )

        self._verify_signature(trust, receipt, pubkey_path)
        self._derive_provenance(trust, receipt, pubkey_path is not None)
        trust.findings = normalize_findings(receipt.run_report.findings)
        trust.teardown_status = _derive_teardown_status(receipt)
        return trust

    def _verify_signature(
        self,
        trust: TrustContext,
        receipt: SignedReceipt,
        pubkey_path: Optional[Path],
    ) -> None:
        if not receipt.signature or not receipt.public_key_fingerprint:
            trust.signature_status = SIG_UNSIGNED
            trust.signature_detail = "receipt carries no signature"
            return

        public_key = self._resolve_pubkey(receipt, pubkey_path)
        if public_key is None:
            trust.signature_status = SIG_UNKNOWN
            trust.signature_detail = (
                "no public key available — pass --pubkey or verify on the "
                "machine that ran the sandbox"
            )
            return

        from sandbox_isolation import verify_receipt_signature

        ok = verify_receipt_signature(receipt, public_key)
        trust.signature_status = SIG_VALID if ok else SIG_INVALID
        trust.signature_detail = (
            "Ed25519 signature verified against the resolved public key"
            if ok
            else "signature does not match the receipt contents — the receipt "
            "was tampered with, or was signed by a different key"
        )

    def _resolve_pubkey(self, receipt: SignedReceipt, pubkey_path: Optional[Path]):
        """Resolve the verification key OFFLINE: --pubkey flag, then the
        local key store. Never the network."""
        if pubkey_path is not None:
            try:
                from cryptography.hazmat.primitives import serialization
                from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                    Ed25519PublicKey,
                )

                key = serialization.load_pem_public_key(
                    Path(pubkey_path).read_bytes()
                )
                if isinstance(key, Ed25519PublicKey):
                    return key
                return None
            except Exception:
                return None

        fingerprint = receipt.public_key_fingerprint
        if fingerprint:
            key_file = (
                Path.home() / ".config" / "workflo" / "keys" / f"{fingerprint}.pub.pem"
            )
            if key_file.exists():
                try:
                    from cryptography.hazmat.primitives import serialization
                    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                        Ed25519PublicKey,
                    )

                    key = serialization.load_pem_public_key(key_file.read_bytes())
                    if isinstance(key, Ed25519PublicKey):
                        return key
                except Exception:
                    return None
        return None

    def _derive_provenance(
        self,
        trust: TrustContext,
        receipt: SignedReceipt,
        explicit_pubkey: bool,
    ) -> None:
        if receipt.key_id:
            trust.provenance_status = PROVENANCE_PROVISIONED
        elif trust.signature_status == SIG_VALID:
            trust.provenance_status = PROVENANCE_LOCAL


def _reject_duplicate_keys(pairs):
    """object_pairs_hook that rejects duplicate JSON keys — a receipt
    carrying them is structurally suspect (same rule as the outside verifier)."""
    seen = set()
    for key, _ in pairs:
        if key in seen:
            raise ValueError(f"receipt contains duplicate field: {key!r}")
        seen.add(key)
    return dict(pairs)


# ---------------------------------------------------------------------------
# EvidenceReader (7B.1)
# ---------------------------------------------------------------------------

class EvidenceReader:
    """Discovers the evidence bundle, reads the ledger, verifies the chain."""

    def load(
        self,
        receipt_path: Path,
        receipt: SignedReceipt,
        evidence_override: Optional[Path] = None,
    ) -> EvidenceBundleView:
        binding = getattr(receipt, "evidence_binding", None)
        if binding is None:
            return EvidenceBundleView(status=EVIDENCE_NONE)

        recorded = getattr(binding, "evidence_dir", None)
        if evidence_override is not None:
            evidence_dir = (
                Path(evidence_override) if Path(evidence_override).exists() else None
            )
        else:
            evidence_dir = resolve_evidence_dir(Path(receipt_path), receipt)

        if evidence_dir is None:
            return EvidenceBundleView(
                status=EVIDENCE_MISSING,
                evidence_dir_recorded=recorded,
                binding=binding,
            )

        events, chain_ok, chain_error = self._read_ledger(evidence_dir)
        view = EvidenceBundleView(
            evidence_dir_recorded=recorded,
            binding=binding,
            chain_ok=chain_ok,
            chain_error=chain_error,
            events=events,
            events_count=len(events),
        )

        digests = compute_evidence_digests(evidence_dir)
        if digests is None:
            view.status = EVIDENCE_INVALID
            view.digest_checks = [
                chain_error or "evidence bundle is incomplete or its hash chain is broken"
            ]
            return view

        checks = []
        ok = True
        for fld in ("events_count", "events_sha256", "bundle_sha256", "manifest_sha256"):
            expected = getattr(binding, fld)
            actual = digests[fld]
            if expected != actual:
                ok = False
                checks.append(
                    f"MISMATCH {fld}: receipt says {expected}, "
                    f"evidence recomputes {actual}"
                )
            else:
                checks.append(f"OK {fld} matches recomputed digest")
        view.status = EVIDENCE_VALID if ok else EVIDENCE_INVALID
        view.digest_checks = checks
        return view

    def _read_ledger(
        self, evidence_dir: Path
    ) -> tuple[dict[str, LedgerEvent], bool, Optional[str]]:
        """Read events.jsonl into a map by event_id, verifying the hash
        chain inline. Returns (events, chain_ok, chain_error)."""
        events_file = evidence_dir / "events.jsonl"
        if not events_file.exists():
            return {}, False, f"events ledger not found: {events_file}"

        events: dict[str, LedgerEvent] = {}
        prev_hash = GENESIS_HASH
        try:
            with open(events_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError as e:
                        return events, False, f"events ledger is not valid JSON: {e}"
                    required = (
                        "event_id", "timestamp", "event_type", "data",
                        "prev_hash", "event_hash",
                    )
                    if not all(k in record for k in required):
                        return events, False, (
                            "events ledger record is missing required fields"
                        )
                    event_content = (
                        f"{record['event_id']}{record['timestamp']}"
                        f"{record['event_type']}"
                        f"{json.dumps(record['data'], sort_keys=True)}{prev_hash}"
                    )
                    expected = hashlib.sha256(event_content.encode()).hexdigest()
                    if record["event_hash"] != expected:
                        return events, False, (
                            f"event {record['event_id']} hash does not match "
                            "its contents"
                        )
                    if record["prev_hash"] != prev_hash:
                        return events, False, (
                            f"event {record['event_id']} does not link to the "
                            "previous event"
                        )
                    events[record["event_id"]] = LedgerEvent(
                        event_id=record["event_id"],
                        timestamp=record["timestamp"],
                        event_type=record["event_type"],
                        data=record.get("data") or {},
                    )
                    prev_hash = record["event_hash"]
        except OSError as e:
            return events, False, f"cannot read events ledger: {e}"
        return events, True, None


# ---------------------------------------------------------------------------
# Finding normalization + selection
# ---------------------------------------------------------------------------

def normalize_findings(raw_findings: Any) -> list[FindingView]:
    """Normalize receipt findings (legacy dicts or the target Finding
    schema) into display views with stable positional IDs (F-001, ...)."""
    views: list[FindingView] = []
    for i, f in enumerate(raw_findings or [], start=1):
        if not isinstance(f, dict):
            views.append(
                FindingView(
                    display_id=f"F-{i:03d}",
                    finding_id=None,
                    title=str(f),
                    severity="info",
                    status="reported",
                    summary="",
                    confidence=None,
                    evidence_refs=[],
                    reproduction=None,
                    agent_reasoning=None,
                )
            )
            continue
        confidence = f.get("confidence")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            confidence = None
        views.append(
            FindingView(
                display_id=f"F-{i:03d}",
                finding_id=f.get("finding_id"),
                title=str(
                    f.get("title") or f.get("test") or f.get("nodeid")
                    or f.get("name") or "Untitled finding"
                ),
                severity=str(f.get("severity") or "info"),
                status=str(f.get("status") or "reported"),
                summary=str(f.get("summary") or f.get("assertion") or ""),
                confidence=confidence,
                evidence_refs=[str(r) for r in (f.get("evidence_refs") or [])],
                reproduction=(
                    f["reproduction"] if isinstance(f.get("reproduction"), dict) else None
                ),
                agent_reasoning=f.get("agent_reasoning"),
            )
        )
    return views


def select_findings(
    findings: list[FindingView], spec: Optional[str]
) -> Optional[list[FindingView]]:
    """Filter findings by a --finding selector. None spec = no filter.

    Accepts the display ID (F-001), an exact finding_id, or a finding_id
    suffix. Returns None when nothing matches (caller reports a bad
    selector).
    """
    if spec is None:
        return findings
    s = spec.strip()
    if not s:
        return None
    by_display = [f for f in findings if f.display_id == s.upper()]
    if by_display:
        return by_display
    by_id = [f for f in findings if f.finding_id == s]
    if by_id:
        return by_id
    return [f for f in findings if f.finding_id and f.finding_id.endswith(s)]


# ---------------------------------------------------------------------------
# Trust derivation helpers
# ---------------------------------------------------------------------------

def _derive_teardown_status(receipt: SignedReceipt) -> str:
    """Derive teardown status from the SIGNED teardown claims (runtime-aware).

    An honest receipt for a failed execution may carry teardown claims that
    are False — that is teardown UNVERIFIED, not artifact corruption.
    """
    tp = receipt.teardown_proof
    if getattr(tp, "runtime_type", None) == "namespaces":
        claims = (
            tp.processes_terminated,
            tp.cgroup_removed,
            tp.network_namespace_removed,
            tp.workspace_removed,
        )
    else:
        claims = (tp.container_removed, tp.filesystem_removed)
    if all(c is True for c in claims):
        return TEARDOWN_VERIFIED
    if any(c is False for c in claims):
        return TEARDOWN_UNVERIFIED
    return TEARDOWN_UNKNOWN


def _resolve_finding_refs(finding: FindingView, view: EvidenceBundleView) -> None:
    if view.status not in (EVIDENCE_VALID, EVIDENCE_INVALID):
        finding.resolved_refs = []
        finding.missing_refs = list(finding.evidence_refs)
        return
    finding.resolved_refs = [r for r in finding.evidence_refs if r in view.events]
    finding.missing_refs = [r for r in finding.evidence_refs if r not in view.events]


def _artifact_status(trust: TrustContext) -> str:
    overall = overall_status(trust)
    if overall == STATUS_VERIFIED:
        return TRUSTED
    if overall == STATUS_UNVERIFIED:
        return UNVERIFIED
    return UNTRUSTED


def _warnings(trust: TrustContext) -> list[str]:
    warnings: list[str] = []
    if trust.schema_status == SCHEMA_UNSUPPORTED:
        warnings.append(
            "receipt uses a protocol version this CLI does not support — "
            "upgrade workflo to inspect it fully"
        )
    if trust.signature_status == SIG_UNKNOWN:
        warnings.append(
            "signature could not be verified — no public key available "
            "(pass --pubkey or inspect on the machine that ran the sandbox)"
        )
    if trust.signature_status == SIG_INVALID:
        warnings.append(
            "receipt signature is INVALID — the contents do not match the "
            "signature; treat every claim in this receipt as untrusted"
        )
    if trust.evidence.status == EVIDENCE_INVALID:
        warnings.append(
            "evidence chain is INVALID — the bundle was altered after "
            "signing or is incomplete; affected evidence is untrusted"
        )
    if trust.evidence.status == EVIDENCE_MISSING:
        warnings.append(
            "evidence bundle not found — receipt claims are "
            "signature-covered but the ledger could not be re-verified"
        )
    if trust.evidence.status == EVIDENCE_NONE:
        warnings.append(
            "receipt carries no evidence binding (legacy receipt) — the "
            "audit trail is the signed lifecycle events only"
        )
    if trust.provenance_status == PROVENANCE_PROVISIONED:
        key_id = trust.receipt.key_id if trust.receipt else None
        warnings.append(
            f"key provenance recorded (key_id={key_id}) — revocation status "
            "is NOT checked offline"
        )
    return warnings


# ---------------------------------------------------------------------------
# Composition (7B.2): both readers feed the TrustContext
# ---------------------------------------------------------------------------

def build_trust_context(
    receipt_path,
    pubkey_path: Optional[Path] = None,
    evidence_override: Optional[Path] = None,
) -> TrustContext:
    """Load a receipt + its evidence into a single TrustContext."""
    receipt_path = Path(receipt_path)
    trust = ReceiptReader().load(receipt_path, pubkey_path)
    if trust.receipt is not None:
        trust.evidence = EvidenceReader().load(
            receipt_path, trust.receipt, evidence_override
        )
        for finding in trust.findings:
            _resolve_finding_refs(finding, trust.evidence)
    trust.artifact_status = _artifact_status(trust)
    trust.warnings = _warnings(trust)
    return trust


# ---------------------------------------------------------------------------
# Shared display helpers
# ---------------------------------------------------------------------------

def wrap(text: Any, width: int = 64, indent: str = "  ") -> list[str]:
    wrapped = textwrap.wrap(str(text), width=width) or [""]
    return [f"{indent}{ln}" for ln in wrapped]
