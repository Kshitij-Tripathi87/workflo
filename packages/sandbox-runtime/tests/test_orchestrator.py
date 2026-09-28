"""Day 12 — orchestrator roles: ordering, model-access rule, dispatch."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from sandbox_runtime.config import RunConfig
from sandbox_runtime.orchestrator import (
    EXECUTOR,
    EXPLORER,
    INGESTOR,
    JUDGE,
    NOTARY,
    PROVISIONER,
    ROLES,
    RunOrchestrator,
    execute_role,
)


def test_role_order_is_run_order():
    names = [r.name for r in ROLES]
    assert names == [
        "provisioner", "ingestor", "executor", "explorer", "judge", "notary",
    ]


def test_only_explorer_may_use_model():
    for role in ROLES:
        assert role.uses_model == (role.name == "explorer")


def test_plan_shape():
    orch = RunOrchestrator()
    plan = orch.plan()
    assert [p["role"] for p in plan] == [r.name for r in ROLES]
    assert all("stages" in p and "uses_model" in p for p in plan)


def test_stage_to_role_mapping():
    orch = RunOrchestrator()
    assert orch.role_for_stage("preflight") is PROVISIONER
    assert orch.role_for_stage("snapshot") is INGESTOR
    assert orch.role_for_stage("tests") is EXECUTOR
    assert orch.role_for_stage("agent") is EXPLORER
    assert orch.role_for_stage("judge") is JUDGE
    assert orch.role_for_stage("receipt") is NOTARY
    assert orch.role_for_stage("nonexistent") is None


def test_model_access_rule():
    orch = RunOrchestrator()
    assert orch.may_use_model("agent") is True
    assert orch.may_use_model("teardown") is False
    assert orch.may_use_model("judge") is False  # v1: deterministic


def test_judge_dispatch_consumes_recorded_records():
    supervisor = MagicMock()
    supervisor._last_agent_records_full = [
        {"seq": 1, "tool": "http_get",
         "args": {"url": "http://app.workflo.internal:3000/"},
         "denied": False, "ok": True,
         "result_summary": {"ok": True, "status": 200}},
        {"seq": 2, "tool": "http_post",
         "args": {"url": "http://app.workflo.internal:3000/pay"},
         "denied": False, "ok": True,
         "result_summary": {"ok": True, "status": 500}},
        {"seq": 3, "tool": "http_post",
         "args": {"url": "http://app.workflo.internal:3000/pay"},
         "denied": False, "ok": True,
         "result_summary": {"ok": True, "status": 500}},
    ]
    supervisor._tool_event_ids = {}
    supervisor._findings = []

    asyncio.run(execute_role(supervisor, JUDGE))

    assert len(supervisor._findings) == 1
    assert supervisor._findings[0]["status"] == "confirmed"


def test_provisioner_dispatch_calls_isolation_steps():
    supervisor = MagicMock()
    for fn in ("_preflight", "_build_rootfs", "_create_isolation", "_run_probes"):
        setattr(supervisor, fn, AsyncMock())
    supervisor._validate_config = MagicMock()

    asyncio.run(execute_role(supervisor, PROVISIONER))

    supervisor._preflight.assert_awaited_once()
    supervisor._build_rootfs.assert_awaited_once()
    supervisor._create_isolation.assert_awaited_once()
    supervisor._run_probes.assert_awaited_once()
    supervisor._validate_config.assert_called_once()


def test_notary_dispatch_teardown_then_receipt():
    supervisor = MagicMock()
    supervisor._teardown = AsyncMock()
    supervisor._build_receipt = AsyncMock()

    asyncio.run(execute_role(supervisor, NOTARY))

    supervisor._teardown.assert_awaited_once()
    supervisor._build_receipt.assert_awaited_once()
