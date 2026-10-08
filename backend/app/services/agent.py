"""CortexAgent — the Autopilot's reasoning core.

The agent runs a tool-calling loop against an OpenAI-compatible LLM
(default: Nvidia NIM). Each iteration:

  1. Builds messages: system prompt + RAG context + task + history
  2. Asks the LLM for the next step (a tool call or a final answer)
  3. If a tool call is returned, executes the tool and appends the result
  4. Repeats until the LLM stops calling tools or `max_iterations` hits

Everything the agent does is recorded on the AutopilotTask's `steps` list
so a human can audit the reasoning chain afterwards.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.llm import BaseLlmProvider, get_llm_provider
from app.core.settings import settings
from app.models.autopilot import AgentStep, AutopilotTask, Complexity, Verdict
from app.services.context_store import ContextStore


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the Cortex Autopilot — an AI agent that monitors
data infrastructure, detects changes, assesses impact, and remediates issues.

You have tools available. Always call `get_asset_context` first if you have an
asset URN, so you can reason from past work. Then call `classify_complexity`
before any execution work so you know how this task is gated.

CLASSIFICATION RULES:
  SIMPLE  ≈ 40% of tasks:
    - ownership gaps (owner_missing)
    - field additions or renames with <3 downstream assets
    - blast radius < 5
    - schema additions only
  COMPLEX ≈ 60% of tasks:
    - column removal (schema_remove)
    - table deprecation (dataset_deprecation)
    - blast radius >= 5
    - multi-hop lineage impact, or >=3 downstream assets

FREEMIUM GATING — current tier: "{tier}", trial_active: {trial}
  - When trial_active=True OR tier="paid": execute EVERY task fully,
    write_back the resolution, and finish with verdict pass/warn/block.
  - When trial_active=False AND tier="free":
      * SIMPLE tasks: execute fully (build_snapshot → run_future_search
        → generate_fix → write_back) and finish with verdict pass/warn/block.
      * COMPLEX tasks: do NOT call write_back. Report the impact and
        finalise with verdict="upgrade_required" along with a short
        message saying the task requires an upgrade to Team ($499/mo)
        to execute. Still call build_snapshot + run_future_search so the
        user gets the impact report.

WORKFLOW (recommended tool order):
  1. get_asset_context(urn)            — gather memory
  2. classify_complexity(...)           — gate the task
  3. run_future_search(urn, connector)   — get the ranked plan
  4. evaluate_policies(plan, policies)  — if any policies are declared
  5. generate_fix(...)                  — draft a remediation artifact
  6. write_back(...)                    — only if gating permits
  7. Summarise the run in a final response. Include: complexity, verdict,
     what changed, the impact, and the recommendation.

Notes:
  - Tools are async and return JSON strings. Use them via function calling.
  - If a tool errors, log the error and continue with the next best plan.
"""


