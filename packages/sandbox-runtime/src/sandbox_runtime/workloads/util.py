"""Shared helpers for sandbox workloads."""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def cgroup_procs_for(run_config) -> Optional[Path]:
    """cgroup.procs path for a RunConfig, or None when no cgroup exists.

    Workloads join the sandbox cgroup via this path so memory/cpu/pids
    limits are enforced on the sandboxed process tree (see bwrap.run_bwrap).
    """
    cgroup_path = getattr(run_config, "cgroup_path", None)
    if cgroup_path is None:
        return None
    return Path(cgroup_path) / "cgroup.procs"
