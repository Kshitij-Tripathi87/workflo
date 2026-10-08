"""Public API contract models — the wire-format types for the REST API.

This module is the FROZEN contract between:

  - The control-plane REST API (`apps/control-plane/`)
  - Any frontend / SDK / external client consuming the API
  - The CLI's `--via-api` mode, which round-trips through these types

The CLI's internal `SandboxSpec` (in `sandbox.py`) is intentionally NOT
the same class as `RunRequest` here, even though they overlap heavily:

  - `SandboxSpec` is implementation detail — it can evolve with internal
    concerns (worker image selection, timeout internals, ephemeral mount
    sizing) without breaking external consumers.
  - `RunRequest` is the public contract — every change here is a breaking
    change for any frontend / SDK / external client, so it changes with
    explicit versioning discipline, not by accident.

If you need to add a new field that the CLI computes locally (e.g.
worker image selection), put it on `SandboxSpec` and have
`RunRequest.to_sandbox_spec()` fill it in. Do NOT add it to `RunRequest`
just because the CLI knows the value.

Tests in `packages/core-schema/tests/test_api.py` exercise every example
in `docs/api_contract.md` to keep docs and code from drifting.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


# --------------------------------------------------------------------
# Probe-group vocabulary
# --------------------------------------------------------------------

ProbeGroup = Literal["test", "security", "deep-test", "aggressive-test", "web"]
_VALID_PROBE_GROUPS: frozenset[str] = frozenset({
    "test", "security", "deep-test", "aggressive-test", "web",
})


# --------------------------------------------------------------------
# Request: what the client sends
# --------------------------------------------------------------------

class RunRequest(BaseModel):
    """Wire format for `POST /v1/runs`."""

    repo_url: str = Field(
        description="Git URL to clone inside the sandbox.",
        examples=["https://github.com/example/repo.git"],
    )
    probe_groups: list[ProbeGroup] = Field(
        description="Which probe tiers to run. Must include at least one "
        "functional tier (test | deep-test | aggressive-test | web). "
        "`security` is composable with any functional tier.",
        examples=[["test"], ["test", "security"], ["deep-test"], ["web"]],
    )
    commit_sha: Optional[str] = Field(
        default=None,
        description="Pin a specific commit. None = HEAD at clone time.",
        max_length=64,
    )
    start_command: Optional[str] = Field(
        default=None,
        description="Shell command to launch the app under test. Required "
        "when `web` is in probe_groups.",
    )
    port: Optional[int] = Field(
        default=None,
        description="Local port the app under test will bind to. Required "
        "when `web` is in probe_groups.",
        ge=1,
        le=65535,
    )
    config: Optional[dict[str, Any]] = Field(
        default=None,
        description="Free-form per-run overrides. Currently understood "
        "keys: timeout_seconds (10..3600), memory_mb (256..16384), "
        "cpu_cores (0.5..8.0). Unknown keys are ignored, not rejected.",
    )

    @field_validator("probe_groups")
    @classmethod
    def _at_least_one_probe_group(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError(
                "probe_groups must contain at least one functional tier "
                "(test, deep-test, aggressive-test, web)"
            )
        unknown = [g for g in v if g not in _VALID_PROBE_GROUPS]
        if unknown:
            raise ValueError(
                f"unknown probe_groups: {unknown}. "
                f"Valid: {sorted(_VALID_PROBE_GROUPS)}"
            )
        return v

    def to_sandbox_spec(self) -> "SandboxSpec":
        """Convert this public request to the executor's internal SandboxSpec.

        Raises:
            ValueError: when `web` is in probe_groups but start_command or
                port is missing — fail at spec-validation time, before any
                container is created, with an actionable message.
        """
        from workflo_schema.sandbox import SandboxSpec

        is_web = "web" in self.probe_groups
        if is_web:
            missing = []
            if not self.start_command:
                missing.append("start_command")
            if self.port is None:
                missing.append("port")
            if missing:
                raise ValueError(
                    f"probe_groups includes 'web' but missing required "
                    f"fields: {', '.join(missing)}. Either provide them on "
                    f"the request, or add them to a workflo.yaml in the "
                    f"target repo's root. Failing fast before container "
                    f"creation — same 'fail closed, fail loud' discipline "
                    f"as the rest of the codebase."
                )

        run_spec: dict[str, Any] = {
            "goal": _public_goal(self.probe_groups),
            "markers": [],
            "probe_groups": [_public_to_internal(g) for g in self.probe_groups],
            "env": {},
            "targets": {"include": [], "exclude": []},
            "config": {},
            "artifacts": {},
        }

        cfg = self.config or {}
        sandbox_kwargs: dict[str, Any] = {
            "sandbox_id": str(uuid4()),
            "repo_url": self.repo_url,
            "commit_sha": self.commit_sha,
            "run_spec": run_spec,
            "allowed_egress_hosts": [],
        }

        if is_web:
            run_spec.setdefault("env", {})["WORKFLO_START_COMMAND"] = self.start_command
            run_spec["env"]["WORKFLO_WEB_PORT"] = str(self.port)

        if "timeout_seconds" in cfg:
            sandbox_kwargs["timeout_seconds"] = cfg["timeout_seconds"]
        if "memory_mb" in cfg:
            sandbox_kwargs["memory_mb"] = cfg["memory_mb"]
        if "cpu_cores" in cfg:
            sandbox_kwargs["cpu_cores"] = cfg["cpu_cores"]

        return SandboxSpec(**sandbox_kwargs)


def _public_goal(groups: list[str]) -> str:
    """Pick the public-facing goal string from probe groups."""
    priority = ["aggressive-test", "deep-test", "web", "test"]
    for g in priority:
        if g in groups:
            return g.replace("-test", "")
    return "security" if "security" in groups else "functional"


def _public_to_internal(public: str) -> str:
    """Translate a public probe-group name to the executor's internal name."""
    return {
        "test": "surface",
        "security": "security",
        "deep-test": "deep",
        "aggressive-test": "aggressive",
        "web": "web",
    }[public]


# --------------------------------------------------------------------
# Response: what the API sends back
# --------------------------------------------------------------------

class RunStatus(BaseModel):
    """Wire format for both `POST /v1/runs` (initial) and `GET /v1/runs/{run_id}`.

    Status transitions:
        queued  -> running  -> completed | failed
    """

    run_id: str = Field(
        description="Server-assigned identifier. Returned by POST; used for GET.",
    )
    status: Literal["queued", "running", "completed", "failed"]
    created_at: datetime
    receipt: Optional[dict[str, Any]] = Field(
        default=None,
        description="The full signed receipt. None while status != completed. "
        "Even when tests fail, this is present — the receipt carries the "
        "per-test outcomes; the status field reflects infrastructure, "
        "not test outcomes.",
    )
    error: Optional[str] = Field(
        default=None,
        description="Human-readable error message. Present only when "
        "status == failed AND no receipt was produced (infrastructure "
        "crash, not test failure).",
    )


__all__ = ["ProbeGroup", "RunRequest", "RunStatus"]