# ---------------------------------------------------------------------------
# Tool schemas (sent to the LLM as function definitions)
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "name": "get_asset_context",
        "description": "Retrieve the current state of an asset plus any past incidents, tasks, or context relevant to it. Always call this first.",
        "parameters": {
            "type": "object",
            "properties": {
                "urn": {"type": "string", "description": "Asset URN to look up"}
            },
            "required": ["urn"],
        },
    },
    {
        "name": "list_registered_assets",
        "description": "List all asset URNs the Autopilot currently tracks (those it has observed before).",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "build_snapshot",
        "description": "Build a graph snapshot (the asset and its upstream/downstream neighbors) using the specified connector.",
        "parameters": {
            "type": "object",
            "properties": {
                "asset_urns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "URNs to center the snapshot on (usually [asset_urn])",
                },
                "connector": {
                    "type": "string",
                    "description": "Connector name: datahub, dbt, or snowflake",
                },
            },
            "required": ["asset_urns", "connector"],
        },
    },
    {
        "name": "run_future_search",
        "description": "Build a snapshot and run the future-search engine to get a ranked change plan. Returns the plan_id, ranked scenario, predicted severity/effort/benefit, blast radius, and candidate list.",
        "parameters": {
            "type": "object",
            "properties": {
                "asset_urn": {"type": "string"},
                "connector": {"type": "string", "default": "datahub"},
                "objective": {"type": "string", "default": "minimize incident risk"},
            },
            "required": ["asset_urn", "connector"],
        },
    },
    {
        "name": "evaluate_policies",
        "description": "Evaluate a list of policies against a plan's metrics. Returns a verdict (pass/warn/block) and list of violations.",
        "parameters": {
            "type": "object",
            "properties": {
                "severity": {"type": "number", "description": "Predicted severity 0-100"},
                "blast_radius": {"type": "integer", "description": "Affected asset count"},
                "has_owner": {"type": "boolean"},
                "policies": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Optional list of policies to evaluate",
                },
            },
            "required": ["severity", "blast_radius", "has_owner"],
        },
    },
    {
        "name": "generate_fix",
        "description": "Generate a remediation artifact (SQL, dbt, YAML, etc.) for an incident on the asset.",
        "parameters": {
            "type": "object",
            "properties": {
                "incident_type": {
                    "type": "string",
                    "description": "schema_drift or ownership_gap",
                },
                "asset_urn": {"type": "string"},
                "severity": {
                    "type": "string",
                    "description": "low, medium, high, or critical",
                },
                "reason": {"type": "string", "description": "Incident reason"},
            },
            "required": ["incident_type", "asset_urn", "severity", "reason"],
        },
    },
    {
        "name": "write_back",
        "description": "Persist a resolution record (audit log + lineage writeback). Only call when gating permits execution.",
        "parameters": {
            "type": "object",
            "properties": {
                "asset_urn": {"type": "string"},
                "severity": {"type": "string"},
                "action_type": {"type": "string"},
                "summary": {"type": "string"},
                "confidence": {"type": "number", "default": 0.7},
            },
            "required": ["asset_urn", "severity", "action_type", "summary"],
        },
    },
    {
        "name": "classify_complexity",
        "description": "Determine whether the task is SIMPLE or COMPLEX based on the change and its blast radius. Sets the gating decision.",
        "parameters": {
            "type": "object",
            "properties": {
                "change_type": {"type": "string"},
                "blast_radius": {"type": "integer", "default": 0},
                "downstream_count": {"type": "integer", "default": 0},
            },
            "required": ["change_type"],
        },
    },
]


# ---------------------------------------------------------------------------
# Complexity classification (deterministic; mirrors SYSTEM_PROMPT rules)
# ---------------------------------------------------------------------------

def classify_complexity(
    change_type: str,
    blast_radius: int = 0,
    downstream_count: int = 0,
) -> Complexity:
    """Return 'simple' or 'complex' for a change. ~40/60 split by design."""
    if change_type in ("schema_remove", "dataset_deprecation"):
        return "complex"
    if blast_radius >= 5:
        return "complex"
    if downstream_count >= 3:
        return "complex"
    if change_type == "owner_missing":
        return "simple"
    if change_type == "schema_rename" and blast_radius < 3:
        return "simple"
    if change_type == "pipeline_failure" and blast_radius < 2:
        return "simple"
    # Default biases toward simple — the ~40% bucket
    return "simple"


# ---------------------------------------------------------------------------
# Result construction helpers
# ---------------------------------------------------------------------------

def _summarise_plan(plan) -> Dict[str, Any]:
    """Reduce a FuturePlan to a compact dict for LLM consumption."""
    choice = plan.ranked_choice
    return {
        "plan_id": plan.plan_id,
        "ranked_choice": {
            "scenario_type": choice.scenario_type,
            "change": choice.change,
            "predicted_severity": choice.predicted_severity,
            "predicted_effort": choice.predicted_effort,
            "predicted_benefit": choice.predicted_benefit,
            "predicted_blast_radius": choice.predicted_blast_radius,
            "confidence": choice.confidence,
            "affected_dashboards": choice.affected_dashboards,
            "affected_models": choice.affected_models,
            "affected_pipelines": choice.affected_pipelines,
        },
        "rationale": plan.rationale,
        "explanation": plan.explanation[:5],
        "candidates": [
            {
                "scenario_type": c.scenario_type,
                "predicted_severity": c.predicted_severity,
                "predicted_blast_radius": c.predicted_blast_radius,
                "predicted_effort": c.predicted_effort,
                "predicted_benefit": c.predicted_benefit,
            }
            for c in plan.candidates
        ],
    }


