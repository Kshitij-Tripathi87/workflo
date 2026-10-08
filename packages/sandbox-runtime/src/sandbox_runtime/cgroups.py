"""cgroups v2 resource limits for sandbox."""

from __future__ import annotations

from pathlib import Path

from sandbox_runtime.config import CgroupConfig

WORKFLO_CGROUP_ROOT = Path("/sys/fs/cgroup/workflo")


def _enable_controllers(cgroup_dir: Path) -> None:
    """Enable domain controllers on a cgroup so its CHILDREN get control files.

    cgroup v2 quirk: a child directory only shows memory.*/cpu.*/pids.*
    files when the parent's cgroup.subtree_control enables them — and
    writing to a nonexistent memory.max surfaces as EACCES, not ENOENT.
    """
    subtree = cgroup_dir / "cgroup.subtree_control"
    try:
        subtree.write_text("+memory +cpu +io +pids")
    except OSError:
        # Already enabled (or owned by systemd) — fine as long as the
        # child ends up with control files; that is verified by the caller.
        pass


def setup_cgroup(config: CgroupConfig) -> Path:
    """Create cgroup for sandbox, apply limits, return cgroup path."""
    # Two-level chain: /sys/fs/cgroup/workflo/<sandbox_id>. Controllers
    # must be enabled at each level so the leaf gets control files.
    workflo_root = config.cgroup_root / "workflo"
    workflo_root.mkdir(parents=True, exist_ok=True)
    _enable_controllers(config.cgroup_root)
    _enable_controllers(workflo_root)

    cgroup_path = workflo_root / config.sandbox_id
    cgroup_path.mkdir(exist_ok=True)

    # Fail loudly and EARLY if the leaf lacks control files (delegation
    # misconfiguration) — writing limits below would EACCES cryptically.
    if not (cgroup_path / "memory.max").exists():
        raise RuntimeError(
            f"cgroup {cgroup_path} has no memory.max — controllers are not "
            "enabled in the parent subtree_control. On systemd hosts, ensure "
            "'memory cpu pids' appear in "
            f"{workflo_root}/cgroup.subtree_control."
        )

    # Memory limit
    (cgroup_path / "memory.max").write_text(f"{config.memory_mb}M")
    (cgroup_path / "memory.swap.max").write_text("0")  # No swap

    # CPU limit (quota/period)
    period = 100000  # 100ms
    quota = int(config.cpu_cores * period)
    (cgroup_path / "cpu.max").write_text(f"{quota} {period}")

    # PIDs limit
    (cgroup_path / "pids.max").write_text(str(config.pids_max))

    # I/O weight — best-effort: some hosts delegate without the io
    # controller; the run must not fail over a nicety.
    try:
        (cgroup_path / "io.weight").write_text(f"default {config.io_weight}")
    except OSError:
        pass

    return cgroup_path


def attach_process(cgroup_path: Path, pid: int) -> None:
    """Attach process to cgroup."""
    (cgroup_path / "cgroup.procs").write_text(str(pid))


def cleanup_cgroup(cgroup_path: Path) -> None:
    """Remove cgroup (must be empty)."""
    try:
        cgroup_path.rmdir()
    except OSError:
        pass  # May have child cgroups or processes still attached


def get_cgroup_stats(cgroup_path: Path) -> dict:
    """Read current cgroup stats for monitoring."""
    stats = {}
    try:
        stats["memory_current"] = (cgroup_path / "memory.current").read_text().strip()
        stats["memory_max"] = (cgroup_path / "memory.max").read_text().strip()
        stats["cpu_stat"] = (cgroup_path / "cpu.stat").read_text().strip()
    except Exception:
        pass
    return stats