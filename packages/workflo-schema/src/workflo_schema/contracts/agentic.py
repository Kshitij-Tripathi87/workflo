"""Canonical v1 contracts for registered, sandboxed agent execution.

These contracts describe agent identity, mission planning, task grants, and
execution evidence. They do not grant authority by themselves: admission and
the signed sandbox assignment bind the selected profile/plan/grants to one
tenant-scoped attempt. Guest-produced records remain observations until trusted
components validate them.
"""
from __future__ import annotations

from enum import Enum
from pathlib import PurePosixPath
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from workflo_schema.contracts.canonical import digest_of, model_digest
from workflo_schema.contracts.common import CanonicalTimestamp, DigestString, IdString, SCHEMA_VERSION
from workflo_schema.contracts.runspec import RunCreatorV1

__all__ = [
    "AgenticContractError", "AgentRole", "AgentTaskStatus", "AgentActionKind",
    "AgentExecutionStatus", "AgentArtifactKind", "AgentBudgetV1", "AgentProfileRefV1",
    "AgentProfileV1", "AgentToolEffect", "AgentToolDefinitionV1", "AgentProfileRegistryV1",
    "AgenticMissionV1", "AgentTaskV1", "AgentPlanV1", "AgentFilesystemRoot",
    "AgentFilesystemAccess", "AgentFilesystemGrantV1", "AgentCapabilityGrantV1",
    "AgentActionEventV1", "AgentExecutionRecordV1", "AgentArtifactRefV1",
    "validate_plan_against_mission",
]


class AgenticContractError(ValueError):
    """A mission, plan, profile, registry, or grant is not safely bound."""


class AgentRole(str, Enum):
    MISSION_SUPERVISOR = "mission_supervisor"
    INGESTOR = "ingestor"
    EXECUTOR = "executor"
    EXPLORER = "explorer"
    TEST_DESIGNER = "test_designer"
    BROWSER_PROBE = "browser_probe"
    SECURITY_PROBE = "security_probe"
    JUDGE = "judge"
    NOTARY = "notary"


class AgentTaskStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    BLOCKED = "blocked"


class AgentActionKind(str, Enum):
    PROPOSED = "proposed"
    VALIDATED = "validated"
    DENIED = "denied"
    EXECUTED = "executed"
    OBSERVED = "observed"


class AgentExecutionStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    BLOCKED = "blocked"


class AgentArtifactKind(str, Enum):
    TEST_PROPOSAL = "test_proposal"
    GENERATED_TEST = "generated_test"
    REPORT = "report"
    OBSERVATION = "observation"
    MODEL_PROVENANCE = "model_provenance"
    OTHER = "other"


class AgentToolEffect(str, Enum):
    READ_ONLY = "read_only"
    SANDBOX_WRITE = "sandbox_write"
    NETWORK_READ = "network_read"
    NETWORK_WRITE = "network_write"


class AgentFilesystemRoot(str, Enum):
    SOURCE_SNAPSHOT = "source_snapshot"
    WORKSPACE = "workspace"
    GENERATED_TESTS = "generated_tests"
    ARTIFACTS = "artifacts"


class AgentFilesystemAccess(str, Enum):
    READ = "read"
    WRITE = "write"


