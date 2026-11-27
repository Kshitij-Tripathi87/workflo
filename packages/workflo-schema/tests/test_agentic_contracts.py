"""Adversarial tests for agentic execution contracts."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from workflo_schema.contracts import (
    AgentActionEventV1, AgentActionKind, AgentArtifactKind, AgentArtifactRefV1,
    AgentBudgetV1, AgentCapabilityGrantV1, AgentExecutionRecordV1,
    AgentExecutionStatus, AgentFilesystemAccess, AgentFilesystemGrantV1,
    AgentFilesystemRoot, AgentPlanV1, AgentProfileRegistryV1, AgentProfileV1,
    AgentRole, AgentTaskV1, AgentToolDefinitionV1, AgentToolEffect,
    AgenticContractError, AgenticMissionV1, RunCreatorV1,
    validate_plan_against_mission, utc_now_ms,
)

D1 = "sha256:" + "11" * 32
D2 = "sha256:" + "22" * 32
D3 = "sha256:" + "33" * 32
D4 = "sha256:" + "44" * 32


def budget(**updates):
    values = {
        "max_tokens": 1000, "max_inference_requests": 4, "max_tool_calls": 10,
        "max_parallel_tasks": 1, "max_elapsed_ms": 30000, "max_cpu_ms": 30000,
        "max_memory_mib": 512, "max_disk_mib": 128, "max_output_bytes": 65536,
        "max_log_bytes": 32768, "max_retries": 0,
    }
    values.update(updates)
    return AgentBudgetV1(**values)


def profile(**updates):
    values = {
        "profile_id": "explorer", "version": "1.0.0", "role": AgentRole.EXPLORER,
        "runtime_bundle_digest": D1, "entrypoint": "workflo_agent/explorer.py",
        "task_types": ("repository_qa", "api_exploration"),
        "input_schema_digest": D2, "output_schema_digest": D3,
        "tool_ids": ("repo.read", "api.probe"), "delegatable_roles": (),
        "model_profile_id": "qwen-local", "model_artifact_digests": (D4,),
        "budget": budget(),
        "created_by": RunCreatorV1(user_id="usr_1", organization_id="org_1"),
        "created_at": utc_now_ms(),
    }
    values.update(updates)
    return AgentProfileV1(**values)


def tool(**updates):
    values = {
        "tool_id": "repo.read", "version": "1", "request_schema_digest": D1,
        "response_schema_digest": D2, "effect": AgentToolEffect.READ_ONLY,
        "allowed_roles": (AgentRole.EXPLORER,), "idempotent": True,
        "requires_approval": False,
    }
    values.update(updates)
    return AgentToolDefinitionV1(**values)


def registry(agent_profile=None, **updates):
    values = {
        "registry_id": "registry_1", "organization_id": "org_1", "version": "1",
        "profiles": (agent_profile or profile(),),
        "tools": (tool(), tool(tool_id="api.probe", effect=AgentToolEffect.NETWORK_READ)),
        "revoked_profile_digests": (),
        "created_by": RunCreatorV1(user_id="usr_1", organization_id="org_1"),
        "created_at": utc_now_ms(),
    }
    values.update(updates)
    return AgentProfileRegistryV1(**values)


def mission(agent_profile, reg):
    return AgenticMissionV1(
        mission_id="mission_1", organization_id="org_1", project_id="prj_1",
        run_id="run_1", source_commit="abcdef0123456", policy_digest=D2,
        registry_digest=reg.digest(), task_type="repository_qa",
        objective="Check the repository for regressions.",
        profiles=(agent_profile.reference(),), budget=budget(max_parallel_tasks=1),
        idempotency_key="mission-idem-0001",
        created_by=RunCreatorV1(user_id="usr_1", organization_id="org_1"),
        created_at=utc_now_ms(),
    )


def task(agent_profile, **updates):
    values = {
        "task_id": "task_explore", "task_type": "repository_qa",
        "role": agent_profile.role, "profile": agent_profile.reference(),
        "allowed_tool_ids": ("repo.read",), "output_schema_digest": D3,
        "budget": budget(max_tokens=500, max_inference_requests=2, max_tool_calls=5),
        "idempotency_key": "task-idem-0001",
    }
    values.update(updates)
    return AgentTaskV1(**values)


def plan(agent_profile, reg, **updates):
    values = {
        "plan_id": "plan_1", "mission_id": "mission_1", "organization_id": "org_1",
        "project_id": "prj_1", "run_id": "run_1", "attempt_id": "attempt_1",
        "source_commit": "abcdef0123456", "policy_digest": D2,
        "registry_digest": reg.digest(), "tasks": (task(agent_profile),),
        "max_parallel_tasks": 1, "compiler_version": "1.0.0",
        "created_at": utc_now_ms(),
    }
    values.update(updates)
    return AgentPlanV1(**values)


def test_profile_rejects_unsafe_paths_duplicate_tool_and_invalid_model_role():
    with pytest.raises(ValidationError):
        profile(entrypoint="../outside.py")
    with pytest.raises(ValidationError):
        profile(tool_ids=("repo.read", "repo.read"))
    with pytest.raises(ValidationError):
        profile(role=AgentRole.TEST_DESIGNER)


def test_budget_and_profile_inference_are_consistent():
    with pytest.raises(ValidationError):
        budget(max_tokens=0)
    with pytest.raises(ValidationError):
        profile(role=AgentRole.EXECUTOR, model_profile_id=None, model_artifact_digests=())


def test_registry_rejects_unknown_tools_and_role_mismatch():
    with pytest.raises(ValidationError):
        registry(profile(tool_ids=("missing.tool",)))
    with pytest.raises(ValidationError):
        registry(tools=(tool(allowed_roles=(AgentRole.EXECUTOR,)),))


def test_revocation_and_profile_registry_digest():
    p = profile()
    reg = registry(p, revoked_profile_digests=(p.digest(),))
    assert reg.resolve_profile(p.reference()) is None
    assert reg.digest() == reg.digest()


def test_plan_is_stable_and_rejects_cycles_and_unknown_dependencies():
    p = profile()
    reg = registry(p)
    first = task(p, task_id="task_a", depends_on=("task_b",))
    second = task(p, task_id="task_b", depends_on=("task_a",))
    with pytest.raises(ValidationError, match="cycle"):
        plan(p, reg, tasks=(first, second))
    with pytest.raises(ValidationError, match="unknown dependencies"):
        plan(p, reg, tasks=(task(p, depends_on=("missing",)),))
    valid = plan(p, reg)
    assert valid.topological_order() == ("task_explore",)
    assert valid.digest() == valid.digest()


def test_cross_object_validation_rejects_tool_and_budget_escalation():
    p = profile()
    reg = registry(p)
    admitted = mission(p, reg)
    with pytest.raises(AgenticContractError, match="outside its profile"):
        unsafe_plan = plan(p, reg, tasks=(task(p, allowed_tool_ids=("admin.shell",)),))
        validate_plan_against_mission(admitted, unsafe_plan, reg)
    with pytest.raises(AgenticContractError, match="exceeds its profile budget"):
        excessive = budget(max_tokens=5000, max_inference_requests=8)
        unsafe_plan = plan(p, reg, tasks=(task(p, budget=excessive),))
        validate_plan_against_mission(admitted, unsafe_plan, reg)


def test_plan_and_mission_must_bind_same_tenant_run_commit_and_policy():
    p = profile()
    reg = registry(p)
    admitted = mission(p, reg)
    wrong_run = plan(p, reg, run_id="run_other")
    with pytest.raises(AgenticContractError, match="scope"):
        validate_plan_against_mission(admitted, wrong_run, reg)


def test_capability_grant_scope_expiry_and_digest():
    grant = AgentCapabilityGrantV1(
        grant_id="grant_1", organization_id="org_1", project_id="prj_1",
        run_id="run_1", attempt_id="attempt_1", sandbox_id="sandbox_1",
        task_id="task_1", agent_id="agent_1", profile_digest=D1,
        policy_digest=D2, tool_registry_digest=D3, tool_ids=("repo.read",),
        filesystem_grants=(
            AgentFilesystemGrantV1(root=AgentFilesystemRoot.SOURCE_SNAPSHOT, access=AgentFilesystemAccess.READ),
            AgentFilesystemGrantV1(root=AgentFilesystemRoot.ARTIFACTS, access=AgentFilesystemAccess.WRITE),
        ),
        network_policy_digest=D4, budget=budget(max_tokens=0, max_inference_requests=0),
        nonce="nonce_1", issued_at="2026-11-21T08:00:00.000Z",
        expires_at="2026-11-21T08:05:00.000Z",
    )
    assert grant.digest() == grant.digest()
    assert grant.digest() != grant.model_copy(update={"sandbox_id": "sandbox_other"}).digest()
    with pytest.raises(ValidationError):
        AgentCapabilityGrantV1(**{**grant.model_dump(), "expires_at": grant.issued_at})


def test_filesystem_grants_are_least_privilege():
    with pytest.raises(ValidationError):
        AgentFilesystemGrantV1(root=AgentFilesystemRoot.SOURCE_SNAPSHOT, access=AgentFilesystemAccess.WRITE)
    with pytest.raises(ValidationError):
        AgentFilesystemGrantV1(root=AgentFilesystemRoot.ARTIFACTS, access=AgentFilesystemAccess.READ)


def test_action_events_require_evidence_for_tool_actions_and_denials():
    base = {
        "event_id": "event_1", "organization_id": "org_1", "project_id": "prj_1",
        "run_id": "run_1", "attempt_id": "attempt_1", "sandbox_id": "sandbox_1",
        "task_id": "task_1", "agent_id": "agent_1", "profile_digest": D1,
        "sequence_number": 1, "tool_id": "repo.read", "request_digest": D2,
        "summary": "The tool action was attempted.", "occurred_at": utc_now_ms(),
    }
    with pytest.raises(ValidationError):
        AgentActionEventV1(**base, action=AgentActionKind.DENIED)
    with pytest.raises(ValidationError):
        AgentActionEventV1(**base, action=AgentActionKind.EXECUTED)
    denied = AgentActionEventV1(**base, action=AgentActionKind.DENIED, denial_code="tool_not_granted")
    assert denied.denial_code == "tool_not_granted"


def test_execution_record_requires_complete_terminal_result():
    base = {
        "execution_id": "exec_1", "organization_id": "org_1", "project_id": "prj_1",
        "run_id": "run_1", "attempt_id": "attempt_1", "sandbox_id": "sandbox_1",
        "task_id": "task_1", "agent_id": "agent_1", "profile_digest": D1,
        "runtime_bundle_digest": D2, "tool_registry_digest": D3, "started_at": utc_now_ms(),
    }
    with pytest.raises(ValidationError):
        AgentExecutionRecordV1(**base, status=AgentExecutionStatus.COMPLETED)
    with pytest.raises(ValidationError):
        AgentExecutionRecordV1(**base, status=AgentExecutionStatus.FAILED, finished_at=utc_now_ms())


def test_artifact_reference_is_bounded_and_metadata_only():
    artifact = AgentArtifactRefV1(
        artifact_id="artifact_1", organization_id="org_1", project_id="prj_1",
        run_id="run_1", attempt_id="attempt_1", sandbox_id="sandbox_1",
        task_id="task_1", kind=AgentArtifactKind.GENERATED_TEST,
        media_type="text/x-python", size_bytes=1024, sha256=D1,
        evidence_artifact_id="evidence_1", created_at=utc_now_ms(),
    )
    assert artifact.size_bytes == 1024
    with pytest.raises(ValidationError):
        AgentArtifactRefV1(**{**artifact.model_dump(), "size_bytes": 2_000_000_000})
