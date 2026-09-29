"""Agent sandbox workload - requests bounded actions via tool gateway.

The agent runs INSIDE the sandbox (bwrap + seccomp + private netns) and
executes a task spec through the governed ToolGateway
(workflo_worker.agent_tools). Every tool call — allowed or denied — is
recorded by the agent to the artifacts directory; this workload then
ingests those records into the HOST-side hash-chained evidence ledger.

Trust boundary: the agent writes its own records (self-reported); the
ledger is host-side and the sandbox cannot tamper with it. The receipt
binds the ledger digests via the evidence binding.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

from sandbox_runtime.config import BwrapConfig, RunConfig, WorkloadType, NetworkMode
from sandbox_runtime.bwrap import run_bwrap
from sandbox_runtime.seccomp import get_seccomp_profile
from sandbox_runtime.landlock import rules_for_workload
from sandbox_runtime.evidence import EvidenceCollector
from sandbox_runtime.workloads.util import cgroup_procs_for

TASK_FILE = "agent_task.json"
REPORT_FILE = "agent_report.json"
RECORDS_FILE = "agent_tool_calls.jsonl"


def build_default_task(config: RunConfig) -> dict:
    """The default agent task: generic probes of the app under test.

    Includes a deliberately out-of-bounds request so the allowlist's
    denial path is exercised on every agent run — an agent trying to
    reach the outside world must be visibly stopped.
    """
    app_url = f"http://app.workflo.internal:{config.port or 3000}"
    return {
        "task_id": config.sandbox_id,
        "steps": [
            {
                "description": "app root responds",
                "tool": "http_get",
                "args": {"url": f"{app_url}/"},
                "expect": {"status": 200},
            },
            {
                "description": "health endpoint responds",
                "tool": "http_get",
                "args": {"url": f"{app_url}/health"},
            },
            {
                "description": "read app log",
                "tool": "read_log",
                "args": {"lines": 50},
            },
            {
                "description": "list repo files",
                "tool": "list_files",
                "args": {"path": "/workspace/repo"},
            },
            {
                "description": "out-of-bounds request must be denied",
                "tool": "http_get",
                "args": {"url": "http://exfiltrate.example.com/steal"},
            },
        ],
    }


def _write_task_spec(config: RunConfig, evidence: EvidenceCollector,
                     task: dict) -> Path:
    """Write the task spec into the shared artifacts directory — the
    agent sandbox reads it at /workflo/artifacts/agent_task.json."""
    task_path = evidence.artifacts_dir / TASK_FILE
    task_path.write_text(json.dumps(task, indent=2, sort_keys=True))
    return task_path


def _activity_from_report(report: dict) -> dict:
    """Map the agent report onto the receipt's AgentActivity fields."""
    return {
        "tool_calls": report.get("tool_calls", 0),
        "tools_used": report.get("tools_used", []),
        "steps_total": report.get("steps_total", 0),
        "steps_completed": report.get("steps_completed", 0),
        "steps_failed": report.get("steps_failed", 0),
        "denied_attempts": report.get("denied_attempts", 0),
        "errors": report.get("errors", 0),
    }


