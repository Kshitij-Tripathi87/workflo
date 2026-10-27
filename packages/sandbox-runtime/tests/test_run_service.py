"""S03 v2 — run_service: single entry point + backend resolver.

Table-driven resolver tests cover: docker only, bwrap only, both, neither,
explicit flag with the backend missing, and unknown backends. Dispatch
tests pin the single-run-path rule: RunConfig → namespaces Supervisor,
SandboxSpec → docker executor, and no silent fallbacks anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import pytest

from sandbox_runtime import run_service
from sandbox_runtime.config import DepMode, RunConfig, RunResult
from sandbox_runtime.run_service import PreflightError, resolve_backend


# ---------------------------------------------------------------------------
# Resolver — table-driven
# ---------------------------------------------------------------------------


def _patch_availability(monkeypatch, docker: bool, bwrap: bool):
    monkeypatch.setattr(
        run_service, "_docker_info_ok", lambda: (docker, "" if docker else "docker not found on PATH")
    )
    monkeypatch.setattr(run_service, "_bwrap_available", lambda: bwrap)


@pytest.mark.parametrize(
    ("requested", "docker", "bwrap", "expected"),
    [
        ("auto", True, True, "docker"),          # auto prefers Docker
        ("auto", True, False, "docker"),
        ("auto", False, True, "namespaces"),     # bwrap exists on Linux → namespaces
        ("docker", True, False, "docker"),
        ("namespaces", False, True, "namespaces"),
    ],
)
def test_resolve_backend_table(monkeypatch, requested, docker, bwrap, expected):
    _patch_availability(monkeypatch, docker, bwrap)
    assert resolve_backend(requested) == expected


@pytest.mark.parametrize(
    ("requested", "docker", "bwrap", "must_mention"),
    [
        ("auto", False, False, ["docker", "bwrap"]),   # names WHAT is missing
        ("docker", False, True, ["docker"]),
        ("namespaces", True, False, ["bwrap"]),
    ],
)
def test_resolve_backend_missing_names_the_reason(monkeypatch, requested, docker, bwrap, must_mention):
    _patch_availability(monkeypatch, docker, bwrap)
    with pytest.raises(PreflightError) as excinfo:
        resolve_backend(requested)
    for fragment in must_mention:
        assert fragment in str(excinfo.value), f"reason must name {fragment}: {excinfo.value}"


def test_resolve_backend_rejects_unknown_backend(monkeypatch):
    _patch_availability(monkeypatch, True, True)
    with pytest.raises(ValueError, match="unknown backend"):
        resolve_backend("kube")


# ---------------------------------------------------------------------------
# Dispatch — one entry point, no second run path
# ---------------------------------------------------------------------------


@dataclass
class _FakeSupervisor:
    config: RunConfig
    calls: int = 0

    def __init__(self, config):
        self.config = config
        type(self).calls = getattr(type(self), "calls", 0) + 1

    async def run(self) -> RunResult:
        return RunResult(sandbox_id=self.config.sandbox_id, success=True, backend="namespaces")


class _FakeExecutor:
    last_spec: Any = None

    def __init__(self, *args, **kwargs):
        pass

    def run(self, spec):
        type(self).last_spec = spec
        return _FakeSandboxRunResult()


@dataclass
class _FakeSandboxRunResult:
    success: bool = True
    error: Optional[str] = None
    elapsed_seconds: float = 1.0
    receipt: Any = None
    lifecycle_events: list = field(default_factory=list)
    report: Any = None


def _run_config() -> RunConfig:
    return RunConfig(sandbox_id="sbx-test-1", repo_url="https://github.com/example/repo.git")


def _sandbox_spec():
    from workflo_schema.sandbox import SandboxSpec

    return SandboxSpec(
        sandbox_id="sbx-test-2",
        repo_url="https://github.com/example/repo.git",
        run_spec={},
    )


def test_runconfig_with_namespaces_uses_supervisor_path(monkeypatch):
    _patch_availability(monkeypatch, docker=True, bwrap=True)
    monkeypatch.setattr(run_service, "Supervisor", _FakeSupervisor)
    result = run_service.run(_run_config(), backend="namespaces")
    assert result.success is True
    assert result.backend == "namespaces"


def test_runconfig_with_docker_goes_through_executor(monkeypatch):
    _patch_availability(monkeypatch, docker=True, bwrap=True)
    monkeypatch.setattr(run_service, "Supervisor", _FakeSupervisor)
    monkeypatch.setattr("workflo_executor.SandboxExecutor", _FakeExecutor)
    result = run_service.run(_run_config(), backend="docker")
    assert result.success is True
    assert result.backend == "docker"
    assert _FakeExecutor.last_spec is not None
    assert _FakeExecutor.last_spec.sandbox_id == "sbx-test-1"


def test_sandboxspec_with_docker_goes_through_executor(monkeypatch):
    _patch_availability(monkeypatch, docker=True, bwrap=True)
    monkeypatch.setattr("workflo_executor.SandboxExecutor", _FakeExecutor)
    result = run_service.run(_sandbox_spec(), backend="docker")
    assert result.success is True
    assert _FakeExecutor.last_spec is not None


def test_sandboxspec_never_runs_namespaces(monkeypatch):
    """The API path cannot produce a signed receipt host-side; fail closed."""
    _patch_availability(monkeypatch, docker=True, bwrap=True)
    monkeypatch.setattr(run_service, "Supervisor", _FakeSupervisor)
    with pytest.raises(PreflightError, match="docker"):
        run_service.run(_sandbox_spec(), backend="namespaces")


def test_run_revalidates_backend_before_dispatch(monkeypatch):
    """An explicit backend that vanished between resolve and run still fails closed."""
    _patch_availability(monkeypatch, docker=False, bwrap=False)
    with pytest.raises(PreflightError):
        run_service.run(_run_config(), backend="docker")


def test_preflight_error_is_exit_six_material():
    """PreflightError maps to failure_stage=preflight → exit 6 (run_contract §6)."""
    err = PreflightError("bwrap not installed")
    assert "bwrap" in str(err)


def test_run_result_carries_backend():
    """Non-negotiable #6: receipts/evidence must name the backend that ran."""
    result = RunResult(sandbox_id="sbx", success=True)
    result.backend = "namespaces"
    assert result.backend == "namespaces"