class AgentBudgetV1(BaseModel):
    """Hard ceilings for one agent or task; units are explicit integers."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_tokens: int = Field(default=0, ge=0, le=2_000_000)
    max_inference_requests: int = Field(default=0, ge=0, le=10_000)
    max_tool_calls: int = Field(default=0, ge=0, le=100_000)
    max_parallel_tasks: int = Field(default=1, ge=1, le=16)
    max_elapsed_ms: int = Field(default=60_000, ge=1_000, le=86_400_000)
    max_cpu_ms: int = Field(default=60_000, ge=0, le=5_184_000_000)
    max_memory_mib: int = Field(default=512, ge=256, le=262_144)
    max_disk_mib: int = Field(default=512, ge=0, le=1_048_576)
    max_output_bytes: int = Field(default=1_048_576, ge=0, le=1_073_741_824)
    max_log_bytes: int = Field(default=262_144, ge=0, le=104_857_600)
    max_retries: int = Field(default=0, ge=0, le=10)

    @model_validator(mode="after")
    def _inference_budget_consistent(self) -> "AgentBudgetV1":
        if self.max_inference_requests > 0 and self.max_tokens == 0:
            raise ValueError("inference requests require a non-zero token budget")
        return self

    def fits_within(self, ceiling: "AgentBudgetV1") -> bool:
        """Whether every requested ceiling is less than or equal to its grant."""
        return all(getattr(self, name) <= getattr(ceiling, name) for name in self.model_fields)


class AgentProfileRefV1(BaseModel):
    """Immutable reference to one exact profile version and its content digest."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_id: IdString
    version: str = Field(min_length=1, max_length=64)
    profile_digest: DigestString


class AgentProfileV1(BaseModel):
    """Approved runtime profile; profile content is immutable once registered."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = SCHEMA_VERSION
    profile_id: IdString
    version: str = Field(min_length=1, max_length=64)
    role: AgentRole
    runtime_bundle_digest: DigestString
    entrypoint: str = Field(min_length=1, max_length=512)
    task_types: tuple[IdString, ...] = Field(min_length=1, max_length=32)
    input_schema_digest: DigestString
    output_schema_digest: DigestString
    tool_ids: tuple[IdString, ...] = Field(default=(), max_length=64)
    delegatable_roles: tuple[AgentRole, ...] = Field(default=(), max_length=8)
    model_profile_id: IdString | None = None
    model_artifact_digests: tuple[DigestString, ...] = Field(default=(), max_length=16)
    budget: AgentBudgetV1
    created_by: RunCreatorV1
    created_at: CanonicalTimestamp

    @field_validator("entrypoint")
    @classmethod
    def _entrypoint_is_relative(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or "\\" in value or ":" in value or any(
            part in {"", ".", ".."} for part in path.parts
        ):
            raise ValueError("agent entrypoint must be a safe relative POSIX path")
        return value

    @model_validator(mode="after")
    def _profile_constraints(self) -> "AgentProfileV1":
        for name in ("task_types", "tool_ids", "delegatable_roles", "model_artifact_digests"):
            values = getattr(self, name)
            if len(set(values)) != len(values):
                raise ValueError(f"{name} must be unique")
        uses_inference = self.budget.max_inference_requests > 0
        if uses_inference and self.model_profile_id is None:
            raise ValueError("inference-enabled profile requires model_profile_id")
        if self.model_profile_id is not None and self.role is not AgentRole.EXPLORER:
            raise ValueError("v1 model access is reserved for the explorer role")
        if self.model_profile_id is not None and not self.model_artifact_digests:
            raise ValueError("model-enabled profile must pin at least one model artifact")
        if self.model_profile_id is None and self.model_artifact_digests:
            raise ValueError("model artifacts require model_profile_id")
        if self.role in {AgentRole.JUDGE, AgentRole.NOTARY} and self.tool_ids:
            raise ValueError("judge and notary profiles cannot receive direct tools")
        return self

    def digest(self) -> str:
        return model_digest(self)

    def reference(self) -> AgentProfileRefV1:
        return AgentProfileRefV1(
            profile_id=self.profile_id, version=self.version, profile_digest=self.digest()
        )


class AgentToolDefinitionV1(BaseModel):
    """Versioned typed tool registry entry; implementation remains guest-side."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_id: IdString
    version: str = Field(min_length=1, max_length=64)
    request_schema_digest: DigestString
    response_schema_digest: DigestString
    effect: AgentToolEffect
    allowed_roles: tuple[AgentRole, ...] = Field(min_length=1, max_length=8)
    idempotent: bool
    requires_approval: bool = False

    @model_validator(mode="after")
    def _roles_unique(self) -> "AgentToolDefinitionV1":
        if len(set(self.allowed_roles)) != len(self.allowed_roles):
            raise ValueError("allowed_roles must be unique")
        if self.effect is AgentToolEffect.NETWORK_WRITE and not self.requires_approval:
            raise ValueError("network_write tools require explicit approval")
        return self


