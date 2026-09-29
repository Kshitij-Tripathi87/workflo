"""The Judge — deterministic finding confirmation from governed observations.

The Explorer decides WHERE to look. The Judge decides what the evidence
actually PROVES. It never asks the model for a verdict: confirmation is a
deterministic function of the recorded tool calls, so a "confirmed"
finding carries ledger authority, not model confidence.

Confirmation rule (v1) for HTTP observations:

    hypothesis H(method, path): "this endpoint is broken"

    H is CONFIRMED when:
      1. the same endpoint failed with the same failure class at two or
         more DISTINCT points in the run (the agent reproduced it), AND
      2. at least one DIFFERENT endpoint on the same base URL answered
         successfully (the app was alive — the failure is localized,
         not "the app was down").

    Otherwise H is REPORTED (observed, not yet proven).

Only governed-tool records count. Denied calls never count as evidence —
a blocked attempt proves nothing about the application.

Input shape: the ``agent_tool_calls.jsonl`` records the ToolGateway writes
(each with seq/tool/args/result_summary), plus the ledger event IDs the
supervisor assigned to them, so every finding can name its evt_* evidence.
Findings conform to workflo_schema.results.Finding.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urlparse

# HTTP status classes that constitute a FAILURE of the endpoint itself.
# 4xx is deliberately excluded: a 404/405 can be correct behavior; only the
# mission context could say otherwise, and the deterministic Judge does not
# guess. Connection-level failures (status None with an error) DO count:
# an endpoint that refuses connections while siblings serve is broken.
_SERVER_ERROR_MIN = 500

_SEVERITY_BY_STATUS_CLASS = {
    "conn_error": "medium",
    "5xx": "medium",
}


@dataclass
class _EndpointObservation:
    seq: int
    method: str
    base: str          # scheme://host:port
    path: str          # path (+ query), the identity of the endpoint
    status: Optional[int]
    failure_class: Optional[str]   # "5xx" | "conn_error" | None


@dataclass
class JudgeReport:
    findings: list[dict] = field(default_factory=list)
    hypotheses: int = 0
    confirmed: int = 0
    reported: int = 0


def _method_of(tool: str) -> Optional[str]:
    return {"http_get": "GET", "http_post": "POST"}.get(tool)


def _bounded_arg_text(value: Any) -> str:
    """Record args are JSON-encoded by the ToolGateway's bounding — unwrap
    a JSON string scalar back to its text before URL parsing."""
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            if isinstance(decoded, str):
                return decoded
        except (json.JSONDecodeError, TypeError):
            pass
        return value
    return str(value or "")


def _classify(record: dict) -> Optional[_EndpointObservation]:
    """Turn one governed tool record into an endpoint observation, or None
    for non-HTTP tools, denied calls, and errored calls."""
    if record.get("denied"):
        return None
    method = _method_of(record.get("tool", ""))
    if method is None:
        return None
    args = record.get("args") or {}
    url = _bounded_arg_text(args.get("url", ""))
    if not url:
        return None
    summary = record.get("result_summary") or {}
    if not summary.get("ok"):
        return None
    status = summary.get("status")
    error = summary.get("error")
    parsed = urlparse(url)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    base = f"{parsed.scheme}://{parsed.netloc}"

    failure = None
    if status is None and error:
        failure = "conn_error"
    elif isinstance(status, int) and status >= _SERVER_ERROR_MIN:
        failure = "5xx"
    return _EndpointObservation(
        seq=int(record.get("seq", 0)), method=method, base=base,
        path=path, status=status if isinstance(status, int) else None,
        failure_class=failure,
    )


def _finding_id(method: str, path: str, failure_class: str) -> str:
    """Deterministic per underlying issue — stable across runs."""
    digest = hashlib.sha256(
        f"{method} {path} {failure_class}".encode("utf-8")
    ).hexdigest()
    return f"wf-fnd-{digest[:16]}"


def judge_findings(records: list[dict],
                   event_ids: Optional[dict[int, str]] = None) -> JudgeReport:
    """Judge a run's governed tool records. Returns confirmed/reported findings.

    records: raw agent_tool_calls.jsonl entries (dicts).
    event_ids: optional map of record seq -> ledger event id (evt_*), so
               findings can cite their evidence precisely. Without it,
               refs fall back to the record seq within the artifacts file.
    """
    event_ids = event_ids or {}
    observations = [
        obs for obs in (_classify(r) for r in records) if obs is not None
    ]

    # Hypotheses: endpoints that failed at least once.
    by_endpoint: dict[tuple[str, str, str], list[_EndpointObservation]] = {}
    controls: dict[str, list[_EndpointObservation]] = {}
    for obs in observations:
        if obs.failure_class:
            by_endpoint.setdefault(
                (obs.base, obs.method, obs.path), []
            ).append(obs)
        else:
            controls.setdefault(obs.base, []).append(obs)

    report = JudgeReport()
    for (base, method, path), failures in sorted(by_endpoint.items()):
        report.hypotheses += 1
        classes = {f.failure_class for f in failures}
        primary_class = sorted(classes)[0]
        repros = [f for f in failures if f.failure_class == primary_class]
        has_control = any(
            c.path != path for c in controls.get(base, [])
        )
        confirmed = len(repros) >= 2 and has_control

        refs = [
            event_ids.get(f.seq, f"agent_tool_calls.jsonl#seq={f.seq}")
            for f in failures
        ]
        statuses = sorted({f.status for f in failures if f.status is not None})
        status_txt = (
            f"HTTP {statuses[0]}" if statuses else "connection failure"
        )
        title = f"{method} {path} fails ({status_txt})"
        report.findings.append({
            "finding_id": _finding_id(method, path, primary_class),
            "title": title,
            "severity": _SEVERITY_BY_STATUS_CLASS.get(primary_class, "medium"),
            "status": "confirmed" if confirmed else "reported",
            "summary": (
                f"{method} {path} failed {len(failures)} time(s) as "
                f"{status_txt}"
                + ("; reproduced and localized against a healthy sibling "
                   "endpoint" if confirmed else
                   "; not yet reproduced against a healthy control")
            ),
            "evidence_refs": refs,
            "reproduction": {
                "method": method,
                "url": f"{base}{path}",
                "observed_failures": len(failures),
                "failure_class": primary_class,
                "attempt_seqs": [f.seq for f in failures],
            },
        })
        if confirmed:
            report.confirmed += 1
        else:
            report.reported += 1
    return report
