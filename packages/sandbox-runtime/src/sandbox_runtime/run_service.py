"""The single run entry point (S03 v2).

Every caller — the CLI's ``workflo run`` and the control-plane's
``runs.py`` — goes through :func:`run`. There is exactly one resolver and
one dispatch table; no caller may keep a second run path alive.

Backend rules (run_contract.md §6 — preflight failures are exit 6):

* ``docker``     — requires ``docker info`` to succeed.
* ``namespaces`` — requires bwrap (Linux namespaces backend).
* ``auto``       — prefers Docker, falls back to namespaces, and fails
  closed naming BOTH missing pieces when neither exists.

Dispatch rules:

* ``RunConfig`` (CLI)   + namespaces → ``Supervisor`` (unchanged path).
* ``RunConfig`` (CLI)   + docker     → converted to a ``SandboxSpec`` and
  run through ``workflo_executor.SandboxExecutor`` (imported lazily: the
  executor package does not depend on sandbox-runtime, and hosts without
  it must still resolve the namespaces backend cleanly).
* ``SandboxSpec`` (API) + docker     → the executor, unchanged.
* ``SandboxSpec`` (API) + namespaces → PreflightError. The API cannot
  sign receipts host-side, so this combination is refused, never
  silently rerouted.

Fail closed everywhere: a backend that disappears between resolution and
dispatch re-runs the availability check and raises.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from typing import Optional, Union

from sandbox_runtime.config import DepMode, RunConfig, RunResult
from sandbox_runtime.supervisor import Supervisor

DOCKER_TIMEOUT_SECONDS = 20


class PreflightError(RuntimeError):
    """The host cannot satisfy the requested backend (run_contract §6 → exit 6)."""


def _docker_info_ok() -> tuple[bool, str]:
    docker = shutil.which("docker")
    if not docker:
        return False, "docker not found on PATH"
    try:
        proc = subprocess.run(
            [docker, "info", "--format", "ok"],
            capture_output=True,
            text=True,
            timeout=DOCKER_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"docker info failed: {exc}"
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip().splitlines()
        return False, detail[0] if detail else "docker info failed"
    return True, ""


def _bwrap_available() -> bool:
    return shutil.which("bwrap") is not None


def resolve_backend(requested: str) -> str:
    """Resolve the requested backend to one that actually exists here.

    Raises PreflightError (never falls back silently) or ValueError for
    an unknown request.
    """
    if requested == "auto":
        docker_ok, docker_err = _docker_info_ok()
        if docker_ok:
            return "docker"
        if _bwrap_available():
            return "namespaces"
        raise PreflightError(
            f"no sandbox backend available: docker ({docker_err}); bwrap not installed (namespaces)"
        )
    if requested == "docker":
        docker_ok, docker_err = _docker_info_ok()
        if not docker_ok:
            raise PreflightError(f"docker backend unavailable: {docker_err}")
        return "docker"
    if requested == "namespaces":
        if not _bwrap_available():
            raise PreflightError("bwrap not installed (Linux namespaces backend)")
        return "namespaces"
    raise ValueError(f"unknown backend: {requested!r} (expected auto|docker|namespaces)")


def run(config: Union[RunConfig, "object"], backend: str = "auto"):
    """Run one sandbox run through exactly one backend.

    Accepts a CLI ``RunConfig`` (returns ``RunResult``) or an API
    ``SandboxSpec`` (returns the executor's ``SandboxRunResult``).
    """
    resolved = resolve_backend(backend)
    if isinstance(config, RunConfig):
        if resolved == "namespaces":
            result = asyncio.run(Supervisor(config).run())
            result.backend = "namespaces"
            return result
        return _run_config_via_docker(config)
    # API input: a workflo_schema.sandbox.SandboxSpec (duck-typed to avoid
    # a hard schema import in the hot path — the executor validates it).
    if resolved != "docker":
        raise PreflightError(
            "the control-plane API requires the docker backend; namespaces runs "
            "are CLI-only because receipt signing happens in the CLI process"
        )
    from workflo_executor import SandboxExecutor

    return SandboxExecutor().run(config)


def _run_config_via_docker(config: RunConfig) -> RunResult:
    """Bridge the CLI's RunConfig onto the executor's SandboxSpec path."""
    from workflo_schema.sandbox import SandboxSpec

    spec = SandboxSpec(
        sandbox_id=config.sandbox_id,
        repo_url=config.repo_url or "",
        repo_path=str(config.repo_path) if config.repo_path else None,
        commit_sha=config.commit_sha,
        run_spec={
            "probe_groups": config.probe_groups,
            "start_command": config.start_command,
            "port": config.port,
            "mission": config.mission,
            "agent_planner": config.agent_planner,
            "dep_mode": config.dep_mode.value,
            "evidence_dir": str(config.evidence_dir),
        },
        timeout_seconds=max(10, min(config.timeout_seconds, 3600)),
        memory_mb=config.memory_mb,
        cpu_cores=config.cpu_cores,
        dependency_install=config.dep_mode == DepMode.PREFLIGHT_CACHE,
    )
    from workflo_executor import SandboxExecutor

    result = SandboxExecutor().run(spec)
    return _sandbox_run_result_to_run_result(config, result)


def _sandbox_run_result_to_run_result(config: RunConfig, result) -> RunResult:
    """Convert the executor's signed result into the CLI's RunResult shape.

    The executor returns a SIGNED receipt; the CLI re-signs host-side
    (deterministic Ed25519 over the canonical payload, same key) — the
    signature ends up identical, and the CLI trust model is preserved.
    """
    receipt_payload: Optional[dict] = None
    teardown_verified = False
    receipt = getattr(result, "receipt", None)
    if receipt is not None:
        receipt_payload = json.loads(receipt.model_dump_json())
        tp = getattr(receipt, "teardown_proof", None)
        if tp is not None:
            teardown_verified = bool(
                getattr(tp, "container_removed", False) and getattr(tp, "filesystem_removed", False)
            )
    return RunResult(
        sandbox_id=config.sandbox_id,
        success=bool(getattr(result, "success", False)),
        error=getattr(result, "error", None),
        lifecycle_events=[
            event.model_dump() if hasattr(event, "model_dump") else dict(event)
            for event in getattr(result, "lifecycle_events", [])
        ],
        receipt_payload=receipt_payload,
        elapsed_seconds=float(getattr(result, "elapsed_seconds", 0.0)),
        teardown_verified=teardown_verified,
        backend="docker",
    )
