"""Tests for the Cortex Autopilot: context store, agent, and API."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.llm import BaseLlmProvider, LlmResponse
from app.main import app
from app.models.autopilot import AutopilotTask
from app.services.agent import CortexAgent, classify_complexity
from app.services.autopilot import Autopilot, reset_autopilot
from app.services.context_store import ContextStore, compute_schema_hash


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class _StubLlm(BaseLlmProvider):
    """Deterministic stub LLM that walks the happy-path tool sequence."""

    def __init__(self):
        self._script: list[list[dict[str, Any]]] = []
        self._call_index = 0

    def set_script(self, script: list[list[dict[str, Any]]]) -> None:
        self._script = script
        self._call_index = 0

    async def chat(self, messages, tools=None, temperature=0.2, max_tokens=None):
        if self._call_index >= len(self._script):
            return LlmResponse(content="Done.", tool_calls=[], finish_reason="stop")
        calls = self._script[self._call_index]
        self._call_index += 1
        return LlmResponse(
            content="",
            tool_calls=[
                {"id": f"call-{i}", "name": c["name"], "arguments": c["arguments"]}
                for i, c in enumerate(calls)
            ],
            finish_reason="tool_calls",
        )


@pytest.fixture
def context_store(tmp_path, monkeypatch):
    """A fresh ContextStore pointing its ChromaDB path at a tmp dir."""
    monkeypatch.setattr("app.services.context_store.settings.CORTEX_CHROMA_PATH", str(tmp_path / "chromadb"))
    return ContextStore()


@pytest.fixture
def stub_llm():
    return _StubLlm()


@pytest.fixture
def agent(context_store, stub_llm):
    return CortexAgent(context_store=context_store, llm=stub_llm)


@pytest.fixture
def autopilot(context_store, agent):
    ap = Autopilot(context_store=context_store, agent=agent)
    reset_autopilot(ap)
    yield ap
    reset_autopilot(None)


# ---------------------------------------------------------------------------
# Complexity classification
# ---------------------------------------------------------------------------

class TestClassifyComplexity:
    def test_owner_missing_is_simple(self):
        assert classify_complexity("owner_missing") == "simple"

    def test_schema_remove_is_complex(self):
        assert classify_complexity("schema_remove") == "complex"

    def test_dataset_deprecation_is_complex(self):
        assert classify_complexity("dataset_deprecation") == "complex"

    def test_large_blast_radius_is_complex(self):
        assert classify_complexity("schema_rename", blast_radius=5) == "complex"

    def test_small_blast_radius_rename_is_simple(self):
        assert classify_complexity("schema_rename", blast_radius=2) == "simple"

    def test_pipeline_failure_small_is_simple(self):
        assert classify_complexity("pipeline_failure", blast_radius=1) == "simple"

    def test_three_downstream_is_complex(self):
        assert classify_complexity("auto_detected", downstream_count=3) == "complex"


# ---------------------------------------------------------------------------
# Context store
# ---------------------------------------------------------------------------

class TestContextStore:
    def test_compute_schema_hash_is_case_insensitive(self):
        assert compute_schema_hash(["ID", "Name"]) == compute_schema_hash(["id", "name"])

    def test_store_asset_state_returns_false_on_first_observation(self, context_store):
        changed = context_store.store_asset_state(
            asset_urn="urn:test:asset",
            connector="dbt",
            name="Orders",
            owner="alice",
            schema_fields=["id", "status"],
        )
        assert changed is False

    def test_store_asset_state_detects_schema_change(self, context_store):
        context_store.store_asset_state(
            asset_urn="urn:test:asset", connector="dbt", schema_fields=["id", "status"]
        )
        changed = context_store.store_asset_state(
            asset_urn="urn:test:asset", connector="dbt", schema_fields=["id", "status", "amount"]
        )
        assert changed is True

    def test_store_and_retrieve_task(self, context_store):
        task = AutopilotTask(asset_urn="urn:test:asset", connector="dbt")
        context_store.store_task(task)
        recent = context_store.recent_tasks(limit=5)
        assert len(recent) == 1
        assert recent[0].task_id == task.task_id
        assert context_store.total_tasks() == 1

    def test_list_registered_assets(self, context_store):
        context_store.store_asset_state(asset_urn="urn:a", connector="dbt")
        context_store.store_asset_state(asset_urn="urn:b", connector="dbt")
        assert set(context_store.list_registered_assets()) == {"urn:a", "urn:b"}

    def test_retrieve_context_returns_relevant_docs(self, context_store):
        context_store.store_task(
            AutopilotTask(
                asset_urn="urn:li:dataset:orders",
                connector="dbt",
                description="orders column removal",
                summary="orders column removal",
            )
        )
        docs = context_store.retrieve_context("orders", k=5)
        # Either ChromaDB found it or our in-memory fallback did
        assert any("orders" in d.text.lower() for d in docs)


# ---------------------------------------------------------------------------
# Freemium gating
# ---------------------------------------------------------------------------

class TestGating:
    def test_trial_active_allows_complex(self, agent, monkeypatch):
        monkeypatch.setattr("app.services.agent.settings.CORTEX_TRIAL_ACTIVE", True)
        monkeypatch.setattr("app.services.agent.settings.CORTEX_TIER", "free")
        assert agent._is_gated("complex") is False

    def test_paid_tier_allows_complex(self, agent, monkeypatch):
        monkeypatch.setattr("app.services.agent.settings.CORTEX_TRIAL_ACTIVE", False)
        monkeypatch.setattr("app.services.agent.settings.CORTEX_TIER", "paid")
        assert agent._is_gated("complex") is False

    def test_free_post_trial_blocks_complex(self, agent, monkeypatch):
        monkeypatch.setattr("app.services.agent.settings.CORTEX_TRIAL_ACTIVE", False)
        monkeypatch.setattr("app.services.agent.settings.CORTEX_TIER", "free")
        assert agent._is_gated("complex") is True

    def test_free_post_trial_allows_simple(self, agent, monkeypatch):
        monkeypatch.setattr("app.services.agent.settings.CORTEX_TRIAL_ACTIVE", False)
        monkeypatch.setattr("app.services.agent.settings.CORTEX_TIER", "free")
        assert agent._is_gated("simple") is False


# ---------------------------------------------------------------------------
# Agent run end-to-end with stub LLM
# ---------------------------------------------------------------------------

class TestAgentRun:
    def test_simple_task_executes_and_writes_back(self, agent, stub_llm, context_store):
        # Use trial active so even complex tasks go through
        # (here we use a simple change_type to keep classified as simple)
        stub_llm.set_script([
            [{"name": "get_asset_context", "arguments": {"urn": "urn:test:orders"}}],
            [{"name": "classify_complexity", "arguments": {
                "change_type": "owner_missing",
                "blast_radius": 0,
                "downstream_count": 0,
            }}],
            [{"name": "run_future_search", "arguments": {
                "asset_urn": "urn:test:orders",
                "connector": "dbt",
            }}],
            [{"name": "generate_fix", "arguments": {
                "incident_type": "ownership_gap",
                "asset_urn": "urn:test:orders",
                "severity": "medium",
                "reason": "no owner assigned",
            }}],
            [{"name": "write_back", "arguments": {
                "asset_urn": "urn:test:orders",
                "severity": "medium",
                "action_type": "assign_owner",
                "summary": "auto-remediated by Cortex Autopilot",
                "confidence": 0.7,
            }}],
        ])

        task = AutopilotTask(
            asset_urn="urn:test:orders",
            connector="dbt",
            change={"change_type": "owner_missing"},
            description="remediate ownership gap",
        )
        result = asyncio.run(agent.run(task))

        assert result.status == "completed"
        assert result.complexity == "simple"
        assert result.verdict == "pass"
        # 5 tool calls + 1 final no-calls step
        assert len(result.steps) == 6
        assert result.steps[1].tool_name == "classify_complexity"

    def test_complex_task_blocked_on_free_post_trial(self, agent, stub_llm, monkeypatch):
        monkeypatch.setattr("app.services.agent.settings.CORTEX_TRIAL_ACTIVE", False)
        monkeypatch.setattr("app.services.agent.settings.CORTEX_TIER", "free")

        stub_llm.set_script([
            [{"name": "get_asset_context", "arguments": {"urn": "urn:test:t"}}],
            [{"name": "classify_complexity", "arguments": {
                "change_type": "schema_remove",
                "blast_radius": 8,
            }}],
            # LLM obeys the gating reminder and stops without write_back
        ])

        task = AutopilotTask(
            asset_urn="urn:test:t",
            connector="dbt",
            change={"change_type": "schema_remove"},
            description="column removal",
        )
        result = asyncio.run(agent.run(task))

        assert result.complexity == "complex"
        assert result.verdict == "upgrade_required"
        assert result.status == "blocked"
        # No write_back tool was ever called
        tool_names = [s.tool_name for s in result.steps if s.tool_name]
        assert "write_back" not in tool_names

    def test_agent_handles_unknown_tool_gracefully(self, agent, stub_llm):
        stub_llm.set_script([
            [{"name": "get_asset_context", "arguments": {"urn": "urn:test:t"}}],
            [{"name": "classify_complexity", "arguments": {"change_type": "owner_missing"}}],
            [{"name": "nonexistent_tool", "arguments": {}}],
        ])

        task = AutopilotTask(
            asset_urn="urn:test:t",
            connector="dbt",
            change={"change_type": "owner_missing"},
            description="trigger with bogus tool",
        )
        result = asyncio.run(agent.run(task))

        # Should have completed (with the error from the unknown tool logged)
        assert any("unknown tool" in s.tool_result.lower() for s in result.steps)


# ---------------------------------------------------------------------------
# Autopilot lifecycle
# ---------------------------------------------------------------------------

class TestAutopilotLifecycle:
    def test_status_reports_running_state(self, autopilot):
        asyncio.run(autopilot.start())
        try:
            status = autopilot.status()
            assert status.enabled is False  # default in tests
            assert status.tier == "trial"
            assert status.trial_active is True
        finally:
            asyncio.run(autopilot.stop())

    def test_execute_task_records_in_context_store(self, autopilot, stub_llm):
        stub_llm.set_script([
            [{"name": "get_asset_context", "arguments": {"urn": "urn:test:z"}}],
            [{"name": "classify_complexity", "arguments": {"change_type": "owner_missing"}}],
        ])

        task = AutopilotTask(
            asset_urn="urn:test:z",
            connector="dbt",
            change={"change_type": "owner_missing"},
            description="test",
        )
        result = asyncio.run(autopilot.execute_task(task))
        assert result.status in ("completed", "blocked")
        assert autopilot.context_store.total_tasks() == 1
        assert "urn:test:z" in autopilot.context_store.list_registered_assets()


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

class TestAutopilotApi:
    def setup_method(self):
        # Replace the singleton with one using a stub LLM
        from app.services.autopilot import reset_autopilot
        self._ctx = ContextStore()
        self._stub = _StubLlm()
        self._agent = CortexAgent(context_store=self._ctx, llm=self._stub)
        self._ap = Autopilot(context_store=self._ctx, agent=self._agent)
        reset_autopilot(self._ap)
        self._client = TestClient(app)

    def teardown_method(self):
        reset_autopilot(None)

    def test_status_endpoint(self):
        res = self._client.get("/autopilot/status")
        assert res.status_code == 200
        body = res.json()
        assert body["enabled"] is False
        assert body["tier"] == "trial"

    def test_assets_endpoint_returns_list(self):
        self._ctx.store_asset_state(asset_urn="urn:api:test", connector="dbt")
        res = self._client.get("/autopilot/assets")
        assert res.status_code == 200
        assert "urn:api:test" in res.json()["asset_urns"]

    def test_trigger_endpoint_executes_task(self):
        self._stub.set_script([
            [{"name": "get_asset_context", "arguments": {"urn": "urn:api:trigger"}}],
            [{"name": "classify_complexity", "arguments": {"change_type": "owner_missing"}}],
        ])
        res = self._client.post(
            "/autopilot/trigger",
            json={
                "asset_urn": "urn:api:trigger",
                "connector": "dbt",
                "change_type": "owner_missing",
                "description": "auto remediate",
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["task"]["status"] in ("completed", "blocked")
        assert body["task"]["asset_urn"] == "urn:api:trigger"
