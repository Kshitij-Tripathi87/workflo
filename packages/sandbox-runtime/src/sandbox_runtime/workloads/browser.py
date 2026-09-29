"""Browser worker workload - Playwright with ephemeral profile."""

from __future__ import annotations

import subprocess
import asyncio
from pathlib import Path
from typing import Optional

from sandbox_runtime.config import BwrapConfig, RunConfig, WorkloadType, NetworkMode
from sandbox_runtime.bwrap import run_bwrap
from sandbox_runtime.seccomp import get_seccomp_profile
from sandbox_runtime.landlock import rules_for_workload
from sandbox_runtime.evidence import EvidenceCollector
from sandbox_runtime.workloads.util import cgroup_procs_for


async def run_browser_workload(config: RunConfig, evidence: EvidenceCollector) -> dict:
    """Run Playwright browser probes in isolated sandbox with ephemeral profile."""
    
    if not config.start_command or not config.port:
        raise ValueError("Browser workload requires start_command and port")
    
    # Host-side directories for this sandbox run
    run_dir = evidence.evidence_dir.parent
    workspace = run_dir / "workspace"
    tmp = run_dir / "tmp"

    # Create ephemeral browser profile directory
    browser_profile = run_dir / "browser-profile"
    browser_profile.mkdir(parents=True, exist_ok=True)

    bwrap_config = BwrapConfig(
        sandbox_id=f"{config.sandbox_id}-browser",
        workload_type=WorkloadType.BROWSER,
        readonly_root=config.runtime_image,
        workspace_dir=workspace,
        evidence_dir=evidence.artifacts_dir,
        tmp_dir=tmp,
        home_dir=browser_profile,  # Ephemeral profile
        memory_mb=1024,
        cpu_cores=1.0,
        network_mode=NetworkMode.PRIVATE,
        netns=f"workflo-{config.sandbox_id}",
        seccomp_profile=get_seccomp_profile(WorkloadType.BROWSER),
        landlock_rules=(
            rules_for_workload(WorkloadType.BROWSER)
            if getattr(config, "landlock_requested", False) else []
        ),
        landlock_mode=getattr(config, "security_mode", "compatible"),
        command=["python", "-m", "workflo_worker.browser_runner"],
        env={
            "WORKFLO_SANDBOX_ID": config.sandbox_id,
            "WORKFLO_APP_URL": f"http://app.workflo.internal:{config.port}",
            "PLAYWRIGHT_BROWSERS_PATH": "/opt/playwright",
            "PROBE_GROUPS": '["web"]',
            "PATH": "/usr/bin:/bin",
            "HOME": "/home/workflo",
        },
        workdir="/workspace",
        cgroup_procs=cgroup_procs_for(config),
    )

    proc = run_bwrap(bwrap_config)

    # Wait for completion
    loop = asyncio.get_event_loop()
    try:
        stdout, stderr = await loop.run_in_executor(
            None, lambda: proc.communicate(timeout=config.timeout_seconds)
        )
        returncode = proc.returncode
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        raise TimeoutError(f"Browser workload timed out after {config.timeout_seconds}s")

    evidence.write_event("BROWSER_COMPLETED", {
        "returncode": returncode,
    })

    evidence.write_artifact("browser_stdout.txt", stdout or b"")
    evidence.write_artifact("browser_stderr.txt", stderr or b"")

    # Browser traces/screenshots are written to the artifacts dir (bound
    # into the sandbox at /workflo/artifacts) — hash-covered by the manifest.
    return {"proc": proc, "pid": proc.pid, "returncode": returncode}