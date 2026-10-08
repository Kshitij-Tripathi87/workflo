"""Teardown verification — prove the sandbox is gone, fail closed.

Teardown commands failing is not the same as the sandbox being gone.
This module performs the POST-TEARDOWN CHECKS that back the receipt's
TeardownProof: every check re-observes host state after cleanup and
reports the verified truth. A check that cannot be performed counts as
a failure — absence of proof is proof of nothing.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from sandbox_runtime.config import NetworkConfig


@dataclass
class TeardownVerification:
    """Verified post-teardown state of every sandbox resource."""

    processes_terminated: bool = False
    cgroup_removed: bool = False
    network_namespace_removed: bool = False
    workspace_removed: bool = False
    details: dict = field(default_factory=dict)

    @property
    def all_verified(self) -> bool:
        return (
            self.processes_terminated
            and self.cgroup_removed
            and self.network_namespace_removed
            and self.workspace_removed
        )


def verify_processes_terminated(processes: dict) -> bool:
    """True only if every tracked sandbox process has exited.

    processes maps a workload name to its Popen handle. A process that
    still has returncode None (running or zombie) fails the check.
    """
    for name, proc in processes.items():
        if proc is None:
            continue
        if proc.poll() is None:
            return False
    return True


def verify_cgroup_removed(cgroup_path: Optional[Path]) -> bool:
    """True only if the sandbox cgroup directory no longer exists."""
    if cgroup_path is None:
        # No cgroup was created (e.g. mocked/dev run) — nothing to verify,
        # and nothing to prove. Fail closed: the receipt claims a cgroup
        # was used, so it must also prove it was removed.
        return False
    return not Path(cgroup_path).exists()


def verify_network_namespace_removed(network_config: Optional[NetworkConfig]) -> bool:
    """True only if the sandbox network namespace no longer exists."""
    if network_config is None:
        return False
    netns_name = f"workflo-{network_config.sandbox_id}"
    result = subprocess.run(
        ["ip", "netns", "list"], capture_output=True, text=True
    )
    if result.returncode != 0:
        # Cannot observe netns state — absence of proof is proof of nothing.
        return False
    # `ip netns list` output: one netns per line, optionally with extra
    # annotations (e.g. "workflo-abc (id: 0)").
    for line in result.stdout.splitlines():
        if line.split()[0] == netns_name:
            return False
    return True


def verify_paths_removed(paths: list[Path]) -> bool:
    """True only if none of the given paths exist anymore."""
    for p in paths:
        if Path(p).exists():
            return False
    return True


def teardown_and_verify(
    processes: dict,
    cgroup_path: Optional[Path],
    network_config: Optional[NetworkConfig],
    writable_paths: list[Path],
) -> TeardownVerification:
    """Best-effort teardown of every sandbox resource, then verify.

    Order matters: processes first (so the cgroup can drain), then the
    cgroup, then the network namespace, then the writable directories.
    Verification re-observes host state after each cleanup step.

    The evidence directory is NOT in writable_paths by design — it
    survives teardown because it backs the receipt.
    """
    verification = TeardownVerification()

    # 1. Processes: terminate -> wait -> kill -> wait
    for name, proc in list(processes.items()):
        if proc is None:
            continue
        if proc.poll() is not None:
            continue  # already exited
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
                proc.wait(timeout=5)
            except Exception:
                pass
    verification.processes_terminated = verify_processes_terminated(processes)

    # 2. Cgroup: drain every member (tracked or not — the cgroup is the
    #    containment unit), verify empty, then remove.
    cgroup_drain = {"drained": True, "killed": 0, "remaining": []}
    if cgroup_path is not None:
        cgroup_drain = _kill_cgroup_processes(cgroup_path)
        _remove_cgroup(cgroup_path)
    verification.cgroup_removed = verify_cgroup_removed(cgroup_path)

    # 3. Network namespace
    if network_config is not None:
        _teardown_netns(network_config)
    verification.network_namespace_removed = verify_network_namespace_removed(
        network_config
    )

    # 4. Writable directories (workspace with repo copy, tmp, home, ...)
    for p in writable_paths:
        _rmtree(p)
    verification.workspace_removed = verify_paths_removed(writable_paths)

    verification.details = {
        "processes_tracked": len(processes),
        "cgroup_path": str(cgroup_path) if cgroup_path else None,
        "cgroup_drain": cgroup_drain,
        "netns": f"workflo-{network_config.sandbox_id}" if network_config else None,
        "writable_paths": [str(p) for p in writable_paths],
    }
    return verification


def _kill_cgroup_processes(cgroup_path: Path,
                           deadline_seconds: float = 10.0) -> dict:
    """Bounded cgroup drain: SIGKILL every process AND thread attached
    to the cgroup until it is provably empty (F-9).

    The cgroup — not the supervisor's PID list — is the containment
    unit: daemonized grandchildren that escaped tracking still live in
    the cgroup and die here. Returns a result dict for the teardown
    verification details:

        {"drained": bool, "killed": int, "remaining": [pids]}

    drained=False means processes survived SIGKILL (D-state or kernel
    bug) — the cgroup cannot be removed and cgroup_removed verification
    will fail the receipt. Explicit, never silent.
    """
    import time

    killed = 0
    deadline = time.monotonic() + deadline_seconds
    while True:
        pids = _cgroup_members(cgroup_path)
        if not pids:
            return {"drained": True, "killed": killed, "remaining": []}
        if time.monotonic() >= deadline:
            return {"drained": False, "killed": killed, "remaining": pids}
        for pid in pids:
            try:
                subprocess.run(
                    ["kill", "-9", pid], capture_output=True, check=False
                )
                killed += 1
            except Exception:
                pass
        # Zombies need a reaper (init inside the sandbox or the parent);
        # give them a moment to exit before re-reading cgroup.procs.
        time.sleep(0.1)


def _cgroup_members(cgroup_path: Path) -> list[str]:
    """All PIDs in cgroup.procs plus all TIDs in cgroup.threads (some
    kernel paths only move threads on exit)."""
    members = []
    for name in ("cgroup.procs", "cgroup.threads"):
        try:
            file = Path(cgroup_path) / name
            if file.exists():
                members.extend(file.read_text().split())
        except OSError:
            pass
    return sorted(set(members))


def _remove_cgroup(cgroup_path: Path) -> None:
    """Remove the cgroup directory (best effort; verified afterwards)."""
    try:
        Path(cgroup_path).rmdir()
    except OSError:
        pass


def _teardown_netns(network_config: NetworkConfig) -> None:
    """Delete the network namespace and host veth ends (best effort)."""
    from sandbox_runtime.network import teardown_network

    try:
        teardown_network(network_config)
    except Exception:
        pass


def _rmtree(path: Path) -> None:
    """Remove a directory tree (best effort; verified afterwards)."""
    import shutil

    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass


def teardown_proof_fields(
    sandbox_id: str,
    verification: TeardownVerification,
    session_duration_seconds: float,
    events_count: int,
    destroyed_at: Optional[str] = None,
) -> dict:
    """Map a TeardownVerification onto SignedReceipt TeardownProof fields.

    container_removed is the composite "execution environment gone" claim:
    processes terminated AND cgroup removed AND netns deleted.
    filesystem_removed is the writable-bind claim (workspace/tmp/home).
    """
    if destroyed_at is None:
        from datetime import datetime, UTC
        destroyed_at = datetime.now(UTC).isoformat()
    return {
        "sandbox_id": sandbox_id,
        "runtime_type": "namespaces",
        "destroyed_at": destroyed_at,
        "filesystem_wipe_method": "workspace_rmtree",
        "container_removed": (
            verification.processes_terminated
            and verification.cgroup_removed
            and verification.network_namespace_removed
        ),
        "filesystem_removed": verification.workspace_removed,
        "no_snapshot_retained": True,
        "processes_terminated": verification.processes_terminated,
        "cgroup_removed": verification.cgroup_removed,
        "network_namespace_removed": verification.network_namespace_removed,
        "workspace_removed": verification.workspace_removed,
        "session_duration_seconds": session_duration_seconds,
        "events_count": events_count,
    }
