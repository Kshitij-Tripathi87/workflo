"""Live run state — what the local console reads while a run is happening.

The supervisor's evidence ledger is write-mostly and final; the console
needs the opposite: a tiny, always-current snapshot. This module maintains
`<run_dir>/run_state.json` — rewritten atomically on every lifecycle event:

    {
      "sandbox_id": ..., "stage": "agent", "status": "running",
      "started_at": ..., "updated_at": ...,
      "stages": {"preflight": "pass", ..., "agent": "active"},
      "agent": {"tool_calls": 12, "denied": 1, ...},     # latest known
      "findings": {"confirmed": 1, "reported": 0},
      "recent_events": [ ... last N ... ]
    }

Budget discipline: the file stays under ~4 KB — recent events are capped
and details are truncated summaries. It is A VIEW, never evidence: nothing
reads it for trust decisions; the receipt + ledger remain the authority.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Optional

# The run contract stage order — drives the console's checklist rendering.
STAGE_ORDER = (
    "preflight", "config", "snapshot", "deps", "rootfs", "isolation",
    "probes", "tests", "app", "agent", "teardown", "receipt",
)

MAX_RECENT_EVENTS = 25
MAX_DETAIL_CHARS = 160


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _truncate_detail(detail: Any) -> Any:
    if not isinstance(detail, dict):
        return detail
    out = {}
    for key, value in detail.items():
        if isinstance(value, str) and len(value) > MAX_DETAIL_CHARS:
            out[key] = value[: MAX_DETAIL_CHARS - 3] + "..."
        elif isinstance(value, (list, dict)):
            out[key] = "(structured)"  # keep the console file small
        else:
            out[key] = value
    return out


class RunStateWriter:
    """Maintains the live run_state.json; one instance per run."""

    def __init__(self, run_dir: Path):
        self.run_dir = Path(run_dir)
        self.path = self.run_dir / "run_state.json"
        self.state: dict[str, Any] = {
            "sandbox_id": self.run_dir.name,
            "stage": "preflight",
            "status": "running",
            "started_at": _utc_now(),
            "updated_at": _utc_now(),
            "started_monotonic": time.monotonic(),
            "stages": {},
            "agent": None,
            "findings": {"confirmed": 0, "reported": 0},
            "recent_events": [],
        }
        self.run_dir.mkdir(parents=True, exist_ok=True)
        try:
            self._flush()
        finally:
            # The monotonic counter must never be serialized.
            self.state.pop("started_monotonic", None)

    # ------------------------------------------------------------------ events

    def on_stage(self, stage: str, phase: str = "active") -> None:
        """Mark a stage active/pass/fail."""
        self.state["stage"] = stage
        self.state["stages"][stage] = phase
        self._touch()

    def on_event(self, event: str, detail: dict) -> None:
        recent = self.state["recent_events"]
        recent.append({
            "event": event,
            "at": _utc_now(),
            "detail": _truncate_detail(detail),
        })
        del recent[:-MAX_RECENT_EVENTS]
        # Agent summaries flow through the same channel.
        if event == "AGENT_REPORTED":
            self.state["agent"] = {
                "tool_calls": detail.get("tool_calls", 0),
                "denied_attempts": detail.get("denied_attempts", 0),
                "steps_total": detail.get("steps_total", 0),
                "steps_completed": detail.get("steps_completed", 0),
                "steps_failed": detail.get("steps_failed", 0),
            }
        elif event == "FINDINGS_JUDGED":
            self.state["findings"] = {
                "confirmed": detail.get("confirmed", 0),
                "reported": detail.get("reported", 0),
            }
        self._touch()

    def finish(self, status: str, failure_stage: Optional[str] = None) -> None:
        self.state["status"] = status  # completed | failed
        if failure_stage:
            self.state["failure_stage"] = failure_stage
            self.state["stages"][failure_stage] = "fail"
        self._touch()

    # ------------------------------------------------------------------ io

    def _touch(self) -> None:
        self.state["updated_at"] = _utc_now()
        self._flush()

    def _flush(self) -> None:
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.state, indent=2, default=str),
                       encoding="utf-8")
        os.replace(tmp, self.path)


def load_run_state(path: Path) -> Optional[dict]:
    """Read a run_state.json; None when absent/corrupt (console is best-effort)."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) and "stage" in data else None
    except (OSError, json.JSONDecodeError):
        return None


def find_latest_run(runs_dir: Path) -> Optional[Path]:
    """The most recently updated run_state.json under the runs directory."""
    runs_dir = Path(runs_dir)
    if not runs_dir.is_dir():
        return None
    candidates = sorted(
        runs_dir.glob("*/run_state.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def render_console(state: dict) -> str:
    """Render the local console view from a run state dict."""
    lines = []
    lines.append(f"WORKFLO  {state.get('sandbox_id', '?')}")
    mission_agent = state.get("agent") or {}
    lines.append(f"status: {state.get('status', '?')}   stage: {state.get('stage', '?')}")
    lines.append("")

    stages = state.get("stages", {})
    for stage in STAGE_ORDER:
        mark = {"pass": "✓", "fail": "✗", "active": "●"}.get(
            stages.get(stage), "·"
        )
        lines.append(f"  {mark} {stage.upper()}")
    lines.append("")

    if mission_agent:
        lines.append(
            "Agent: {tool_calls} tool calls, {denied_attempts} denied, "
            "{steps_completed}/{steps_total} steps met".format(**{
                "tool_calls": mission_agent.get("tool_calls", 0),
                "denied_attempts": mission_agent.get("denied_attempts", 0),
                "steps_total": mission_agent.get("steps_total", 0),
                "steps_completed": mission_agent.get("steps_completed", 0),
            })
        )
    findings = state.get("findings", {})
    if findings.get("confirmed") or findings.get("reported"):
        lines.append(
            f"Findings: {findings.get('confirmed', 0)} confirmed, "
            f"{findings.get('reported', 0)} reported"
        )
    lines.append("")
    recent = state.get("recent_events", [])
    if recent:
        lines.append("Recent:")
        for evt in recent[-8:]:
            lines.append(f"  {evt.get('event')}")
    return "\n".join(lines)
