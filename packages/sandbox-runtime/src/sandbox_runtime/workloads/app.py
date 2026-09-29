"""App sandbox workload — the ApplicationManager stage of the run.

Lifecycle contract (Day 7): start -> watch -> READY | CRASHED | READY_TIMEOUT.

The failure state matters: "the app crashed on boot" tells the user to fix
their start command; "the app never answered on the port" tells them the
port is wrong or the app is slow. Collapsing both into one timeout would
make the launch experience untrustworthy.
"""

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


class AppStartError(RuntimeError):
    """The app failed during startup."""
    failure_state = "START_FAILED"


class AppCrashedError(AppStartError):
    """The app process exited before the port became ready."""
    failure_state = "CRASHED"


class AppReadyTimeoutError(AppStartError):
    """The app kept running but never answered on its port in time."""
    failure_state = "READY_TIMEOUT"


def base_url_for(config: RunConfig) -> str:
    """The canonical in-sandbox URL for the app under test."""
    return f"http://app.workflo.internal:{config.port or 3000}"


async def run_app_workload(config: RunConfig, evidence: EvidenceCollector) -> dict:
    """Start app under test in isolated sandbox."""

    if not config.start_command or not config.port:
        raise ValueError("App workload requires start_command and port")
    
    # Host-side directories for this sandbox run
    run_dir = evidence.evidence_dir.parent
    workspace = run_dir / "workspace"
    tmp = run_dir / "tmp"
    home = run_dir / "home"

    # resolv.conf pointing at the netns dnsmasq
    resolv_conf = run_dir / "resolv.conf"
    if not resolv_conf.exists():
        resolv_conf.write_text("nameserver 10.200.0.1\n")

    # App log: redirect the app's stdout/stderr to the shared workspace
    # (bound into every sandbox at /workspace) so the agent's read_log
    # tool can read it. Also ingested into the host-side evidence logs.
    app_log_path = workspace / "app.log"
    app_log_path.parent.mkdir(parents=True, exist_ok=True)
    app_log = open(app_log_path, "ab", buffering=0)

    bwrap_config = BwrapConfig(
        sandbox_id=f"{config.sandbox_id}-app",
        workload_type=WorkloadType.APP,
        readonly_root=config.runtime_image,
        workspace_dir=workspace,
        evidence_dir=evidence.artifacts_dir,
        tmp_dir=tmp,
        home_dir=home,
        memory_mb=config.memory_mb,
        cpu_cores=config.cpu_cores,
        network_mode=NetworkMode.PRIVATE,
        netns=f"workflo-{config.sandbox_id}",
        resolv_conf=resolv_conf,
        seccomp_profile=get_seccomp_profile(WorkloadType.APP),
        landlock_rules=(
            rules_for_workload(WorkloadType.APP)
            if getattr(config, "landlock_requested", False) else []
        ),
        landlock_mode=getattr(config, "security_mode", "compatible"),
        command=["/bin/sh", "-c", config.start_command],
        env={
            "PORT": str(config.port),
            "WORKFLO_SANDBOX_ID": config.sandbox_id,
            "PATH": "/usr/bin:/bin",
            "HOME": "/home/workflo",
        },
        workdir="/workspace/repo",
        cgroup_procs=cgroup_procs_for(config),
    )

    proc = run_bwrap(bwrap_config, capture=False, stdout_file=app_log,
                     stderr_file=app_log)

    # Wait for health — watching the process, so a boot crash surfaces as
    # CRASHED immediately instead of burning the whole readiness window.
    await _wait_for_health(
        config.port, evidence, proc=proc,
        netns=f"workflo-{config.sandbox_id}",
        app_ip="10.200.0.2",
        app_log_path=app_log_path,
    )

    evidence.write_event("APP_STARTED", {
        "pid": proc.pid, "port": config.port, "base_url": base_url_for(config),
    })

    return {
        "proc": proc,
        "pid": proc.pid,
        "status": "healthy",
        "port": config.port,
        "base_url": base_url_for(config),
        "app_log": app_log,
        "app_log_path": app_log_path,
    }


def _log_tail(app_log_path: Optional[Path], max_bytes: int = 4096) -> str:
    """Best-effort tail of the app log for a crash report."""
    try:
        if app_log_path and Path(app_log_path).exists():
            data = Path(app_log_path).read_bytes()[-max_bytes:]
            return data.decode("utf-8", "replace")
    except OSError:
        pass
    return ""


async def _wait_for_health(port: int, evidence: EvidenceCollector, timeout: int = 30,
                           netns: str = None, app_ip: str = "10.200.0.10",
                           proc=None, app_log_path: Optional[Path] = None) -> None:
    """Wait for app to become healthy, watching for a boot crash.

    CRASHED wins over READY_TIMEOUT: if the process already exited, waiting
    out the timeout would report the wrong failure state and waste the run.

    The app runs inside the sandbox's private network namespace, so it is
    NOT reachable on host loopback. Probe it from inside the netns via
    `ip netns exec` (Linux). Falls back to host loopback only when no
    netns is given (development / mocked runs).
    """
    import socket
    import subprocess as _sp
    start = asyncio.get_event_loop().time()

    def _probe() -> bool:
        if netns:
            probe_cmd = [
                "ip", "netns", "exec", netns,
                "python3", "-c",
                f"import socket; socket.create_connection(('{app_ip}', {port}), timeout=1)",
            ]
            return _sp.run(probe_cmd, capture_output=True).returncode == 0
        try:
            sock = socket.create_connection(("127.0.0.1", port), timeout=1)
            sock.close()
            return True
        except Exception:
            return False

    while asyncio.get_event_loop().time() - start < timeout:
        if proc is not None and proc.poll() is not None:
            tail = _log_tail(app_log_path)
            raise AppCrashedError(
                f"app exited with code {proc.returncode} before port {port} "
                f"became ready. App log tail:\n{tail}"
            )
        if await asyncio.get_event_loop().run_in_executor(None, _probe):
            return
        await asyncio.sleep(0.5)

    raise AppReadyTimeoutError(
        f"App did not become healthy on port {port} within {timeout}s"
    )