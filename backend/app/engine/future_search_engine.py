from uuid import uuid4
from copy import deepcopy
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from app.models.asset import GraphSnapshot, AssetNode
from app.models.scenario import ScenarioRequest
from app.models.future import FutureScenario, FuturePlan
from app.engine.scenario_engine import apply_scenario
from app.engine.impact_engine import analyze_impact
from app.engine.recommendation_ranker import rank_candidates
from app.engine.explanation_builder import build_explanation


def _build_candidates(
    snapshot: GraphSnapshot,
    asset_urn: str,
) -> List[Tuple[str, str, dict, int]]:
    candidates: List[Tuple[str, str, dict, int]] = []
    node = snapshot.nodes.get(asset_urn)

    if node is None:
        return candidates

    candidates.append(
        ("schema_remove", "do_nothing", {"action": "do nothing - evaluate baseline"}, 5)
    )

    if not node.owner:
        candidates.append(
            ("owner_missing", "assign_owner", {"action": "assign asset owner"}, 10)
        )

    if node.kind == "pipeline":
        candidates.append(
            ("pipeline_failure", "patch_dag", {"action": "patch DAG or retry pipeline"}, 30)
        )
    elif node.kind == "dataset":
        candidates.append(
            ("schema_remove", "patch_sql", {"action": "patch downstream SQL"}, 20)
        )
        candidates.append(
            ("schema_remove", "patch_dbt", {"action": "patch dbt model references"}, 25)
        )
        candidates.append(
            ("schema_remove", "create_temp_view", {"action": "create temporary compatibility view"}, 35)
        )
        candidates.append(
            ("dataset_deprecation", "archive_asset", {"action": "archive and migrate consumers"}, 50)
        )
    else:
        candidates.append(
            ("dataset_deprecation", "archive_asset", {"action": "archive and migrate consumers"}, 50)
        )

    if len(candidates) <= 1:
        candidates.append(
            ("schema_remove", "patch_sql", {"action": "patch downstream SQL"}, 20)
        )
    return candidates


def generate_futures(
    snapshot: GraphSnapshot,
    asset_urn: str,
    objective: str = "minimize incident risk",
    constraints: Dict = None
) -> FuturePlan:
    candidates: List[FutureScenario] = []
    constraints = constraints or {}

    scenario_candidates = _build_candidates(snapshot, asset_urn)

    for scenario_type, action_label, change, effort_estimate in scenario_candidates:
        request = ScenarioRequest(
            asset_urn=asset_urn,
            scenario_type=scenario_type,
            change=change,
        )

        candidate_snapshot = deepcopy(snapshot)
        scenario_result = apply_scenario(candidate_snapshot, request)

        impact = analyze_impact(candidate_snapshot, scenario_result)

        severity_map = {
            "low": 15,
            "medium": 40,
            "high": 70,
            "critical": 95,
        }
        predicted_severity = severity_map.get(impact.severity, 50)

        base_benefit = 100 - predicted_severity
        if action_label == "do_nothing":
            predicted_benefit = max(0, base_benefit - 20)
        elif action_label in ["patch_sql", "patch_dbt", "patch_dag"]:
            predicted_benefit = min(100, base_benefit + 10)
        else:
            predicted_benefit = base_benefit

        predicted_effort = effort_estimate

        evidence = impact.explanation[:3] if impact.explanation else []

        # Capture blast-radius numbers so the policy engine can evaluate them
        predicted_blast_radius = len(impact.affected_assets)
        affected_dashboards = len(impact.affected_dashboards)
        affected_models = len(impact.affected_models)
        affected_pipelines = len(impact.affected_pipelines)

        candidate = FutureScenario(
            future_id=str(uuid4()),
            asset_urn=asset_urn,
            scenario_type=action_label,
            change=change,
            predicted_severity=predicted_severity,
            predicted_effort=predicted_effort,
            predicted_benefit=predicted_benefit,
            predicted_blast_radius=predicted_blast_radius,
            confidence=impact.confidence,
            evidence=evidence,
            affected_dashboards=affected_dashboards,
            affected_models=affected_models,
            affected_pipelines=affected_pipelines,
        )
        candidates.append(candidate)

    ranked_choice = rank_candidates(candidates, objective=objective, constraints=constraints)

    explanation = build_explanation(ranked_choice, candidates)

    return FuturePlan(
        plan_id=str(uuid4()),
        asset_urn=asset_urn,
        objective=objective,
        candidates=candidates,
        ranked_choice=ranked_choice,
        rationale=f"Selected {ranked_choice.scenario_type} because it best balances risk, effort, and benefit for the objective: {objective}.",
        explanation=explanation,
        created_at=datetime.now(timezone.utc),
    )