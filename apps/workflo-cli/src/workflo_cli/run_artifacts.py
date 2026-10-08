"""Run artifact materializer — the exit-gate artifact set next to every run.

After the CLI signs the receipt it projects the signed payload plus the
surviving evidence bundle into the run root, so an auditor gets the full
story as plain files:

    <run_root>/
    ├── provenance.json          repo URL + requested ref + immutable SHA +
    │                            snapshot tree digest (what was tested)
    ├── run_state.json           final console snapshot (runbook view; the
    │                            receipt/ledger remain the authority)
    ├── observations.jsonl       per-step agent observations (bounded)
    ├── tool_calls.jsonl         governed tool-call ledger copy
    ├── evidence/                hash-chained ledger + manifest + artifacts
    ├── findings.json            deterministic Judge findings w/ evt refs
    ├── agent_activity.json      governed-agent summary from the receipt
    ├── teardown_attestation.json teardown proof + security attestation
    ├── receipt.json             the SIGNED receipt (Ed25519)
    └── receipt.sig              the raw signature (hex) for detached checks

Every file except receipt.json/receipt.sig is a PROJECTION — modifying one
changes nothing cryptographically signed (the receipt's evidence binding
digests cover the evidence bundle, not these views). Best-effort: a disk
hiccup here must never erase a completed run, so failures warn and move on.
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional


ARTIFACT_MANIFEST_VERSION = 1


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True, default=str),
                    encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(r, sort_keys=True, default=str) + "\n" for r in rows),
        encoding="utf-8",
    )


def materialize_run_artifacts(
    run_root: Path,
    evidence_dir: Optional[Path],
    receipt=None,
    receipt_path: Optional[Path] = None,
) -> list[str]:
    """Project the signed receipt + evidence bundle into the exit-gate set.

    Returns the list of files written. Never raises: the run already
    finished; artifact projection is the last mile and must not eat it.
    """
    written: list[str] = []

    def _warn(msg: str) -> None:
        print(f"run-artifacts: {msg}", file=sys.stderr)

    try:
        run_root.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        _warn(f"cannot create run root {run_root}: {e}")
        return written

    # Signed receipt + detached signature
    if receipt is not None:
        try:
            target = receipt_path or (run_root / "receipt.json")
            target.write_text(receipt.model_dump_json(indent=2), encoding="utf-8")
            written.append(str(target))
            sig_path = run_root / "receipt.sig"
            sig_path.write_text((receipt.signature or "") + "\n", encoding="utf-8")
            written.append(str(sig_path))
        except OSError as e:
            _warn(f"receipt projection failed: {e}")

    if receipt is None:
        return written

    artifacts = evidence_dir / "artifacts" if evidence_dir else None

    # provenance.json — repository provenance is signed into the receipt
    # for git-URL runs; local-path runs record the tree digest instead.
    try:
        repo = getattr(receipt, "repository", None)
        provenance = (
            repo if isinstance(repo, dict) else (repo.model_dump(mode="json") if repo else None)
        ) or {}
        provenance.setdefault("receipt_version", receipt.receipt_version)
        provenance.setdefault("sandbox_id", receipt.sandbox_id)
        _write_json(run_root / "provenance.json", provenance)
        written.append(str(run_root / "provenance.json"))
    except OSError as e:
        _warn(f"provenance projection failed: {e}")

    # findings.json + agent_activity.json
    try:
        _write_json(run_root / "findings.json",
                    {"findings": [
                        f if isinstance(f, dict) else f.model_dump(mode="json")
                        for f in (receipt.run_report.findings or [])
                    ]})
        written.append(str(run_root / "findings.json"))
        activity = getattr(receipt, "agent_activity", None)
        if activity is not None:
            _write_json(
                run_root / "agent_activity.json",
                activity if isinstance(activity, dict)
                else activity.model_dump(mode="json"),
            )
            written.append(str(run_root / "agent_activity.json"))
    except OSError as e:
        _warn(f"findings/activity projection failed: {e}")

    # teardown_attestation.json — teardown proof + canary + security posture
    try:
        sec_att = getattr(receipt, "security_attestation", None)
        _write_json(run_root / "teardown_attestation.json", {
            "teardown_proof": receipt.teardown_proof.model_dump(mode="json"),
            "canary_check": receipt.canary_check.model_dump(mode="json"),
            "security_attestation": (
                sec_att if isinstance(sec_att, (dict, type(None)))
                else sec_att.model_dump(mode="json")
            ),
        })
        written.append(str(run_root / "teardown_attestation.json"))
    except OSError as e:
        _warn(f"teardown attestation projection failed: {e}")

    # tool_calls.jsonl + observations.jsonl — copies of agent-layer outputs
    # (self-reported by the sandboxed agent; the evidence bundle's hashes
    # remain the authority)
    try:
        if artifacts is not None and (artifacts / "agent_tool_calls.jsonl").exists():
            shutil.copyfile(artifacts / "agent_tool_calls.jsonl",
                            run_root / "tool_calls.jsonl")
        else:
            _write_jsonl(run_root / "tool_calls.jsonl", [])
        written.append(str(run_root / "tool_calls.jsonl"))

        observations: list[dict] = []
        if artifacts is not None and (artifacts / "agent_report.json").exists():
            try:
                report = json.loads((artifacts / "agent_report.json").read_text(
                    encoding="utf-8", errors="replace"))
                observations = [
                    o for o in report.get("observations", []) if isinstance(o, dict)
                ]
            except (json.JSONDecodeError, OSError):
                observations = []
        _write_jsonl(run_root / "observations.jsonl", observations)
        written.append(str(run_root / "observations.jsonl"))
    except OSError as e:
        _warn(f"agent artifact projection failed: {e}")

    # run_metrics.json — the cost/benchmark rail (Sprint 4 parallel track).
    # Wall clock from the signed teardown proof; agent + model usage from
    # the signed agent_activity; stage statuses from the live run_state
    # snapshot when present. Costs per run/finding derive from these.
    try:
        activity = getattr(receipt, "agent_activity", None)
        activity_doc = (
            activity if isinstance(activity, dict)
            else (activity.model_dump(mode="json") if activity is not None else None)
        )
        inference = (activity_doc or {}).get("inference_provenance") or None
        run_state: dict = {}
        rs_path = run_root / "run_state.json"
        if rs_path.exists():
            try:
                run_state = json.loads(rs_path.read_text(encoding="utf-8",
                                                         errors="replace"))
            except (json.JSONDecodeError, OSError):
                run_state = {}
        _write_json(run_root / "run_metrics.json", {
            "sandbox_id": receipt.sandbox_id,
            "wall_clock_seconds": receipt.teardown_proof.session_duration_seconds,
            "events_count": receipt.teardown_proof.events_count,
            "findings_count": len(receipt.run_report.findings or []),
            "tests": {
                "total": receipt.run_report.total,
                "passed": receipt.run_report.passed,
                "failed": receipt.run_report.failed,
            },
            "agent": {
                "planner": (activity_doc or {}).get("planner"),
                "tool_calls": (activity_doc or {}).get("tool_calls"),
                "denied_attempts": (activity_doc or {}).get("denied_attempts"),
                "steps_total": (activity_doc or {}).get("steps_total"),
                "steps_completed": (activity_doc or {}).get("steps_completed"),
            } if activity_doc else None,
            "model": {
                "model": inference.get("model"),
                "requests": inference.get("requests"),
                "input_tokens": inference.get("input_tokens"),
                "output_tokens": inference.get("output_tokens"),
                "inference_seconds": inference.get("inference_seconds"),
                "tokens_per_second": (
                    round(
                        (inference.get("input_tokens", 0)
                         + inference.get("output_tokens", 0))
                        / inference["inference_seconds"], 3)
                    if inference and inference.get("inference_seconds")
                    else None
                ),
            } if inference else None,
            "stages": run_state.get("stages"),
        })
        written.append(str(run_root / "run_metrics.json"))
    except OSError as e:
        _warn(f"run metrics projection failed: {e}")

    # manifest: what was projected, when — keeps the set self-describing
    try:
        _write_json(run_root / "artifacts_manifest.json", {
            "version": ARTIFACT_MANIFEST_VERSION,
            "written_at": datetime.now(UTC).isoformat(),
            "sandbox_id": receipt.sandbox_id,
            "files": sorted(Path(w).name for w in written),
        })
        written.append(str(run_root / "artifacts_manifest.json"))
    except OSError as e:
        _warn(f"artifact manifest projection failed: {e}")

    return written
