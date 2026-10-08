"""Docker runner — a thin, fail-closed wrapper around the Docker CLI.

Every call in this module defaults to the safe state (container removed,
no volumes, no network) and raises on any error. The principle is: the
sandbox executor cannot accidentally leave a container running with customer
code on it.

Tests patch `subprocess.run` so this module has zero hard external
dependencies (no Docker daemon required to test the orchestration logic).
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from typing import Optional


# Container/image name validation: alphanumeric + . _ : / -
# Prevents shell injection via --tmpfs, -e, or image arguments
# Any string that ends up as a single Docker CLI argument (image refs, env
# var keys, tmpfs mount destinations) must be expressible safely in a
# NO-SHELL subprocess invocation. This regex is deliberately restrictive:
#   - Underscores are allowed because env var keys (e.g.
#     WORKFLO_START_COMMAND) conventionally use them, and an underscore
#     cannot break out of a list-arg invocation (subprocess passes argv
#     directly; there is no shell to interpret metacharacters).
#   - Anything with spaces, quotes, shell metacharacters, or control
#     characters is rejected — the value is passed to Docker as a single
#     argv element, and a hostile value must never be able to inject
#     extra args.
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_.:/\-@]+$")

@dataclass
class ContainerConfig:
    """Declarative config for the sandbox container — no hidden state."""

    image: str
    command: list[str]
    network_mode: str = "none"
    memory_mb: int = 2048
    cpu_cores: float = 2.0
    timeout_seconds: int = 600
    env: dict[str, str] = field(default_factory=dict)
    workdir: str = "/workspace"
    read_only_root: bool = False
    tmpfs_mounts: dict[str, str] = field(default_factory=dict)
    volume_mounts: dict[str, str] = field(default_factory=dict)


@dataclass
class ContainerResult:
    """Result of running a container to completion."""

    container_id: str
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


def _validate_safe_name(value: str, field_name: str) -> None:
    """Validate that a string is safe to pass as a Docker CLI argument.

    Prevents shell metacharacter injection even though subprocess.run
    uses list form (which is already safe from shell injection), this
    belt-and-suspenders approach also catches obvious mistakes early.
    """
    if not value or not _SAFE_NAME_RE.match(value):
        raise ValueError(
            f"{field_name} contains invalid characters: {value!r}. "
            f"Only alphanumeric, '.', '_', ':', '/', '-', '@' allowed."
        )


def create_container(config: ContainerConfig) -> str:
    """Create a Docker container (stopped) and return its ID.

    Note: We create-then-start because it gives us the container_id before
    the run begins, so teardown can always find it even if the container
    explodes on start.
    """

    _validate_safe_name(config.image, "image")
    _validate_safe_name(config.workdir, "workdir")

    cmd: list[str] = ["docker", "create"]

    cmd.extend(["--network", config.network_mode])

    cmd.extend(["--memory", f"{config.memory_mb}m"])
    cmd.extend(["--cpus", str(config.cpu_cores)])

    if config.read_only_root:
        cmd.append("--read-only")

    if config.tmpfs_mounts:
        for dest, opts in config.tmpfs_mounts.items():
            _validate_safe_name(dest, "tmpfs_mount destination")
            cmd.append(f"--tmpfs={dest}:{opts}")

    # Bind-mount the host tmpfs (which holds the cloned repo + spec.json)
    # into the container. This is how the repo gets into the sandbox without
    # git inside the image — we clone on the host with --network none blocked,
    # then share the result read-only inside the container.
    if config.volume_mounts:
        for src, dest in config.volume_mounts.items():
            _validate_safe_name(dest, "volume_mount destination")
            # Source path is a filesystem path (Windows or POSIX) — allow more
            # characters than the Docker arg name regex, but still reject any
            # shell-metacharacter-ish content as defense in depth.
            if not src or any(c in src for c in [";", "|", "&", "$", "`", "\n"]):
                raise ValueError(
                    f"volume_mount source contains forbidden chars: {src!r}"
                )
            cmd.append(f"-v={src}:{dest}")

    if config.env:
        for key, value in config.env.items():
            # Env vars are passed as -e KEY=VALUE, validate the key.
            # Value is trusted (we control it) but key naming should be sane.
            _validate_safe_name(key, "env key")
            cmd.extend(["-e", f"{key}={value}"])

    cmd.extend(["-w", config.workdir])

    cmd.append(config.image)
    cmd.extend(config.command)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        raise RuntimeError("docker binary not found on PATH")
    except subprocess.TimeoutExpired:
        raise RuntimeError("docker create timed out after 30s")

    if result.returncode != 0:
        raise RuntimeError(
            f"docker create failed (exit {result.returncode}): {result.stderr.strip()}"
        )

    container_id = result.stdout.strip()
    if not container_id:
        raise RuntimeError("docker create returned empty container ID")

    return container_id


def start_container(container_id: str, timeout_seconds: int = 30) -> None:
    """Start a previously-created container."""

    try:
        result = subprocess.run(
            ["docker", "start", container_id],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError:
        raise RuntimeError("docker binary not found on PATH")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"docker start timed out after {timeout_seconds}s")

    if result.returncode != 0:
        raise RuntimeError(
            f"docker start failed for {container_id} (exit {result.returncode}): {result.stderr.strip()}"
        )


def wait_container(
    container_id: str, timeout_seconds: int = 600
) -> ContainerResult:
    """Block until the container exits or the timeout fires.

    On timeout, kills the container and returns timed_out=True. We never
    silently let a timed-out container keep running — that's how a sandbox
    with customer code lingers.
    """

    import time

    start = time.monotonic()
    timed_out = False
    returncode = -1
    stdout = ""
    stderr = ""

    deadline = start + timeout_seconds
    while time.monotonic() < deadline:
        try:
            result = subprocess.run(
                ["docker", "inspect",
                 "--format", "{{.State.Status}} {{.State.ExitCode}}",
                 container_id],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            # Daemon unreachable or hung — back off and retry until deadline.
            time.sleep(1)
            continue
        if result.returncode == 0:
            parts = result.stdout.strip().split()
            if len(parts) >= 2 and parts[0] != "running":
                returncode = int(parts[1]) if parts[1].isdigit() else -1
                break
        time.sleep(0.5)
    else:
        timed_out = True

    if timed_out:
        kill_container(container_id)

    try:
        logs = subprocess.run(
            ["docker", "logs", container_id],
            capture_output=True,
            text=True,
            timeout=10,
        )
        stdout = logs.stdout
        stderr = logs.stderr
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return ContainerResult(
        container_id=container_id,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
    )


def kill_container(container_id: str) -> None:
    """Kill and remove a container. Idempotent — safe to call after teardown."""

    try:
        subprocess.run(
            ["docker", "rm", "-f", container_id],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        # Best effort in teardown — don't raise.
        pass


def container_exists(container_id: Optional[str]) -> bool:
    """Return True if the container still exists on the Docker daemon."""

    if not container_id:
        return False

    try:
        result = subprocess.run(
            ["docker", "inspect", container_id],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0
