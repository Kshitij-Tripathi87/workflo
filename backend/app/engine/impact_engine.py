from app.models.asset import GraphSnapshot
from app.models.scenario import ScenarioResult
from app.models.impact import ImpactReport
from app.engine.graph import get_all_downstream


WEIGHT_DOWNSTREAM_COUNT = 10
WEIGHT_DEPTH = 15
WEIGHT_CRITICALITY = {"low": 0, "medium": 10, "high": 25, "critical": 40}
WEIGHT_OWNER_GAP = 15
WEIGHT_ML_DEPENDENCY = 20
WEIGHT_PIPELINE_STATUS = 20


def _collect_affected_assets(snapshot: GraphSnapshot, start_urn: str) -> dict:
    affected_urns = get_all_downstream(snapshot, start_urn)

    affected = {
        "assets": [],
        "dashboards": [],
        "models": [],
        "pipelines": []
    }

    for urn in affected_urns:
        node = snapshot.nodes.get(urn)
        if node:
            affected["assets"].append(urn)
            if node.kind == "dashboard":
                affected["dashboards"].append(urn)
            elif node.kind == "model":
                affected["models"].append(urn)
            elif node.kind == "pipeline":
                affected["pipelines"].append(urn)

    return affected


def _compute_depth(snapshot: GraphSnapshot, start_urn: str, visited: set = None) -> int:
    if visited is None:
        visited = set()

    node = snapshot.nodes.get(start_urn)
    if not node or not node.downstream:
        return 0

    max_depth = 0
    for downstream_urn in node.downstream:
        if downstream_urn not in visited and downstream_urn in snapshot.nodes:
            visited.add(downstream_urn)
            depth = 1 + _compute_depth(snapshot, downstream_urn, visited)
            max_depth = max(max_depth, depth)

    return max_depth


def _has_ml_dependency(snapshot: GraphSnapshot, start_urn: str, visited: set = None) -> bool:
    if visited is None:
        visited = set()

    node = snapshot.nodes.get(start_urn)
    if not node:
        return False

    for downstream_urn in node.downstream:
        if downstream_urn not in visited and downstream_urn in snapshot.nodes:
            visited.add(downstream_urn)
            downstream_node = snapshot.nodes[downstream_urn]
            if downstream_node.kind == "model":
                return True
            if _has_ml_dependency(snapshot, downstream_urn, visited):
                return True

    return False


def _build_explanation(affected: dict, severity_score: int, node) -> list[str]:
    explanations = []

    downstream_count = len(affected["assets"])
    if downstream_count > 0:
        explanations.append(f"This asset feeds {downstream_count} downstream asset(s).")
    else:
        explanations.append("No downstream assets affected directly.")

    if affected["dashboards"]:
        explanations.append(f"Impacts {len(affected['dashboards'])} dashboard(s).")

    if affected["models"]:
        explanations.append(f"Impacts {len(affected['models'])} ML model(s).")

    if affected["pipelines"]:
        explanations.append(f"Impacts {len(affected['pipelines'])} pipeline(s).")

    if node.criticality in ["high", "critical"]:
        explanations.append(f"Asset is marked as {node.criticality} criticality.")

    if not node.owner:
        explanations.append("No owner is assigned - resolution may be delayed.")

    if severity_score >= 75:
        explanations.append("Immediate attention required.")
    elif severity_score >= 50:
        explanations.append("High priority - multiple critical dependencies affected.")

    return explanations


def analyze_impact(snapshot: GraphSnapshot, scenario_result: ScenarioResult) -> ImpactReport:
    start_node = snapshot.nodes.get(scenario_result.asset_urn)
    if not start_node:
        return ImpactReport(
            asset_urn=scenario_result.asset_urn,
            severity="low",
            reason="Asset not found in graph",
            explanation=["Asset not found - cannot compute impact"]
        )

    affected = _collect_affected_assets(snapshot, scenario_result.asset_urn)

    downstream_count = len(affected["assets"])
    depth = _compute_depth(snapshot, scenario_result.asset_urn)
    criticality_weight = WEIGHT_CRITICALITY.get(start_node.criticality, 10)
    owner_gap_weight = WEIGHT_OWNER_GAP if not start_node.owner else 0
    ml_dep_weight = WEIGHT_ML_DEPENDENCY if _has_ml_dependency(snapshot, scenario_result.asset_urn) else 0

    pipeline_status_weight = 0
    if start_node.kind == "pipeline" and start_node.status == "failed":
        pipeline_status_weight = WEIGHT_PIPELINE_STATUS

    severity_score = (
        min(downstream_count * WEIGHT_DOWNSTREAM_COUNT, 30) +
        min(depth * WEIGHT_DEPTH, 30) +
        criticality_weight +
        owner_gap_weight +
        ml_dep_weight +
        pipeline_status_weight
    )

    if severity_score >= 75:
        severity = "critical"
    elif severity_score >= 50:
        severity = "high"
    elif severity_score >= 25:
        severity = "medium"
    else:
        severity = "low"

    severity_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    if severity_order.get(severity, 0) < severity_order.get(scenario_result.predicted_severity, 0):
        severity = scenario_result.predicted_severity

    if (
        scenario_result.scenario_type == "auto_detected"
        and scenario_result.predicted_severity == "low"
        and severity_order.get(severity, 0) >= 2
    ):
        severity = "medium"

    explanation = _build_explanation(affected, severity_score, start_node)

    reason = f"Scenario '{scenario_result.scenario_type}' on {start_node.name} "
    reason += f"affects {downstream_count} downstream asset(s) with severity {severity}."

    return ImpactReport(
        asset_urn=scenario_result.asset_urn,
        affected_assets=affected["assets"],
        affected_dashboards=affected["dashboards"],
        affected_models=affected["models"],
        affected_pipelines=affected["pipelines"],
        severity=severity,
        reason=reason,
        confidence=0.8,
        explanation=explanation
    )