class AgentProfileRegistryV1(BaseModel):
    """Tenant-scoped registry snapshot; its digest is bound into admission."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = SCHEMA_VERSION
    registry_id: IdString
    organization_id: IdString
    version: str = Field(min_length=1, max_length=64)
    profiles: tuple[AgentProfileV1, ...] = Field(min_length=1, max_length=128)
    tools: tuple[AgentToolDefinitionV1, ...] = Field(default=(), max_length=256)
    revoked_profile_digests: tuple[DigestString, ...] = Field(default=(), max_length=512)
    created_by: RunCreatorV1
    created_at: CanonicalTimestamp
    signature: str | None = Field(default=None, max_length=1024)

    @model_validator(mode="after")
    def _registry_consistent(self) -> "AgentProfileRegistryV1":
        if self.created_by.organization_id != self.organization_id:
            raise ValueError("registry creator must belong to registry organization")
        profile_keys = [(p.profile_id, p.version) for p in self.profiles]
        if len(set(profile_keys)) != len(profile_keys):
            raise ValueError("registry contains duplicate profile versions")
        tool_ids = [tool.tool_id for tool in self.tools]
        if len(set(tool_ids)) != len(tool_ids):
            raise ValueError("registry contains duplicate tool ids")
        registered_tools = set(tool_ids)
        for profile in self.profiles:
            missing = set(profile.tool_ids) - registered_tools
            if missing:
                raise ValueError(
                    f"profile {profile.profile_id} references unknown tools: "
                    + ", ".join(sorted(missing))
                )
            for tool in self.tools:
                if tool.tool_id in profile.tool_ids and profile.role not in tool.allowed_roles:
                    raise ValueError(
                        f"tool {tool.tool_id} is not allowed for role {profile.role.value}"
                    )
        if len(set(self.revoked_profile_digests)) != len(self.revoked_profile_digests):
            raise ValueError("revoked_profile_digests must be unique")
        return self

    def digest(self) -> str:
        body = {
            "schema_version": self.schema_version,
            "registry_id": self.registry_id,
            "organization_id": self.organization_id,
            "version": self.version,
            "profiles": [
                {"profile_id": p.profile_id, "version": p.version, "profile_digest": p.digest()}
                for p in sorted(self.profiles, key=lambda item: (item.profile_id, item.version))
            ],
            "tools": [model_digest(tool) for tool in sorted(self.tools, key=lambda item: item.tool_id)],
            "revoked_profile_digests": sorted(self.revoked_profile_digests),
            "created_by": self.created_by.model_dump(mode="json"),
            "created_at": self.created_at,
        }
        return digest_of(body)

    def verify_signature(
        self, verify: Callable[[str, bytes], bool], public_key_id: str = ""
    ) -> bool:
        if not self.signature:
            return False
        return bool(verify(public_key_id, self.digest().encode("utf-8")))

    def resolve_profile(self, reference: AgentProfileRefV1) -> AgentProfileV1 | None:
        if reference.profile_digest in self.revoked_profile_digests:
            return None
        for profile in self.profiles:
            if (
                profile.profile_id == reference.profile_id
                and profile.version == reference.version
                and profile.digest() == reference.profile_digest
            ):
                return profile
        return None


class AgenticMissionV1(BaseModel):
    """User-authorized mission pinned to one run, source revision, policy, registry."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = SCHEMA_VERSION
    mission_id: IdString
    organization_id: IdString
    project_id: IdString
    run_id: IdString
    source_commit: str = Field(pattern=r"^[0-9a-f]{7,64}$")
    policy_digest: DigestString
    registry_digest: DigestString
    task_type: IdString
    objective: str = Field(min_length=5, max_length=2_000)
    profiles: tuple[AgentProfileRefV1, ...] = Field(min_length=1, max_length=16)
    budget: AgentBudgetV1
    idempotency_key: str = Field(min_length=8, max_length=128)
    created_by: RunCreatorV1
    created_at: CanonicalTimestamp

    @model_validator(mode="after")
    def _mission_scope(self) -> "AgenticMissionV1":
        if self.created_by.organization_id != self.organization_id:
            raise ValueError("mission creator must belong to mission organization")
        keys = [(p.profile_id, p.version) for p in self.profiles]
        if len(set(keys)) != len(keys):
            raise ValueError("mission profile references must be unique")
        return self

    def digest(self) -> str:
        return model_digest(self)