def _bounded_records(records_path: Path) -> list[dict]:
    """Read the agent's tool-call records (bounded fields) for the
    supervisor to emit into the lifecycle/event trail."""
    records = []
    if records_path.exists():
        with open(records_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                records.append({
                    "seq": record.get("seq"),
                    "tool": record.get("tool"),
                    "denied": bool(record.get("denied")),
                    "ok": bool(record.get("ok")),
                    "duration_ms": record.get("duration_ms"),
                })
    return records


def _full_records(records_path: Path) -> list[dict]:
    """Read the COMPLETE governed tool records (args + result summaries).

    These stay inside the evidence pipeline — the Judge consumes them to
    derive findings; they are never copied into the receipt verbatim. The
    records are already bounded by the ToolGateway itself (URL caps, body
    previews, redactions), so no further processing happens here.
    """
    records: list[dict] = []
    if records_path.exists():
        with open(records_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(record, dict):
                    records.append(record)
    return records


async def run_agent_workload(config: RunConfig, evidence: EvidenceCollector) -> dict:
    """Run the agent in an isolated sandbox and ingest its evidence.

    Two modes, decided by config.agent_planner and LLM availability:

      planner (LLM): the agent runs in batch mode; a HOST-side LLM
      planner drives it through the plan/observations file protocol.
      The planner requests; only the sandboxed gateway executes.

      task_spec (fallback): no LLM configured or unreachable — the
      deterministic default task. An unavailable LLM must not fail a
      run whose sandbox and isolation are healthy.
    """

    # Host-side directories for this sandbox run
    run_dir = evidence.evidence_dir.parent
    workspace = run_dir / "workspace"
    tmp = run_dir / "tmp"
    home = run_dir / "home"

    # Planner mode decision: requested AND the endpoint is reachable
    planner_mode = False
    planner_note = None
    planner_events = []  # collected concurrently; supervisor emit()s them
    if getattr(config, "agent_planner", False):
        from sandbox_runtime.planner import llm_config_from_env, llm_available
        cfg = llm_config_from_env()
        if cfg and llm_available(cfg):
            planner_mode = True
        else:
            planner_note = "LLM unavailable - fell back to task-spec mode"

    # Task spec (used by task-spec mode; planner mode ignores it)
    task = build_default_task(config)
    _write_task_spec(config, evidence, task)

    # resolv.conf pointing at the netns dnsmasq — the agent's HTTP tools
    # resolve *.workflo.internal through it (same bind as the probe/app
    # workloads; the rootfs default points at systemd-resolved, which
    # does not exist inside the netns).
    resolv_conf = run_dir / "resolv.conf"
    if not resolv_conf.exists():
        resolv_conf.write_text("nameserver 10.200.0.1\n")

    bwrap_config = BwrapConfig(
        sandbox_id=f"{config.sandbox_id}-agent",
        workload_type=WorkloadType.AGENT,
        readonly_root=config.runtime_image,
        workspace_dir=workspace,
        evidence_dir=evidence.artifacts_dir,
        tmp_dir=tmp,
        home_dir=home,
        memory_mb=512,  # Agent is lightweight
        cpu_cores=0.5,
        network_mode=NetworkMode.PRIVATE,
        netns=f"workflo-{config.sandbox_id}",
        resolv_conf=resolv_conf,
        seccomp_profile=get_seccomp_profile(WorkloadType.AGENT),
        landlock_rules=(
            rules_for_workload(WorkloadType.AGENT)
            if getattr(config, "landlock_requested", False) else []
        ),
        landlock_mode=getattr(config, "security_mode", "compatible"),
        command=["python3", "-m", "workflo_worker.agent_runner"],
        env={
            "WORKFLO_SANDBOX_ID": config.sandbox_id,
            "WORKFLO_APP_URL": f"http://app.workflo.internal:{config.port or 3000}",
            "PROBE_GROUPS": json.dumps(config.probe_groups),
            "PYTHONPATH": "/opt/workflo/runtime",
            "PATH": "/usr/bin:/bin",
            "HOME": "/home/workflo",
            # Planner mode: the runner waits for plan batches
            **({"WORKFLO_AGENT_PLANNER": "1"} if planner_mode else {}),
        },
        workdir="/workspace",
        cgroup_procs=cgroup_procs_for(config),
    )

    proc = run_bwrap(bwrap_config)

    # Wait for completion — with the host-side planner loop running
    # concurrently in planner mode.
    loop = asyncio.get_event_loop()
    planner_future = None
    planner_result = None
    if planner_mode:
        from sandbox_runtime.planner import run_planner_loop

        def _planner_event(note, data):
            planner_events.append({"note": note, **data})

        app_url = f"http://app.workflo.internal:{config.port or 3000}"
        planner_future = loop.run_in_executor(
            None, lambda: run_planner_loop(
                evidence.artifacts_dir, app_url, on_event=_planner_event,
                mission=getattr(config, "mission", None))
        )

    def _communicate():
        return proc.communicate(timeout=config.timeout_seconds)

    communicate_future = loop.run_in_executor(None, _communicate)

    futures = [communicate_future] + ([planner_future] if planner_future else [])
    done, pending = await asyncio.wait(futures, return_when=asyncio.FIRST_EXCEPTION)

    # Surface planner failures early (the planner loop ends gracefully on
    # LLM failure, but an unexpected exception should not be swallowed)
    for f in done:
        exc = f.exception()
        if exc is not None and f is not communicate_future:
            raise RuntimeError(f"planner loop failed: {exc}")
        if f is not communicate_future and planner_future is not None:
            try:
                planner_result = f.result()
            except Exception:
                planner_result = None

    try:
        stdout, stderr = await communicate_future
        returncode = proc.returncode
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        raise TimeoutError(f"Agent timed out after {config.timeout_seconds}s")

    evidence.write_artifact("agent_stdout.txt", stdout or b"")
    evidence.write_artifact("agent_stderr.txt", stderr or b"")

    # The agent exits 0 when it wrote its report — even with failed steps
    # (a broken app is a reportable outcome, not an infra crash).
    if returncode != 0:
        evidence.write_event("AGENT_COMPLETED", {"returncode": returncode})
        raise RuntimeError(
            f"agent crashed (exit {returncode}): "
            f"{(stderr or b'').decode(errors='replace')[:500]}"
        )

    report_path = evidence.artifacts_dir / REPORT_FILE
    records_path = evidence.artifacts_dir / RECORDS_FILE
    if not report_path.exists():
        evidence.write_event("AGENT_COMPLETED", {"returncode": returncode})
        raise RuntimeError("agent exited 0 but produced no report")

    report = json.loads(report_path.read_text())
    activity = _activity_from_report(report)
    activity["planner"] = "llm" if planner_mode else "task_spec"
    # The run's mission is signed into the receipt verbatim (bounded): what
    # the user asked the agent to test. Comes from the run config (and is
    # echoed back by the planner loop when it ran).
    mission = getattr(config, "mission", None)
    if planner_result and planner_result.get("mission"):
        mission = planner_result["mission"]
    if mission:
        activity["mission"] = str(mission)[:512]
    if planner_note:
        activity["planner_note"] = planner_note
    # Hosted-inference provenance (receipt v4): gateway/direct mode, hashes
    # of the bounded observations and model responses, request IDs.
    if planner_result and planner_result.get("inference_provenance"):
        activity["inference_provenance"] = planner_result["inference_provenance"]
    records = _bounded_records(records_path)

    return {
        "proc": proc,
        "pid": proc.pid,
        "returncode": returncode,
        "activity": activity,
        "records": records,
        "records_full": _full_records(records_path),
        "planner_enabled": planner_mode,
        "planner_events": planner_events,
    }
