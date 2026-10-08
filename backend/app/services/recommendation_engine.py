from app.models.impact import ImpactReport
from app.models.recommendation import Recommendation


# Decision rules: scenario_type -> (primary_action, fallback_action, title, rationale)
RECOMMENDATION_RULES = {
    "schema_rename": (
        "patch_sql",
        "patch_dbt",
        "Patch downstream transforms",
        "Column rename requires updating downstream SQL/dbt references"
    ),
    "schema_remove": (
        "patch_sql",
        "create_temp_view",
        "Create compatibility view or patch SQL",
        "Removed column breaks downstream consumers - create view or update queries"
    ),
    "owner_missing": (
        "assign_owner",
        "escalate",
        "Assign asset owner",
        "Missing owner delays incident resolution - assign steward immediately"
    ),
    "pipeline_failure": (
        "patch_dag",
        "rollback_change",
        "Patch DAG or retry pipeline",
        "Pipeline failure causes stale data - fix DAG or rollback recent changes"
    ),
    "dataset_deprecation": (
        "archive_asset",
        "escalate",
        "Archive and migrate consumers",
        "Deprecated dataset requires consumer migration plan"
    ),
    "auto_detected": (
        "patch_sql",
        "escalate",
        "Investigate and patch",
        "Auto-detected issue requires investigation before remediation"
    )
}


def _select_action(scenario_type: str, impact: ImpactReport) -> tuple:
    """Select primary and fallback action based on scenario and impact."""
    rule = RECOMMENDATION_RULES.get(scenario_type, RECOMMENDATION_RULES["auto_detected"])
    
    primary, fallback, title, rationale = rule
    
    # Escalate if severity is critical and no owner
    if impact.severity == "critical" and not any("owner" in e.lower() for e in impact.explanation):
        fallback = "escalate"
    
    # If ML models affected, prefer dbt patch over SQL
    if impact.affected_models and primary == "patch_sql":
        primary = "patch_dbt"
    
    return primary, fallback, title, rationale


def _compute_risk(impact: ImpactReport) -> str:
    """Compute risk level based on impact severity and affected assets."""
    if impact.severity == "critical":
        return "critical"
    if impact.severity == "high" or len(impact.affected_models) > 0:
        return "high"
    if impact.severity == "medium" or len(impact.affected_dashboards) > 0:
        return "medium"
    return "low"


def _compute_confidence(scenario_type: str, impact: ImpactReport) -> float:
    """Compute confidence based on scenario type and impact clarity."""
    base_confidence = 0.7
    
    # Higher confidence for well-understood scenarios
    if scenario_type in ["schema_rename", "schema_remove"]:
        base_confidence += 0.1
    
    # Lower confidence if many affected assets (more uncertainty)
    if len(impact.affected_assets) > 5:
        base_confidence -= 0.1
    
    # Lower confidence if no owner (harder to validate)
    if any("owner" in e.lower() for e in impact.explanation):
        base_confidence -= 0.1
    
    return min(max(base_confidence, 0.5), 0.95)


def recommend_action(impact_report: ImpactReport, scenario_type: str = "auto_detected") -> Recommendation:
    """
    Choose the best remediation class based on impact and scenario.
    Returns a Recommendation with primary action and optional fallback.
    """
    primary, fallback, title, rationale = _select_action(scenario_type, impact_report)
    
    risk = _compute_risk(impact_report)
    confidence = _compute_confidence(scenario_type, impact_report)
    
    return Recommendation(
        impact_id=impact_report.impact_id,
        action_type=primary,
        title=title,
        rationale=rationale,
        confidence=confidence,
        risk=risk,
        fallback_action=fallback if fallback != primary else None
    )