def _truncate(s: str, limit: int = 4000) -> str:
    return s if len(s) <= limit else s[:limit] + "...[truncated]"


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class CortexAgent:
    """Stateful reasoning loop that orchestrates Cortex tools."""

    def __init__(
        self,
        context_store: ContextStore,
        llm: Optional[BaseLlmProvider] = None,
        max_iterations: Optional[int] = None,
    ) -> None:
        self.context_store = context_store
        self._llm: BaseLlmProvider = llm or get_llm_provider()
        self.max_iterations = max_iterations or settings.CORTEX_MAX_AGENT_ITERATIONS

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run(self, task: AutopilotTask) -> AutopilotTask:
        """Execute an AutopilotTask end-to-end."""
        task.status = "running"

        # Prime the LLM with context
        rag_ctx = self._retrieve_relevant_context(task)
        system = (
            SYSTEM_PROMPT
            .replace("{tier}", settings.CORTEX_TIER)
            .replace("{trial}", str(settings.CORTEX_TRIAL_ACTIVE).lower())
        )

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system},
        ]
        if rag_ctx:
            messages.append(
                {"role": "system", "content": f"Retrieved context:\n{rag_ctx}"}
            )
        messages.append(
            {
                "role": "user",
                "content": self._format_task_prompt(task),
            }
        )

        # Tool dispatch loop
        for step_index in range(self.max_iterations):
            try:
                response = await self._llm.chat(messages, tools=TOOL_SCHEMAS)
            except Exception as exc:
                step = AgentStep(
                    step_index=step_index,
                    thought=f"LLM call failed: {exc}",
                )
                task.steps.append(step)
                task.status = "failed"
                task.summary = f"Agent aborted: LLM error — {exc}"
                return task

            assistant_message: Dict[str, Any] = {"role": "assistant", "content": response.content}
            if response.tool_calls:
                assistant_message["tool_calls"] = response.tool_calls
            messages.append(assistant_message)

            if not response.tool_calls:
                # No more tool calls → the LLM is done reasoning
                final_step = AgentStep(
                    step_index=step_index,
                    thought=response.content or "Agent finished",
                )
                task.steps.append(final_step)
                task.summary = response.content or ""
                self._finalise(task)
                return task

            # Execute each requested tool call in order
            for tc in response.tool_calls:
                step = AgentStep(
                    step_index=step_index,
                    thought=f"Calling {tc['name']}",
                    tool_name=tc["name"],
                    tool_args=tc["arguments"],
                )
                try:
                    result = await self._dispatch_tool(tc["name"], tc["arguments"], task)
                    step.tool_result = _truncate(result)
                except Exception as exc:
                    step.tool_result = f"ERROR: {exc}"
                step.observation = step.tool_result[:500]
                task.steps.append(step)

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "name": tc["name"],
                        "content": step.tool_result,
                    }
                )

        # Loop exhausted — terminate gracefully
        task.steps.append(
            AgentStep(
                step_index=self.max_iterations,
                thought=f"Max iterations ({self.max_iterations}) reached",
            )
        )
        task.summary = task.summary or "Agent stopped after max iterations."
        self._finalise(task)
        return task

    # ------------------------------------------------------------------
    # Tool dispatch
    # ------------------------------------------------------------------

    async def _dispatch_tool(self, name: str, args: Dict[str, Any], task: AutopilotTask) -> str:
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return f"ERROR: unknown tool '{name}'"

        import inspect

        if inspect.iscoroutinefunction(handler):
            result = await handler(**args)
        else:
            result = handler(**args)

        # Side-effect on key tools: tag complexity / verdict
        if name == "classify_complexity":
            complexity = result.get("complexity", "simple")
            task.complexity = complexity
            gated = self._is_gated(complexity)
            result["gating"] = (
                "blocked (free tier, complex task) — do not write_back, report only"
                if gated
                else "allowed — proceed with execution"
            )
        elif name == "run_future_search":
            if task.complexity is None:
                # If the LLM skipped classify_complexity, infer from the plan
                br = (result.get("ranked_choice") or {}).get("predicted_blast_radius", 0)
                task.complexity = classify_complexity(
                    task.change.get("change_type", "auto_detected"),
                    blast_radius=br,
                    downstream_count=br,
                )
        elif name == "write_back":
            task.verdict = "pass"

        return _truncate(json.dumps(result, default=str))

    # ------------------------------------------------------------------
    # The tools themselves
    # ------------------------------------------------------------------

    def _tool_get_asset_context(self, urn: str, **_kwargs) -> Dict[str, Any]:
        state = self.context_store.get_asset_state(urn) or {}
        docs = self.context_store.retrieve_context(urn, k=4)
        return {
            "asset_state": state,
            "retrieved_context": [
                {"text": d.text, "metadata": d.metadata, "similarity": d.similarity}
                for d in docs
            ],
        }

    def _tool_list_registered_assets(self, **_kwargs) -> Dict[str, Any]:
        return {"asset_urns": self.context_store.list_registered_assets()}

    def _tool_classify_complexity(
        self,
        change_type: str,
        blast_radius: int = 0,
        downstream_count: int = 0,
        **_kwargs,
    ) -> Dict[str, Any]:
        complexity = classify_complexity(
            change_type=change_type,
            blast_radius=blast_radius,
            downstream_count=downstream_count,
        )
        gated = self._is_gated(complexity)
        return {
            "complexity": complexity,
            "is_gated": gated,
            "policy_reminder": (
                "Free tier post-trial: complex tasks cannot write_back. "
                "Report impact only with verdict=upgrade_required."
                if gated
                else "Execution allowed."
            ),
        }


    async def _tool_build_snapshot(
        self, asset_urns: List[str], connector: str = "datahub", **_kwargs
    ) -> Dict[str, Any]:
        from app.connectors import get_connector, list_connectors

        if not list_connectors():
            import app.connectors  # noqa: F401 (triggers auto-registration)

        try:
            conn = get_connector(connector)
        except ValueError as exc:
            return {"error": str(exc)}

        snapshot = await conn.build_snapshot(asset_urns)
        nodes = []
        for urn, node in snapshot.nodes.items():
            nodes.append(
                {
                    "urn": node.urn,
                    "name": node.name,
                    "kind": node.kind,
                    "owner": node.owner,
                    "downstream_count": len(node.downstream),
                    "upstream_count": len(node.upstream),
                    "schema_fields": node.schema_fields,
                }
            )
        return {
            "node_count": len(snapshot.nodes),
            "nodes": nodes[:20],
            "edges": len(snapshot.edges),
        }

    async def _tool_run_future_search(
        self,
        asset_urn: str,
        connector: str = "datahub",
        objective: str = "minimize incident risk",
        **_kwargs,
    ) -> Dict[str, Any]:
        from app.connectors import get_connector, list_connectors
        from app.engine.future_search_engine import generate_futures

        if not list_connectors():
            import app.connectors  # noqa: F401

        conn = get_connector(connector)
        snapshot = await conn.build_snapshot([asset_urn])
        if asset_urn not in snapshot.nodes:
            return {"error": f"asset {asset_urn} not found in connector {connector}"}
        plan = generate_futures(
            snapshot=snapshot,
            asset_urn=asset_urn,
            objective=objective,
        )
        return _summarise_plan(plan)

    def _tool_evaluate_policies(
        self,
        severity: float,
        blast_radius: int,
        has_owner: bool,
        policies: Optional[List[Dict[str, Any]]] = None,
        **_kwargs,
    ) -> Dict[str, Any]:
        from app.engine.policy import evaluate_policies, combine_verdict, policies_from_dicts

        policy_objs = policies_from_dicts(policies or [])
        results = evaluate_policies(
            policies=policy_objs,
            severity=severity,
            blast_radius=blast_radius,
            has_owner=has_owner,
        )
        verdict = combine_verdict(results)
        return {
            "verdict": verdict,
            "violations": [r.model_dump() for r in results],
        }

    def _tool_generate_fix(
        self,
        incident_type: str,
        asset_urn: str,
        severity: str,
        reason: str,
        **_kwargs,
    ) -> Dict[str, Any]:
        from uuid import uuid4
        from app.models import Incident, FixDraft
        from app.services.fix_generator import generate_fix

        # Map severity → incident severity literal. Some callers pass
        # number severity (predicted_severity) - normalise here.
        sev_norm = severity
        if isinstance(severity, (int, float)):
            sev_norm = (
                "critical" if severity >= 75
                else "high" if severity >= 50
                else "medium" if severity >= 25
                else "low"
            )

        # Map a free-text type to one of the two supported Incident literal
        if incident_type not in ("schema_drift", "ownership_gap"):
            incident_type_norm = "schema_drift"
        else:
            incident_type_norm = incident_type

        incident = Incident(
            incident_id=str(uuid4()),
            incident_type=incident_type_norm,  # type: ignore[arg-type]
            severity=sev_norm,  # type: ignore[arg-type]
            asset_urn=asset_urn,
            reason=reason,
        )
        fix: FixDraft = generate_fix(incident)
        return {
            "incident_id": fix.incident_id,
            "title": fix.title,
            "summary": fix.summary,
            "artifact_type": fix.artifact_type,
            "artifact_body": fix.artifact_body,
            "confidence": fix.confidence,
        }

    def _tool_write_back(
        self,
        asset_urn: str,
        severity: str,
        action_type: str,
        summary: str,
        confidence: float = 0.7,
        **_kwargs,
    ) -> Dict[str, Any]:
        from app.models.impact import ImpactReport
        from app.models.recommendation import Recommendation
        from app.services.writeback_service import writeback_service

        impact = ImpactReport(
            asset_urn=asset_urn,
            affected_assets=[],
            affected_dashboards=[],
            affected_models=[],
            affected_pipelines=[],
            severity=severity,  # type: ignore[arg-type]
            reason=summary,
            confidence=confidence,
            explanation=[],
        )
        recommendation = Recommendation(
            impact_id="autopilot",
            action_type=action_type,
            title=action_type,
            rationale=summary,
            confidence=confidence,
            risk="low",
        )
        record = writeback_service.record_resolution(
            asset_urn=asset_urn,
            impact_report=impact,
            recommendation=recommendation,
            created_by="autopilot",
        )
        return {"record_id": record.record_id, "asset_urn": record.asset_urn}

    # ------------------------------------------------------------------
    # Free / Paid gating
    # ------------------------------------------------------------------

    def _is_gated(self, complexity: Complexity) -> bool:
        """True if a COMPLEX task should NOT execute on the current tier."""
        if settings.CORTEX_TRIAL_ACTIVE:
            return False
        if settings.CORTEX_TIER == "paid":
            return False
        # free tier post-trial: complex tasks are gated
        return complexity == "complex"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _retrieve_relevant_context(self, task: AutopilotTask) -> str:
        query = " ".join(filter(None, [task.asset_urn, task.description, str(task.change)]))
        docs = self.context_store.retrieve_context(query, k=5)
        if not docs:
            return ""
        serialized = []
        for d in docs:
            serialized.append(f"- {d.metadata.get('kind', 'doc')}: {d.text[:500]}")
        return "\n".join(serialized)

    def _format_task_prompt(self, task: AutopilotTask) -> str:
        lines = [
            f"Task: {task.description or 'Autopilot detected a change'}",
            f"Asset URN: {task.asset_urn}",
            f"Connector: {task.connector}",
            f"Trigger: {task.trigger_type}",
            f"Change: {json.dumps(task.change)}",
        ]
        if task.change.get("change_type"):
            lines.append(
                f"Hint: change_type is '{task.change['change_type']}' — classify_complexity needs it."
            )
        return "\n".join(lines)

    def _finalise(self, task: AutopilotTask) -> None:
        # If the agent marked the task gated, set the upgrade verdict
        if task.complexity == "complex" and self._is_gated(task.complexity):
            task.verdict = "upgrade_required"
            task.status = "blocked"
            return

        if task.verdict is None:
            # Reasonable default if the agent didn't say otherwise
            task.verdict = "pass" if task.complexity != "complex" else "warn"

        task.status = "completed"
        task.completed_at = datetime.utcnow()