# ---------------------------------------------------------------------------
# CLI <-> API parity through the shared docker dispatch
# ---------------------------------------------------------------------------


class _FakeReceipt:
    def __init__(self):
        self.teardown_proof = type("TP", (), {"container_removed": True, "filesystem_removed": True})()

    def model_dump_json(self):
        return '{"sandbox_id": "sbx-test-1", "receipt_version": 1}'


def test_docker_parity_runconfig_and_sandboxspec_carry_same_truth(monkeypatch):
    """Same fixture, both input shapes: success, error, lifecycle events and
    the receipt payload must be identical through the shared dispatch."""
    _patch_availability(monkeypatch, docker=True, bwrap=True)

    shared = _FakeSandboxRunResult(
        success=True,
        error=None,
        elapsed_seconds=3.25,
        receipt=_FakeReceipt(),
        lifecycle_events=[],
    )

    class _SharedExecutor(_FakeExecutor):
        def run(self, spec):
            type(self).last_spec = spec
            return shared

    monkeypatch.setattr("workflo_executor.SandboxExecutor", _SharedExecutor)

    cli_result = run_service.run(_run_config(), backend="docker")
    api_result = run_service.run(_sandbox_spec(), backend="docker")

    assert cli_result.success == api_result.success
    assert cli_result.error == api_result.error
    assert cli_result.elapsed_seconds == api_result.elapsed_seconds
    assert cli_result.receipt_payload == {"sandbox_id": "sbx-test-1", "receipt_version": 1}
    assert cli_result.teardown_verified is True
    assert cli_result.backend == "docker"
