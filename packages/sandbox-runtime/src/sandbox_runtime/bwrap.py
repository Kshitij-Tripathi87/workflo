"""Bubblewrap command builder and execution.

Two network modes, two launch shapes:

- NetworkMode.NONE (sealed): bwrap ``--unshare-net`` — an anonymous,
  empty network namespace. No interfaces, no routes, no DNS. This is
  the default for test workloads.

- NetworkMode.PRIVATE: bwrap is launched via ``ip netns exec
  workflo-<id>`` and ``--unshare-net`` is OMITTED so the sandbox shares
  the named namespace created by network.py (veth + dnsmasq + nftables
  default-drop). Running bwrap with --unshare-net here would create a
  DIFFERENT anonymous netns and silently bypass all of that.

Seccomp: bwrap's ``--seccomp FD`` takes an inherited file descriptor
containing a compiled classic seccomp-BPF program (as produced by
libseccomp's seccomp_export_bpf) — not a path, not JSON, not syscall
names. run_bwrap compiles the JSON profile via libseccomp, writes the
BPF program to a run-local file, and passes the FD explicitly.

Landlock: when ``config.landlock_rules`` is non-empty, run_bwrap writes
the rules JSON to the run root, RO-binds the standalone wrapper
(landlock_exec.py) and the rules into the sandbox, and rewrites the
command so the wrapper applies the ruleset INSIDE the sandbox process
before exec'ing the real workload (spec §5, F-1). The seccomp profiles
allow the three landlock syscalls for exactly this wrapper.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from sandbox_runtime.config import BwrapConfig, NetworkMode


def build_bwrap_args(config: BwrapConfig, seccomp_fd: int = 3) -> list[str]:
    """Build the bwrap command line (WITHOUT the ip netns exec prefix)."""
    args = ["bwrap"]

    # Namespaces. Network: NONE -> anonymous empty netns; PRIVATE -> we
    # join the named netns via the wrapper, so no --unshare-net here.
    args += ["--unshare-user", "--unshare-pid", "--unshare-ipc",
             "--unshare-uts", "--unshare-cgroup"]
    if config.network_mode == NetworkMode.NONE:
        args += ["--unshare-net"]

    # User namespace identity. bwrap creates the mapping itself when
    # --unshare-user is requested; the uid-map/gid-map options used by
    # older prototype code are not supported by bwrap 0.11.x. Keeping
    # the explicit in-sandbox identity makes the workload contract
    # clear without passing unsupported flags.
    args += ["--uid", "0", "--gid", "0"]

    # Rootfs (read-only base)
    args += ["--ro-bind", str(config.readonly_root), "/"]

    # Writable binds
    args += ["--bind", str(config.workspace_dir), "/workspace"]
    args += ["--bind", str(config.evidence_dir), "/workflo/artifacts"]
    args += ["--bind", str(config.tmp_dir), "/tmp"]
    args += ["--bind", str(config.home_dir), "/home/workflo"]

    # Landlock: RO-bind the in-sandbox wrapper + rules so it can apply
    # the ruleset and exec the real command (F-1). The rules JSON lives
    # at the RUN root next to seccomp.allow — never inside the evidence
    # bundle (its hashes must only cover run outputs).
    if config.landlock_rules:
        args += ["--ro-bind", str(landlock_exec_src(config.readonly_root)), "/workflo/landlock_exec.py"]
        args += ["--ro-bind", str(landlock_rules_path(config)), "/workflo/landlock-rules.json"]

    # Per-run resolv.conf (PRIVATE network mode: point at the netns dnsmasq)
    if config.resolv_conf is not None:
        args += ["--ro-bind", str(config.resolv_conf), "/etc/resolv.conf"]

    # Minimal /dev, /proc, /run
    args += ["--dev", "/dev"]
    args += ["--proc", "/proc"]
    args += ["--tmpfs", "/run"]

    # Seccomp: inherited FD with the allowlist (bwrap reads names from it)
    if config.seccomp_profile is not None:
        args += ["--seccomp", str(seccomp_fd)]

    # Capabilities - drop dangerous ones
    for cap in config.drop_caps:
        args += ["--cap-drop", cap]

    # Working directory
    args += ["--chdir", config.workdir]

    # Environment
    for k, v in config.env.items():
        args += ["--setenv", k, v]

    # Command. With Landlock enabled the real workload is wrapped in the
    # pre-exec applier: the ruleset is applied INSIDE the sandbox process
    # (irreversible, inherited by all descendants) before exec.
    command = list(config.command)
    if config.landlock_rules:
        command = [
            "python3", "/workflo/landlock_exec.py",
            "--rules", "/workflo/landlock-rules.json",
            "--status", f"/workflo/artifacts/landlock-status-{_workload_tag(config)}.json",
            "--",
        ] + command

    args += ["--"] + command

    return args


def build_launch_command(config: BwrapConfig, seccomp_fd: int = 3) -> list[str]:
    """Full launch command, including the ip netns exec prefix if PRIVATE."""
    args = build_bwrap_args(config, seccomp_fd=seccomp_fd)
    if config.network_mode == NetworkMode.PRIVATE:
        if not config.netns:
            raise ValueError(
                "NetworkMode.PRIVATE requires BwrapConfig.netns "
                "(the named namespace created by network.py)"
            )
        return ["ip", "netns", "exec", config.netns] + args
    return args


def run_bwrap(config: BwrapConfig, capture: bool = True,
              stdout_file=None, stderr_file=None) -> subprocess.Popen:
    """Spawn the sandbox process, return the Popen handle.

    With capture=True stdout/stderr are piped so the caller can read
    them via communicate(). NOTE: when capturing, always use
    communicate() to drain the pipes — a bare wait() can deadlock on
    full pipe buffers.

    stdout_file/stderr_file (when capture=False) redirect the sandbox
    process's output to host-side files instead of inheriting the
    parent's streams — used by the app workload so the app-under-test's
    log lands in the shared workspace where the agent's log tool reads it.
    """
    from sandbox_runtime.seccomp import write_bwrap_profile

    pass_fds = ()

    if config.seccomp_profile is not None:
        # Convert JSON profile -> bwrap text allowlist. Stored at the RUN
        # root (parent of the evidence dir), NOT inside the evidence
        # bundle — the bundle's hashes must only cover run outputs.
        seccomp_text_path = config.evidence_dir.parent.parent / "seccomp.allow"
        seccomp_text_path.parent.mkdir(parents=True, exist_ok=True)
        write_bwrap_profile(config.seccomp_profile, seccomp_text_path)

        fd = os.open(str(seccomp_text_path), os.O_RDONLY)
        os.set_inheritable(fd, True)
        pass_fds = (fd,)
        cmd = build_launch_command(config, seccomp_fd=fd)
    else:
        cmd = build_launch_command(config)

    # Landlock rules JSON — written BEFORE the sandbox can read it.
    if config.landlock_rules:
        write_landlock_rules(config)

    kwargs = {}
    if capture:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE
    else:
        if stdout_file is not None:
            # Accept an already-open handle or a path
            kwargs["stdout"] = (
                stdout_file if hasattr(stdout_file, "write")
                else open(stdout_file, "ab", buffering=0)
            )
        if stderr_file is not None:
            kwargs["stderr"] = (
                stderr_file if hasattr(stderr_file, "write")
                else open(stderr_file, "ab", buffering=0)
            )

    # Join the cgroup BEFORE exec: bwrap's launcher forks the sandbox
    # child at startup, so attaching the launcher PID after Popen returns
    # would leave the child outside the cgroup — no limits would apply.
    # The shell writes its own PID to cgroup.procs, then execs bwrap in
    # the same process; the forked child inherits the membership.
    if config.cgroup_procs is not None:
        procs = str(config.cgroup_procs).replace('"', '')
        cmd = ["sh", "-c", f'echo $$ > "{procs}" && exec "$@"', "bwrap-cgroup-join"] + cmd

    try:
        return subprocess.Popen(
            cmd, start_new_session=True, pass_fds=pass_fds, **kwargs
        )
    finally:
        # Popen dup'd the FDs it needs; close our copy in the parent
        for fd in pass_fds:
            os.close(fd)


def landlock_exec_src(readonly_root: Path | None = None) -> Path:
    """Host path of the standalone in-sandbox Landlock wrapper.

    Prefer the immutable runtime image copy over a path in the checked-out
    repository. The latter can be inaccessible to bwrap's nested user
    namespace on hosted runners and is mutable relative to the tested image.
    The package-adjacent path remains a fallback for unit/dev environments
    that have not built the runtime image.
    """
    if readonly_root is not None:
        image_copy = Path(readonly_root) / "workflo" / "landlock_exec.py"
        if image_copy.is_file():
            return image_copy
    from sandbox_runtime import landlock as _landlock
    return Path(_landlock.__file__).parent / "landlock_exec.py"


def landlock_rules_path(config: BwrapConfig) -> Path:
    """Run-root path of the Landlock rules JSON for this sandbox.

    Mirrors the seccomp.allow placement: run root, NOT the evidence
    bundle (bundle hashes must only cover run outputs).
    """
    return config.evidence_dir.parent.parent / "landlock-rules.json"


def _workload_tag(config: BwrapConfig) -> str:
    return getattr(config.workload_type, "value", str(config.workload_type)).lower()


def write_landlock_rules(config: BwrapConfig) -> Path:
    """Serialize the rules JSON the in-sandbox wrapper will apply."""
    import json as _json
    from sandbox_runtime.landlock import ACCESS_NAMES

    payload = {
        "workload": _workload_tag(config),
        "mode": config.landlock_mode,
        "rules": config.landlock_rules,
    }
    # Fail loud on a malformed rule table — an unreadable policy inside
    # the sandbox is fail-closed there; a malformed one here is a bug.
    for rule in config.landlock_rules:
        if rule.get("access") not in ACCESS_NAMES:
            raise ValueError(f"invalid landlock rule access: {rule!r}")
    path = landlock_rules_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json.dumps(payload, indent=2, sort_keys=True))
    return path
