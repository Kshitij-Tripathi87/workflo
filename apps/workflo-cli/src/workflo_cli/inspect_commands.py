"""workflo inspect - read-only receipt inspector ("What happened?").

Phase 7B: inspect answers "What happened during this run?" from the
signed receipt and its evidence bundle. It is a pure artifact reader:

  * it never executes anything
  * it never mutates the artifacts it reads
  * it never invokes a model and never touches the network

Trust is explicit (7B.2): every section distinguishes verified
information from untrusted or unavailable information, because the
receipt being displayed is a potentially attacker-controlled artifact.

Sections (fixed order, 7B.3):
    verification, execution, tests, agent, security, privacy,
    findings, teardown, evidence, receipt

Exit codes (artifact trust - NOT the run's outcome, 7B.9):
    0  VERIFIED             - artifact verified; warnings may apply
    4  VERIFICATION_FAILED  - untrusted / unverified / corrupt / unsupported
    5  CONFIGURATION_ERROR  - receipt file not found, unknown --finding

A failed EXECUTION with an honest receipt is not a verification failure:
the receipt stays trusted and the failure is reported inside it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import click

from workflo_cli.artifacts import (
    EVIDENCE_INVALID,
    EVIDENCE_MISSING,
    EVIDENCE_NONE,
    EVIDENCE_VALID,
    FindingView,
    PROVENANCE_UNKNOWN,
    SIG_INVALID,
    SIG_UNKNOWN,
    SIG_UNSIGNED,
    SIG_VALID,
    STATUS_VERIFIED,
    TEARDOWN_UNVERIFIED,
    TEARDOWN_VERIFIED,
    TrustContext,
    build_trust_context,
    select_findings,
    wrap,
)
from workflo_cli.exit_codes import (
    EXIT_CONFIGURATION_ERROR,
    EXIT_VERIFIED,
    EXIT_VERIFICATION_FAILED,
)


# ---------------------------------------------------------------------------
# Text rendering (7B.3)
# ---------------------------------------------------------------------------

def _fmt_confidence(confidence: Optional[float]) -> str:
    return f"{confidence:.2f}" if confidence is not None else "(not recorded)"


def _signature_label(trust: TrustContext) -> str:
    if trust.signature_status == SIG_VALID:
        return "valid — Ed25519 signature verified against the resolved public key"
    if trust.signature_status == SIG_INVALID:
        return ("INVALID — signature does not match the receipt contents "
                "(tampered, or signed by a different key)")
    if trust.signature_status == SIG_UNSIGNED:
        return "unsigned — receipt carries no signature"
    return ("UNKNOWN — no public key available (pass --pubkey, or inspect "
            "on the machine that ran the sandbox)")


def _verification_lines(trust: TrustContext) -> list[str]:
    lines = ["VERIFICATION"]
    lines.append(f"  Status: {trust.status.upper()}")
    if trust.receipt is None:
        lines.append(f"  Detail: {trust.schema_detail}")
    else:
        lines.append(f"  Receipt schema: {trust.schema_status} ({trust.schema_detail})")
        lines.append(f"  Receipt signature: {_signature_label(trust)}")
        lines.append(f"  Evidence: {trust.evidence.status}")
        lines.append(f"  Teardown: {trust.teardown_status}")
        if trust.receipt.run_status == "failed":
            lines.append(
                "  Execution: FAILED — this is an honest receipt for a "
                "failed run; execution failure is not receipt invalidity"
            )
        if trust.provenance_status != PROVENANCE_UNKNOWN:
            key_id = trust.receipt.key_id
            lines.append(
                f"  Key provenance: {trust.provenance_status}"
                + (f" (key_id={key_id})" if key_id else "")
                + " — revocation NOT checked offline"
            )
    if trust.warnings:
        lines.append("  Warnings:")
        for w in trust.warnings:
            lines.extend(wrap(f"WARNING: {w}", indent="    "))
    else:
        lines.append("  Warnings: (none)")
    return lines


def _execution_lines(trust: TrustContext) -> list[str]:
    r = trust.receipt
    lines = ["EXECUTION"]
    if r.run_status is None:
        lines.append("  Run status: not recorded (pre-Phase-7 receipt)")
    else:
        lines.append(f"  Run status: {r.run_status}")
    if r.failure_stage:
        lines.append(f"  Failure stage: {r.failure_stage}")
    lines.append(f"  Sandbox: {r.sandbox_id}")
    lines.append(f"  Issued at: {r.issued_at}")
    lines.append(f"  Duration: {r.run_report.duration_seconds:.2f} seconds")
    if r.run_report.collection_error:
        lines.append(f"  Collection error: {r.run_report.collection_error}")
    return lines


def _tests_lines(trust: TrustContext) -> list[str]:
    rr = trust.receipt.run_report
    lines = ["TESTS"]
    lines.append(
        f"  Total: {rr.total}  Passed: {rr.passed}  "
        f"Failed: {rr.failed}  Skipped: {rr.skipped}"
    )
    return lines


def _agent_lines(trust: TrustContext) -> list[str]:
    lines = ["AGENT"]
    aa = trust.receipt.agent_activity
    if aa is None:
        lines.append(
            "  Activity recorded: no — the agent tier was disabled, or the "
            "receipt predates agent recording"
        )
        return lines
    lines.append("  Activity recorded: yes")
    lines.append(f"  Tool calls: {aa.tool_calls}")
    if aa.tools_used:
        lines.append(f"  Tools used: {', '.join(aa.tools_used)}")
    lines.append(
        f"  Steps: {aa.steps_total} total, {aa.steps_completed} completed, "
        f"{aa.steps_failed} failed"
    )
    lines.append(f"  Denied attempts: {aa.denied_attempts}")
    lines.append(f"  Errors: {aa.errors}")
    lines.append(f"  Planner: {aa.planner}")
    if aa.planner_note:
        lines.extend(wrap(f"Planner note: {aa.planner_note}"))
    return lines


def _security_lines(trust: TrustContext) -> list[str]:
    lines = ["SECURITY"]
    att = trust.receipt.security_attestation
    if att is None:
        lines.append("  Attestation: none — receipt predates Phase 6 hardening")
        return lines
    lines.append(f"  Mode: {att.security_mode}")
    ll = att.landlock
    if ll.applied:
        abi = f" (kernel ABI {ll.abi_version})" if ll.abi_version else ""
        lines.append(f"  Landlock: requested + applied{abi}")
    elif ll.requested:
        reason = f" (reason: {ll.reason})" if ll.reason else ""
        lines.append(f"  Landlock: requested but NOT applied{reason}")
    else:
        lines.append("  Landlock: not requested")
    lines.append(f"  cgroup attached: {att.cgroup_attached}")
    lines.append(f"  seccomp applied: {att.seccomp_applied}")
    lines.append(f"  network isolated: {att.network_isolated}")
    return lines


def _privacy_lines(trust: TrustContext) -> list[str]:
    lines = ["PRIVACY"]
    aa = trust.receipt.agent_activity
    prov = aa.inference_provenance if aa else None
    tp = trust.receipt.teardown_proof
    model_teardown = getattr(tp, "model_inference_teardown", None)
    if prov is None and model_teardown is None:
        lines.append(
            "  No hosted inference recorded — no model was involved in "
            "this run (or the receipt predates provenance recording)"
        )
        return lines
    if prov is not None:
        lines.append(
            f"  Source code included in inference: {prov.source_code_included}"
        )
        if prov.gateway_url:
            lines.append(f"  Inference mode: {prov.mode} ({prov.gateway_url})")
        else:
            lines.append(f"  Inference mode: {prov.mode}")
        lines.append(f"  Model: {prov.model}")
        lines.append(
            f"  Inference requests: {prov.requests} "
            f"(observations sent: {prov.observations_sent})"
        )
    if model_teardown is not None:
        lines.append(f"  Model inference torn down: {model_teardown}")
    return lines


def _findings_lines(trust: TrustContext) -> list[str]:
    lines = [f"FINDINGS ({len(trust.findings)})"]
    if not trust.findings:
        lines.append("  (none recorded)")
        return lines
    for f in trust.findings:
        lines.append(
            f"  {f.display_id}  [{f.severity.upper()}] {f.title} — {f.status}"
        )
        if f.summary:
            lines.extend(wrap(f"Summary: {f.summary}", indent="    "))
        if f.confidence is not None:
            lines.append(f"    Confidence: {f.confidence:.2f}")
        if f.evidence_refs:
            lines.append(f"    Evidence: {', '.join(f.evidence_refs)}")
    return lines


def _teardown_lines(trust: TrustContext) -> list[str]:
    lines = ["TEARDOWN"]
    tp = trust.receipt.teardown_proof
    if getattr(tp, "runtime_type", None) == "namespaces":
        lines.append("  Runtime: namespaces")
        lines.append(f"  Processes terminated: {tp.processes_terminated}")
        lines.append(f"  Cgroup removed: {tp.cgroup_removed}")
        lines.append(f"  Network namespace removed: {tp.network_namespace_removed}")
        lines.append(f"  Workspace removed: {tp.workspace_removed}")
    else:
        lines.append("  Runtime: docker")
        lines.append(f"  Container removed: {tp.container_removed}")
        lines.append(f"  Filesystem removed: {tp.filesystem_removed}")
    if getattr(tp, "model_inference_teardown", None) is not None:
        lines.append(f"  Model inference torn down: {tp.model_inference_teardown}")
    lines.append(f"  Destroyed at: {tp.destroyed_at}")
    status_label = {
        TEARDOWN_VERIFIED: "VERIFIED",
        TEARDOWN_UNVERIFIED: "UNVERIFIED",
    }.get(trust.teardown_status, "UNKNOWN")
    lines.append(f"  Status: {status_label}")
    return lines


def _evidence_lines(trust: TrustContext) -> list[str]:
    lines = ["EVIDENCE"]
    view = trust.evidence
    if view.status == EVIDENCE_NONE:
        lines.append(
            "  Binding: none — legacy receipt with no evidence bundle; the "
            "audit trail is the signed lifecycle events only"
        )
        return lines
    if view.status == EVIDENCE_MISSING:
        lines.append(
            f"  Binding: present (evidence dir recorded: "
            f"{view.evidence_dir_recorded})"
        )
        lines.append(
            "  Bundle: NOT FOUND — the evidence bundle could not be "
            "located; its claims are signature-covered but the ledger "
            "could not be re-verified (nothing is fabricated)"
        )
        return lines
    if view.status == EVIDENCE_INVALID:
        lines.append("  Binding: present")
        lines.append(
            "  Bundle: INVALID — the bundle was altered after signing, "
            "or is incomplete"
        )
        expected_n = view.binding.events_count if view.binding else "?"
        lines.append(
            f"  Ledger: {len(view.events)} of {expected_n} events "
            "readable (chain broken)"
        )
        for check in view.digest_checks:
            lines.extend(wrap(check, indent="  "))
        return lines
    lines.append("  Binding: present")
    lines.append("  Bundle: valid")
    lines.append(f"  Evidence dir: {view.evidence_dir_recorded}")
    lines.append(f"  Ledger: {view.events_count} events, chain valid")
    lines.append("  Digest checks:")
    for check in view.digest_checks:
        lines.append(f"    {check}")
    return lines


def _receipt_lines(trust: TrustContext) -> list[str]:
    r = trust.receipt
    lines = ["RECEIPT"]
    lines.append(f"  Version: {trust.receipt_version}")
    lines.append(f"  Signature algorithm: {r.signature_algorithm}")
    if r.public_key_fingerprint:
        lines.append(f"  Public key fingerprint: {r.public_key_fingerprint}")
    if r.key_id:
        lines.append(f"  Key ID: {r.key_id}")
    if r.provisioned_at:
        lines.append(f"  Provisioned at: {r.provisioned_at}")
    if r.device_id:
        lines.append(f"  Device: {r.device_id}")
    lines.append(f"  Issued at: {r.issued_at}")
    return lines


def render_inspect(trust: TrustContext, receipt_label: str) -> str:
    lines = [f"Workflo Inspect — {receipt_label}", ""]
    lines.extend(_verification_lines(trust))
    lines.append("")
    if trust.receipt is None:
        # Corrupt / unsupported: nothing else can be reported honestly.
        lines.append(f"STATUS: {trust.status.upper()}")
        return "\n".join(lines)
    for section in (
        _execution_lines,
        _tests_lines,
        _agent_lines,
        _security_lines,
        _privacy_lines,
        _findings_lines,
        _teardown_lines,
        _evidence_lines,
    ):
        lines.extend(section(trust))
        lines.append("")
    lines.extend(_receipt_lines(trust))
    lines.append("")
    lines.append(f"STATUS: {trust.status.upper()}")
    return "\n".join(lines)


def _ref_detail(ref: str, view) -> list[str]:
    """Finding → evidence ref → observed event, with trust per ref.

    Event contents are only shown as `observed` when the ledger chain
    verified; otherwise the ref is marked untrusted/unavailable and
    nothing is fabricated.
    """
    if view.status == EVIDENCE_INVALID:
        return ["    UNTRUSTED — evidence chain failed verification"]
    if view.status in (EVIDENCE_MISSING, EVIDENCE_NONE):
        return [
            "    NOT AVAILABLE — evidence bundle not found "
            "(recorded in the receipt; never fabricated)"
        ]
    if ref in view.events:
        ev = view.events[ref]
        return [f"    observed: {ev.event_type} @ {ev.timestamp}"]
    return ["    NOT FOUND in ledger (never fabricated)"]


def render_finding_focus(
    trust: TrustContext, receipt_label: str, finding: FindingView
) -> str:
    """Focused finding view (7B.5): Title/Severity/Status/Confidence/
    Evidence/Reproduction/Proof status, establishing
    Finding → Evidence refs → Observed event."""
    view = trust.evidence
    lines = [
        f"Workflo Inspect — {receipt_label} (finding {finding.display_id})",
        "",
    ]

    lines.append("VERIFICATION")
    lines.append(f"  Status: {trust.status.upper()}")
    lines.append(f"  Receipt signature: {_signature_label(trust)}")
    lines.append(f"  Evidence: {view.status}")
    lines.append("")

    lines.append(f"FINDING {finding.display_id}")
    lines.append(f"  Title: {finding.title}")
    lines.append(f"  Severity: {finding.severity}")
    lines.append(f"  Status: {finding.status}")
    lines.append(f"  Confidence: {_fmt_confidence(finding.confidence)}")
    if finding.summary:
        lines.extend(wrap(f"Summary: {finding.summary}"))
    lines.append("")

    lines.append("EVIDENCE")
    if not finding.evidence_refs:
        lines.append("  (no evidence refs recorded)")
    else:
        for ref in finding.evidence_refs:
            lines.append(f"  {ref}")
            lines.extend(_ref_detail(ref, view))
    lines.append("")

    lines.append("REPRODUCTION")
    if finding.reproduction:
        for k, v in finding.reproduction.items():
            lines.extend(wrap(f"{k}: {v}"))
    else:
        lines.append("  (not recorded)")
    lines.append("")

    lines.append("RECORDED AGENT ASSESSMENT")
    if finding.agent_reasoning:
        lines.extend(wrap(finding.agent_reasoning))
    else:
        lines.append("  (not recorded)")
    lines.append("")

    lines.append("PROOF STATUS")
    lines.append(
        f"  Evidence refs: {len(finding.resolved_refs)} resolved, "
        f"{len(finding.missing_refs)} missing"
    )
    chain_label = "valid" if view.chain_ok else (view.chain_error or "unavailable")
    lines.append(f"  Evidence chain: {chain_label}")
    lines.append(f"  Receipt: {trust.status.upper()}")
    lines.append("")
    lines.append(f"STATUS: {trust.status.upper()}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# JSON presentation schema (7B.4) — stable contract, not a raw receipt dump
# ---------------------------------------------------------------------------

def _verification_json(trust: TrustContext) -> dict:
    v = {
        "status": trust.status,
        "schema": trust.schema_status,
        "schema_detail": trust.schema_detail,
        "signature": trust.signature_status,
        "signature_detail": trust.signature_detail,
        "provenance": trust.provenance_status,
    }
    if trust.receipt is None:
        return v
    v["teardown"] = trust.teardown_status
    v["evidence"] = trust.evidence.status
    return v


def _execution_json(trust: TrustContext) -> Optional[dict]:
    r = trust.receipt
    if r is None:
        return None
    return {
        "run_status": r.run_status,
        "failure_stage": r.failure_stage,
        "sandbox_id": r.sandbox_id,
        "issued_at": r.issued_at.isoformat(),
        "duration_seconds": r.run_report.duration_seconds,
        "collection_error": r.run_report.collection_error,
    }


def _tests_json(trust: TrustContext) -> Optional[dict]:
    rr = trust.receipt.run_report if trust.receipt else None
    if rr is None:
        return None
    return {
        "total": rr.total,
        "passed": rr.passed,
        "failed": rr.failed,
        "skipped": rr.skipped,
        "findings_count": len(trust.findings),
    }


def _agent_json(trust: TrustContext) -> Optional[dict]:
    aa = trust.receipt.agent_activity if trust.receipt else None
    if aa is None:
        return None
    return {
        "recorded": True,
        "tool_calls": aa.tool_calls,
        "tools_used": list(aa.tools_used),
        "steps_total": aa.steps_total,
        "steps_completed": aa.steps_completed,
        "steps_failed": aa.steps_failed,
        "denied_attempts": aa.denied_attempts,
        "errors": aa.errors,
        "planner": aa.planner,
        "planner_note": aa.planner_note,
        "inference_provisioned": aa.inference_provenance is not None,
    }


def _security_json(trust: TrustContext) -> Optional[dict]:
    att = trust.receipt.security_attestation if trust.receipt else None
    if att is None:
        return None
    return {
        "mode": att.security_mode,
        "landlock_requested": att.landlock.requested,
        "landlock_applied": att.landlock.applied,
        "landlock_abi_version": att.landlock.abi_version,
        "landlock_reason": att.landlock.reason,
        "cgroup_attached": att.cgroup_attached,
        "seccomp_applied": att.seccomp_applied,
        "network_isolated": att.network_isolated,
        "source_code_included": att.source_code_included,
    }


def _privacy_json(trust: TrustContext) -> Optional[dict]:
    if trust.receipt is None:
        return None
    aa = trust.receipt.agent_activity
    prov = aa.inference_provenance if aa else None
    model_teardown = getattr(trust.receipt.teardown_proof,
                             "model_inference_teardown", None)
    if prov is None and model_teardown is None:
        return None
    doc: dict = {}
    if prov is not None:
        doc.update({
            "source_code_included": prov.source_code_included,
            "inference_mode": prov.mode,
            "inference_model": prov.model,
            "inference_requests": prov.requests,
            "observations_sent": prov.observations_sent,
        })
    if model_teardown is not None:
        doc["model_inference_teardown"] = model_teardown
    return doc


def _finding_json(f: FindingView) -> dict:
    return {
        "id": f.display_id,
        "finding_id": f.finding_id,
        "title": f.title,
        "severity": f.severity,
        "status": f.status,
        "confidence": f.confidence,
        "summary": f.summary,
        "evidence_refs": list(f.evidence_refs),
        "evidence_resolved": list(f.resolved_refs),
        "evidence_missing": list(f.missing_refs),
        "reproduction": f.reproduction,
        "agent_reasoning": f.agent_reasoning,
    }


def _findings_json(
    trust: TrustContext, selected: Optional[list[FindingView]]
) -> Optional[list[dict]]:
    if trust.receipt is None:
        return None
    findings = selected if selected is not None else trust.findings
    return [_finding_json(f) for f in findings]


def _teardown_json(trust: TrustContext) -> Optional[dict]:
    tp = trust.receipt.teardown_proof if trust.receipt else None
    if tp is None:
        return None
    return {
        "runtime": getattr(tp, "runtime_type", None),
        "status": trust.teardown_status,
        "model_inference_teardown": getattr(tp, "model_inference_teardown", None),
        "destroyed_at": tp.destroyed_at.isoformat(),
        "session_duration_seconds": getattr(tp, "session_duration_seconds", None),
    }


def _evidence_json(trust: TrustContext) -> Optional[dict]:
    if trust.receipt is None:
        return None
    view = trust.evidence
    return {
        "status": view.status,
        "recorded_dir": view.evidence_dir_recorded,
        "chain_ok": view.chain_ok,
        "chain_error": view.chain_error,
        "events_count": view.events_count,
        "digest_checks": list(view.digest_checks),
    }


def build_presentation(
    trust: TrustContext, selected: Optional[list[FindingView]] = None
) -> dict:
    """Build the stable presentation schema (7B.4).

    Sections are null when they do not apply (e.g. a corrupt receipt has
    no execution/tests/agent sections); they are never fabricated.
    With `selected`, findings[] is filtered to the selection.
    """
    return {
        "command": "inspect",
        "presentation": "workflo.inspect/1",
        "status": trust.status,
        "receipt_version": trust.receipt_version,
        "verification": _verification_json(trust),
        "execution": _execution_json(trust),
        "tests": _tests_json(trust),
        "agent": _agent_json(trust),
        "security": _security_json(trust),
        "privacy": _privacy_json(trust),
        "findings": _findings_json(trust, selected),
        "teardown": _teardown_json(trust),
        "evidence": _evidence_json(trust),
        "warnings": list(trust.warnings),
    }


# ---------------------------------------------------------------------------
# Command entry point
# ---------------------------------------------------------------------------

def _inspect_exit_code(trust: TrustContext) -> int:
    if trust.status == STATUS_VERIFIED:
        return EXIT_VERIFIED
    return EXIT_VERIFICATION_FAILED


def run_inspect(
    receipt_path: str,
    json_output: bool = False,
    finding_spec: Optional[str] = None,
    pubkey: Optional[str] = None,
    evidence_dir: Optional[str] = None,
) -> tuple[str, int]:
    """Run the inspect analysis. Returns (output, exit_code)."""
    path = Path(receipt_path)
    if not path.exists():
        return (
            f"ERROR: receipt file not found: {receipt_path}",
            EXIT_CONFIGURATION_ERROR,
        )

    trust = build_trust_context(
        path,
        pubkey_path=Path(pubkey) if pubkey else None,
        evidence_override=Path(evidence_dir) if evidence_dir else None,
    )

    selected: Optional[list[FindingView]] = None
    if finding_spec is not None:
        selected = select_findings(trust.findings, finding_spec)
        if not selected:
            available = ", ".join(f.display_id for f in trust.findings) or "(none)"
            return (
                f"ERROR: no finding matches '{finding_spec}' "
                f"(available: {available})",
                EXIT_CONFIGURATION_ERROR,
            )
        if json_output:
            doc = build_presentation(trust, selected)
            return (
                json.dumps(doc, indent=2, sort_keys=True),
                _inspect_exit_code(trust),
            )
        return (
            render_finding_focus(trust, receipt_path, selected[0]),
            _inspect_exit_code(trust),
        )

    if json_output:
        doc = build_presentation(trust)
        return (
            json.dumps(doc, indent=2, sort_keys=True),
            _inspect_exit_code(trust),
        )
    return (render_inspect(trust, receipt_path), _inspect_exit_code(trust))


@click.command("inspect")
@click.argument("receipt", metavar="RECEIPT")
@click.option("--json", "json_output", is_flag=True, default=False,
              help="Emit the stable presentation schema (JSON) instead of text")
@click.option("--finding", "finding_spec", default=None,
              help="Focus on one finding: display ID (F-001), finding_id, "
                   "or finding_id suffix")
@click.option("--pubkey", default=None,
              help="Path to an Ed25519 public key PEM used to verify the "
                   "receipt signature offline (no network fetch is performed)")
@click.option("--evidence", "evidence_dir", default=None,
              help="Path to the evidence bundle directory (default: "
                   "auto-resolve from the receipt)")
def inspect_command(receipt, json_output, finding_spec, pubkey, evidence_dir):
    """Inspect a signed receipt: what happened during this run?

    Read-only artifact analysis (Phase 7B): displays the receipt and
    resolves its evidence bundle. Never executes anything, never mutates
    the artifacts, never invokes a model. Trust is explicit — a tampered
    or unverifiable artifact is reported UNTRUSTED/UNVERIFIED and exits
    non-zero.

    \b
    Exit codes (artifact trust, not the run's outcome):
      0  VERIFIED            - artifact verified (warnings may apply)
      4  VERIFICATION_FAILED - untrusted / unverified / corrupt / unsupported
      5  CONFIGURATION_ERROR - receipt file not found, unknown --finding
    """
    output, code = run_inspect(
        receipt,
        json_output=json_output,
        finding_spec=finding_spec,
        pubkey=pubkey,
        evidence_dir=evidence_dir,
    )
    click.echo(output)
    sys.exit(code)