class AgentTaskV1(BaseModel):
    """One planned role invocation with explicit dependencies and budgets."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: IdString
    task_type: IdString
    role: AgentRole
    profile: AgentProfileRefV1
    depends_on: tuple[IdString, ...] = Field(default=(), max_length=64)
    input_artifact_ids: tuple[IdString, ...] = Field(default=(), max_length=128)
    allowed_tool_ids: tuple[IdString, ...] = Field(default=(), max_length=64)
    output_schema_digest: DigestString
    budget: AgentBudgetV1
    idempotency_key: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def _task_refs_unique(self) -> "AgentTaskV1":
        for name in ("depends_on", "input_artifact_ids", "allowed_tool_ids"):
            values = getattr(self, name)
            if len(set(values)) != len(values):
                raise ValueError(f"{name} must be unique")
        if self.task_id in self.depends_on:
            raise ValueError("a task cannot depend on itself")
        return self


class AgentPlanV1(BaseModel):
    """Validated task DAG for one admitted attempt."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = SCHEMA_VERSION
    plan_id: IdString
    mission_id: IdString
    organization_id: IdString
    project_id: IdString
    run_id: IdString
    attempt_id: IdString
    source_commit: str = Field(pattern=r"^[0-9a-f]{7,64}$")
    policy_digest: DigestString
    registry_digest: DigestString
    tasks: tuple[AgentTaskV1, ...] = Field(min_length=1, max_length=64)
    max_parallel_tasks: int = Field(default=1, ge=1, le=16)
    compiler_version: str = Field(min_length=1, max_length=64)
    created_at: CanonicalTimestamp

    @model_validator(mode="after")
    def _dag_is_valid(self) -> "AgentPlanV1":
        task_ids = [task.task_id for task in self.tasks]
        if len(set(task_ids)) != len(task_ids):
            raise ValueError("plan contains duplicate task ids")
        known = set(task_ids)
        for task in self.tasks:
            missing = set(task.depends_on) - known
            if missing:
                raise ValueError(
                    f"task {task.task_id} references unknown dependencies: "
                    + ", ".join(sorted(missing))
                )
        self.topological_order()
        return self

    def topological_order(self) -> tuple[str, ...]:
        """Return a stable topological order; reject cycles deterministically."""
        dependencies = {task.task_id: set(task.depends_on) for task in self.tasks}
        ready = sorted(task_id for task_id, deps in dependencies.items() if not deps)
        ordered: list[str] = []
        while ready:
            current = ready.pop(0)
            ordered.append(current)
            for task_id in sorted(dependencies):
                if current in dependencies[task_id]:
                    dependencies[task_id].remove(current)
                    if not dependencies[task_id] and task_id not in ordered and task_id not in ready:
                        ready.append(task_id)
            ready.sort()
        if len(ordered) != len(dependencies):
            raise ValueError("agent task graph contains a dependency cycle")
        return tuple(ordered)

    def digest(self) -> str:
        return model_digest(self)


