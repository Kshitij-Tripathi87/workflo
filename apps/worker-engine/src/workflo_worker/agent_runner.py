"""Agent runner — the agent loop executed INSIDE the sandbox.

Two modes:

  task-spec (default): reads a task spec written host-side, executes each
  step through the governed ToolGateway, writes a report.

  planner (WORKFLO_AGENT_PLANNER=1): batch-driven by a HOST-side LLM
  planner through a file protocol in the shared artifacts directory.
  The host planner writes plan.json (a batch of governed steps); this
  runner executes it through the gateway, writes observations.json back,
  and waits for the next batch. The LLM decides WHAT to probe; the
  sandbox decides WHAT IT IS ALLOWED to do. The planner can request;
  only the gateway executes.

Discipline mirrors the receipt's three-state conventions:

  - A failed step is a valid, reportable OUTCOME (observation), not an
    infra crash. A broken app produces failing observations; the agent
    still completes and the receipt records the activity.
  - An infra crash (task spec missing, unexpected exception) exits
    nonzero and the workload raises — the run fails closed.

Standard library only.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from workflo_worker.agent_tools import ToolGateway, ToolDenied

ARTIFACTS_DIR = Path("/workflo/artifacts")
TASK_PATH = ARTIFACTS_DIR / "agent_task.json"
REPORT_PATH = ARTIFACTS_DIR / "agent_report.json"
RECORDS_PATH = ARTIFACTS_DIR / "agent_tool_calls.jsonl"
APP_LOG_PATH = Path("/workspace/app.log")

# Planner-mode protocol files (shared artifacts bind)
PLAN_PATH = ARTIFACTS_DIR / "plan.json"
OBSERVATIONS_PATH = ARTIFACTS_DIR / "observations.json"

MAX_OBSERVATIONS = 500
MAX_BATCH_STEPS = 12

# Planner mode: how long to wait for the next plan batch before giving
# up gracefully (the host planner writes a done-plan on failure, so a
# timeout here is a backstop, not the normal exit).
PLANNER_POLL_TIMEOUT = float(os.environ.get("WORKFLO_AGENT_PLANNER_TIMEOUT", "90"))
PLANNER_POLL_INTERVAL = 0.2


def load_task(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"agent task spec not found: {path}")
    task = json.loads(path.read_text())
    if not isinstance(task, dict) or "steps" not in task:
        raise ValueError("agent task spec must be an object with a 'steps' list")
    return task


def execute_step(gateway: ToolGateway, step: dict) -> dict:
    """Execute one task step; return an observation (never raises)."""
    tool = str(step.get("tool", ""))
    args = step.get("args", {}) or {}
    expect = step.get("expect", {}) or {}
    description = step.get("description", f"{tool} {args.get('url') or args.get('path') or ''}".strip())

    try:
        record = gateway.call(tool, args)
    except ToolDenied as e:
        return {
            "description": description,
            "tool": tool,
            "ok": False,
            "denied": True,
            "detail": f"denied: {e.reason}",
        }

    if record.get("denied"):
        return {
            "description": description,
            "tool": tool,
            "ok": False,
            "denied": True,
            "detail": f"denied: {record.get('reason')}",
        }

    summary = record.get("result_summary", {})
    ok = _evaluate_expectations(summary, expect)
    return {
        "description": description,
        "tool": tool,
        "ok": ok,
        "denied": False,
        "detail": _step_detail(summary),
    }


def _evaluate_expectations(summary: dict, expect: dict) -> bool:
    """Evaluate the step's 'expect' block against the tool result summary.

    Supported: status (int), status_not (int), contains (str in body_preview).
    An empty expect block means "observation only" — OK unless the call
    itself errored (a connection failure IS a failed observation, e.g.
    the app being down).
    """
    if summary.get("error") is not None or summary.get("ok") is False:
        return False

    if not expect:
        return True

    if "status" in expect and summary.get("status") != expect["status"]:
        return False
    if "status_not" in expect and summary.get("status") == expect["status_not"]:
        return False
    if "contains" in expect:
        if expect["contains"] not in str(summary.get("body_preview", "")):
            return False
    return True


def _step_detail(summary: dict) -> str:
    status = summary.get("status")
    error = summary.get("error")
    if error:
        return str(error)
    if status is not None:
        return f"HTTP {status}"
    return "ok"


def _write_report(gateway: ToolGateway, observations: list, task_id,
                  planner_mode: bool, note: str = None) -> None:
    report = {
        "task_id": task_id,
        "mode": "planner" if planner_mode else "task_spec",
        "steps_total": len(observations),
        "steps_completed": sum(1 for o in observations if o["ok"]),
        "steps_failed": sum(1 for o in observations if not o["ok"]),
        "tool_calls": gateway.tool_calls,
        "denied_attempts": gateway.denied_attempts,
        "errors": gateway.errors,
        "tools_used": gateway.tools_used,
        "observations": observations[:MAX_OBSERVATIONS],
    }
    if note:
        report["note"] = note
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True))


def _run_task_spec_mode() -> int:
    task = load_task(TASK_PATH)
    gateway = ToolGateway(RECORDS_PATH, app_log_path=APP_LOG_PATH)

    observations = []
    for step in task.get("steps", [])[:MAX_OBSERVATIONS]:
        observations.append(execute_step(gateway, step))

    _write_report(gateway, observations, task.get("task_id"), planner_mode=False)
    return 0


def _wait_for_plan(last_seq: int, deadline: float) -> dict:
    """Poll for the next plan batch with seq > last_seq. Returns the plan
    or None when the poll timeout lapses (graceful exit)."""
    while time.monotonic() < deadline:
        try:
            if PLAN_PATH.exists():
                plan = json.loads(PLAN_PATH.read_text())
                if plan.get("seq", 0) > last_seq:
                    return plan
        except (json.JSONDecodeError, OSError):
            pass  # partially-written plan; keep polling
        time.sleep(PLANNER_POLL_INTERVAL)
    return None


def _run_planner_mode() -> int:
    """Batch-driven by the host-side LLM planner.

    Protocol: host writes plan.json {"seq": N, "done": bool, "steps": []};
    this runner executes the batch through the governed gateway, writes
    observations.json {"seq": N, "observations": [...], "tool_calls": n}
    and waits for seq N+1. done=true ends the session.
    """
    gateway = ToolGateway(RECORDS_PATH, app_log_path=APP_LOG_PATH)
    task_id = os.environ.get("WORKFLO_SANDBOX_ID", "planner")

    observations: list = []
    last_seq = 0
    deadline = time.monotonic() + PLANNER_POLL_TIMEOUT
    note = None

    while True:
        plan = _wait_for_plan(last_seq, deadline)
        if plan is None:
            note = "planner poll timeout — no further plan batches received"
            break

        last_seq = plan.get("seq", last_seq + 1)

        for step in plan.get("steps", [])[:MAX_BATCH_STEPS]:
            observation = execute_step(gateway, step)
            observations.append(observation)

        # Report observations for this batch back to the host planner
        OBSERVATIONS_PATH.write_text(json.dumps({
            "seq": last_seq,
            "tool_calls": gateway.tool_calls,
            "denied_attempts": gateway.denied_attempts,
            "observations": observations[:MAX_OBSERVATIONS],
        }, sort_keys=True))

        if plan.get("done"):
            note = "planner finished"
            break

        deadline = time.monotonic() + PLANNER_POLL_TIMEOUT

    _write_report(gateway, observations, task_id, planner_mode=True, note=note)
    return 0


def main() -> int:
    if os.environ.get("WORKFLO_AGENT_PLANNER") == "1":
        return _run_planner_mode()
    return _run_task_spec_mode()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except FileNotFoundError as e:
        print(f"agent_runner: {e}", file=sys.stderr)
        sys.exit(3)
    except Exception as e:
        print(f"agent_runner: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(2)
