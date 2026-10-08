"""Run orchestrator — the agent team, made explicit.

The supervisor's lifecycle IS the orchestration; this module gives it the
role taxonomy the product speaks in (Provisioner, Ingestor, Executor,
Explorer, Judge, Notary) and enforces the single most important cost
rule):

    only the Explorer may call the model.
    The Judge may call the model LATER (selective confirmation); v1 is
    deterministic. Nobody else ever does.

Each role declares:
  - stages it owns (run-contract names)
  - uses_model: whether it may touch inference at all
  - execute(supervisor): the real work — delegates to the supervisor's
    proven stage implementations (no behavior is re-implemented here)

RunOrchestrator.plan() returns the ordered role/stage map the console and
the audit trail can render; execute() runs it for real when a caller opts
into orchestrator-driven runs (the Supervisor.run() path remains the
canonical lifecycle — this layer adds role visibility, not a second
engine).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:  # avoid import cycles at module load
    from sandbox_runtime.supervisor import Supervisor


@dataclass(frozen=True)
class Role:
    name: str
    stages: tuple[str, ...]
    uses_model: bool
    description: str


# The team. Order is the run order.
PROVISIONER = Role(
    "provisioner",
    ("preflight", "config", "rootfs", "isolation", "probes"),
    uses_model=False,
    description="create sandbox, apply security, prove isolation",
)
INGESTOR = Role(
    "ingestor",
    ("snapshot", "deps"),
    uses_model=False,
    description="acquire repo at exact commit, snapshot, resolve dependencies",
)
EXECUTOR = Role(
    "executor",
    ("tests", "app"),
    uses_model=False,
    description="install, start, probe the application",
)
EXPLORER = Role(
    "explorer",
    ("agent",),
    uses_model=True,
    description="model-driven governed testing of the running app",
)
JUDGE = Role(
    "judge",
    ("judge",),
    uses_model=False,  # v1: deterministic confirmation over ledger records
    description="turn reproduced, localized failures into findings",
)
NOTARY = Role(
    "notary",
    ("teardown", "receipt"),
    uses_model=False,
    description="evidence, teardown verification, receipt payload (unsigned)",
)

ROLES: tuple[Role, ...] = (PROVISIONER, INGESTOR, EXECUTOR, EXPLORER, JUDGE, NOTARY)


@dataclass
class RoleRun:
    """Execution record for one role within a run."""
    role: Role
    events: list[str] = field(default_factory=list)


class RunOrchestrator:
    """Orders the roles and answers 'who may do what' for a run."""

    def __init__(self, roles: tuple[Role, ...] = ROLES):
        self.roles = roles

    def plan(self) -> list[dict]:
        """The ordered role/stage map (what the console renders)."""
        return [
            {
                "role": role.name,
                "stages": list(role.stages),
                "uses_model": role.uses_model,
                "description": role.description,
            }
            for role in self.roles
        ]

    def role_for_stage(self, stage: str) -> Optional[Role]:
        for role in self.roles:
            if stage in role.stages:
                return role
        return None

    def may_use_model(self, stage: str) -> bool:
        """The cost-control invariant: only the explorer stage may infer."""
        role = self.role_for_stage(stage)
        return bool(role and role.uses_model)


# ---------------------------------------------------------------------------
# Dispatch: role -> supervisor stage implementations (thin, honest adapters)
# ---------------------------------------------------------------------------

async def execute_role(supervisor: "Supervisor", role: Role) -> None:
    """Run one role against a Supervisor instance.

    Dispatches to the supervisor's existing, tested stage implementations.
    The orchestrator adds ROLE SEPARATION (and the model-access rule), not
    a parallel lifecycle.
    """
    if role.name == "provisioner":
        await supervisor._preflight()
        supervisor._validate_config()
        await supervisor._build_rootfs()
        await supervisor._create_isolation()
        await supervisor._run_probes()
    elif role.name == "ingestor":
        await supervisor._snapshot_repo()
        await supervisor._resolve_deps()
    elif role.name == "executor":
        from sandbox_runtime.workloads import run_test_workload
        from sandbox_runtime.workloads.app import run_app_workload
        test_result = await run_test_workload(supervisor.config, supervisor.evidence)
        supervisor._last_test_result = test_result
        supervisor.register_process("test", test_result.get("proc"))
        if any(t in supervisor.config.probe_groups
               for t in ("web", "security", "deep", "aggressive")):
            app_result = await run_app_workload(supervisor.config, supervisor.evidence)
            supervisor.register_process("app", app_result.get("proc"))
    elif role.name == "explorer":
        from sandbox_runtime.workloads import run_agent_workload
        agent_result = await run_agent_workload(supervisor.config, supervisor.evidence)
        supervisor.register_process("agent", agent_result.get("proc"))
        supervisor.agent_activity = agent_result.get("activity")
    elif role.name == "judge":
        from sandbox_runtime.judge import judge_findings
        judged = judge_findings(
            getattr(supervisor, "_last_agent_records_full", []),
            supervisor._tool_event_ids,
        )
        supervisor._findings = judged.findings
    elif role.name == "notary":
        await supervisor._teardown()
        await supervisor._build_receipt()
    else:  # pragma: no cover - defensive
        raise ValueError(f"unknown role {role.name!r}")