class AgentFilesystemGrantV1(BaseModel):
    """Named workspace scope; deliberately no arbitrary host path field."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    root: AgentFilesystemRoot
    access: AgentFilesystemAccess

    @model_validator(mode="after")
    def _scope_is_not_overbroad(self) -> "AgentFilesystemGrantV1":
        if self.root is AgentFilesystemRoot.SOURCE_SNAPSHOT and self.access is AgentFilesystemAccess.WRITE:
            raise ValueError("source_snapshot is read-only")
        if self.root is AgentFilesystemRoot.ARTIFACTS and self.access is AgentFilesystemAccess.READ:
            raise ValueError("artifacts scope is write-only in v1")
        return self


class AgentCapabilityGrantV1(BaseModel):
    """Short-lived, attempt-bound capability grant; no ambient authority."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = SCHEMA_VERSION
    grant_id: IdString
    organization_id: IdString
    project_id: IdString
    run_id: IdString
    attempt_id: IdString
    sandbox_id: IdString
    task_id: IdString
    agent_id: IdString
    profile_digest: DigestString
    policy_digest: DigestString
    tool_registry_digest: DigestString
    tool_ids: tuple[IdString, ...] = Field(default=(), max_length=64)
    filesystem_grants: tuple[AgentFilesystemGrantV1, ...] = Field(default=(), max_length=8)
    network_policy_digest: DigestString
    budget: AgentBudgetV1
    nonce: IdString
    issued_at: CanonicalTimestamp
    expires_at: CanonicalTimestamp
    signature: str | None = Field(default=None, max_length=1024)

    @model_validator(mode="after")
    def _grant_is_bounded(self) -> "AgentCapabilityGrantV1":
        if self.expires_at <= self.issued_at:
            raise ValueError("capability grant must expire after it is issued")
        if len(set(self.tool_ids)) != len(self.tool_ids):
            raise ValueError("tool_ids must be unique")
        scopes = [(item.root, item.access) for item in self.filesystem_grants]
        if len(set(scopes)) != len(scopes):
            raise ValueError("filesystem grants must be unique")
        return self

    def digest(self) -> str:
        body = self.model_dump(mode="json")
        body.pop("signature", None)
        return digest_of(body)

    def verify_signature(
        self, verify: Callable[[str, bytes], bool], public_key_id: str = ""
    ) -> bool:
        if not self.signature:
            return False
        return bool(verify(public_key_id, self.digest().encode("utf-8")))


class AgentActionEventV1(BaseModel):
    """Public action/observation record; intentionally contains no chain-of-thought."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = SCHEMA_VERSION
    event_id: IdString
    organization_id: IdString
    project_id: IdString
    run_id: IdString
    attempt_id: IdString
    sandbox_id: IdString
    task_id: IdString
    agent_id: IdString
    profile_digest: DigestString
    sequence_number: int = Field(ge=1)
    action: AgentActionKind
    tool_id: IdString | None = None
    request_digest: DigestString | None = None
    output_digest: DigestString | None = None
    denial_code: IdString | None = None
    summary: str = Field(min_length=1, max_length=500)
    occurred_at: CanonicalTimestamp

    @model_validator(mode="after")
    def _action_payload_complete(self) -> "AgentActionEventV1":
        tool_action = self.action in {
            AgentActionKind.PROPOSED, AgentActionKind.VALIDATED,
            AgentActionKind.DENIED, AgentActionKind.EXECUTED,
        }
        if tool_action and (self.tool_id is None or self.request_digest is None):
            raise ValueError("tool actions require tool_id and request_digest")
        if self.action is AgentActionKind.EXECUTED and self.output_digest is None:
            raise ValueError("executed action requires output_digest")
        if self.action is AgentActionKind.DENIED and self.denial_code is None:
            raise ValueError("denied action requires a denial_code")
        if self.action is not AgentActionKind.DENIED and self.denial_code is not None:
            raise ValueError("denial_code is only valid for denied actions")
        return self


class AgentExecutionRecordV1(BaseModel):
    """Bounded execution accounting for one exact agent task."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = SCHEMA_VERSION
    execution_id: IdString
    organization_id: IdString
    project_id: IdString
    run_id: IdString
    attempt_id: IdString
    sandbox_id: IdString
    task_id: IdString
    agent_id: IdString
    profile_digest: DigestString
    runtime_bundle_digest: DigestString
    tool_registry_digest: DigestString
    model_manifest_digest: DigestString | None = None
    status: AgentExecutionStatus
    started_at: CanonicalTimestamp
    finished_at: CanonicalTimestamp | None = None
    inference_requests: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    denied_tool_calls: int = Field(default=0, ge=0)
    cpu_ms: int = Field(default=0, ge=0)
    peak_memory_mib: int = Field(default=0, ge=0)
    output_bytes: int = Field(default=0, ge=0)
    failure_code: IdString | None = None

    @model_validator(mode="after")
    def _execution_terminal_fields(self) -> "AgentExecutionRecordV1":
        if self.status is AgentExecutionStatus.RUNNING:
            if self.finished_at is not None or self.failure_code is not None:
                raise ValueError("running execution cannot have terminal fields")
        elif self.finished_at is None:
            raise ValueError("terminal execution requires finished_at")
        if self.finished_at is not None and self.finished_at < self.started_at:
            raise ValueError("finished_at cannot precede started_at")
        if self.status is AgentExecutionStatus.FAILED and self.failure_code is None:
            raise ValueError("failed execution requires failure_code")
        return self


