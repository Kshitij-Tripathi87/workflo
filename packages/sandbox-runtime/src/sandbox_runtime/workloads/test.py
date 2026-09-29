"""Test sandbox workload - runs pytest/Vitest/etc."""

from __future__ import annotations

import asyncio
import json
import subprocess
import time
from pathlib import Path

from sandbox_runtime.config import BwrapConfig, RunConfig, WorkloadType, NetworkMode
from sandbox_runtime.bwrap import run_bwrap
from sandbox_runtime.seccomp import get_seccomp_profile
from sandbox_runtime.landlock import rules_for_workload
from sandbox_runtime.evidence import EvidenceCollector
from sandbox_runtime.workloads.util import cgroup_procs_for


async def run_test_workload(config: RunConfig, evidence: EvidenceCollector) -> dict:
    """Run test suite in isolated sandbox.

    Only the evidence *artifacts* directory is bound into the sandbox
    (at /workflo/artifacts) — the hash-chained ledger (events.jsonl),
    logs and traces stay host-side so the sandbox cannot tamper with
    them. Everything the test run writes to /workflo/artifacts therefore
    lands in the hash-covered artifacts directory.
    """

    # Host-side directories for this sandbox run
    run_dir = evidence.evidence_dir.parent
    workspace = run_dir / "workspace"
    tmp = run_dir / "tmp"
    home = run_dir / "home"

    # Build test command based on probe groups
    test_cmd = _build_test_command(config.probe_groups)

    bwrap_config = BwrapConfig(
        sandbox_id=f"{config.sandbox_id}-test",
        workload_type=WorkloadType.TEST,
        readonly_root=config.runtime_image,
        workspace_dir=workspace,
        evidence_dir=evidence.artifacts_dir,
        tmp_dir=tmp,
        home_dir=home,
        memory_mb=config.memory_mb,
        cpu_cores=config.cpu_cores,
        network_mode=NetworkMode.NONE,
        seccomp_profile=get_seccomp_profile(WorkloadType.TEST),
        landlock_rules=(
            rules_for_workload(WorkloadType.TEST)
            if getattr(config, "landlock_requested", False) else []
        ),
        landlock_mode=getattr(config, "security_mode", "compatible"),
        command=test_cmd,
        env={
            "WORKFLO_SANDBOX_ID": config.sandbox_id,
            "PROBE_GROUPS": json.dumps(config.probe_groups),
            # Runtime site-packages first (pytest + json-report plugin),
            # then the repo under test.
            "PYTHONPATH": "/opt/workflo/site:/workspace/repo",
            "PATH": "/usr/bin:/bin",
            "HOME": "/home/workflo",
        },
        workdir="/workspace/repo",
        cgroup_procs=cgroup_procs_for(config),
    )

    started = time.monotonic()
    proc = run_bwrap(bwrap_config)

    # Drain pipes via communicate() — a bare wait() would risk deadlock
    # once the pytest JSON report grows past the pipe buffer size.
    loop = asyncio.get_event_loop()
    try:
        stdout, stderr = await loop.run_in_executor(
            None, lambda: proc.communicate(timeout=config.timeout_seconds)
        )
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        raise TimeoutError(f"Tests timed out after {config.timeout_seconds}s")

    duration = time.monotonic() - started

    # Parse test results — the report was written by the sandbox process
    # to /workflo/artifacts/pytest-report.json, which is the host-side
    # artifacts dir bound into the sandbox.
    results = _parse_test_output(evidence.artifacts_dir, stdout, stderr, proc.returncode)

    evidence.write_event("TESTS_COMPLETED", {
        "returncode": proc.returncode,
        "total": results.get("total", 0),
        "passed": results.get("passed", 0),
        "failed": results.get("failed", 0),
    })

    # Write test output as artifact
    evidence.write_artifact("test_stdout.txt", stdout or b"")
    evidence.write_artifact("test_stderr.txt", stderr or b"")

    return {
        "proc": proc,
        "pid": proc.pid,
        "returncode": proc.returncode,
        "duration_seconds": duration,
        **results,
    }


def _build_test_command(probe_groups: list) -> list[str]:
    """Build test command based on probe groups."""
    cmd = ["python", "-m", "pytest", "-v", "--json-report", "--json-report-file=/workflo/artifacts/pytest-report.json"]

    # Add markers based on probe groups
    if "deep" in probe_groups or "aggressive" in probe_groups:
        # Model-generated tests will be in tests/
        pass

    return cmd


def _parse_test_output(artifacts_dir: Path, stdout: bytes, stderr: bytes, returncode: int) -> dict:
    """Parse pytest JSON report from the host-side artifacts directory."""

    results = {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "collection_error": None}

    report_path = artifacts_dir / "pytest-report.json"
    if report_path.exists():
        try:
            data = json.loads(report_path.read_text())
            summary = data.get("summary", {})
            results["total"] = summary.get("total", 0)
            results["passed"] = summary.get("passed", 0)
            results["failed"] = summary.get("failed", 0)
            results["skipped"] = summary.get("skipped", 0)
        except Exception:
            results["collection_error"] = "pytest JSON report existed but could not be parsed"
    else:
        # Nonzero exit with no report = collection failure (mirrors the
        # Docker executor's RunReport.collection_error semantics).
        if returncode != 0:
            results["collection_error"] = (
                f"pytest exited {returncode} without producing a JSON report"
            )

    return results