class AgentArtifactRefV1(BaseModel):
    """Metadata-only reference to immutable bytes stored by the evidence service."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = SCHEMA_VERSION
    artifact_id: IdString
    organization_id: IdString
    project_id: IdString
    run_id: IdString
    attempt_id: IdString
    sandbox_id: IdString
    task_id: IdString
    kind: AgentArtifactKind
    media_type: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]{0,63}/[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]{0,63}$")
    size_bytes: int = Field(ge=0, le=1_073_741_824)
    sha256: DigestString
    evidence_artifact_id: IdString
    created_at: CanonicalTimestamp


def validate_plan_against_mission(
    mission: AgenticMissionV1, plan: AgentPlanV1, registry: AgentProfileRegistryV1
) -> None:
    """Validate cross-object bindings that a single JSON Schema cannot express."""
    if registry.organization_id != mission.organization_id:
        raise AgenticContractError("profile registry belongs to another organization")
    if registry.digest() != mission.registry_digest or plan.registry_digest != mission.registry_digest:
        raise AgenticContractError("mission, plan, and registry digests do not match")
    if (
        plan.mission_id != mission.mission_id
        or plan.organization_id != mission.organization_id
        or plan.project_id != mission.project_id
        or plan.run_id != mission.run_id
        or plan.source_commit != mission.source_commit
        or plan.policy_digest != mission.policy_digest
    ):
        raise AgenticContractError("plan scope does not match the admitted mission")
    selected = {
        (ref.profile_id, ref.version, ref.profile_digest) for ref in mission.profiles
    }
    for task in plan.tasks:
        key = (task.profile.profile_id, task.profile.version, task.profile.profile_digest)
        if key not in selected:
            raise AgenticContractError(
                f"task {task.task_id} uses a profile not selected by the mission"
            )
        profile = registry.resolve_profile(task.profile)
        if profile is None:
            raise AgenticContractError(f"task {task.task_id} profile is absent or revoked")
        if task.role is not profile.role:
            raise AgenticContractError(f"task {task.task_id} role does not match its profile")
        if task.task_type not in profile.task_types:
            raise AgenticContractError(f"task {task.task_id} task type is not allowed by its profile")
        if not set(task.allowed_tool_ids).issubset(set(profile.tool_ids)):
            raise AgenticContractError(f"task {task.task_id} requested tools outside its profile")
        if not task.budget.fits_within(profile.budget):
            raise AgenticContractError(f"task {task.task_id} exceeds its profile budget")
    if plan.max_parallel_tasks > mission.budget.max_parallel_tasks:
        raise AgenticContractError("plan parallelism exceeds mission budget")
