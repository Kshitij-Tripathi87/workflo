from copy import deepcopy
from app.models.asset import GraphSnapshot, AssetNode
from app.models.scenario import ScenarioRequest, ScenarioResult


def _apply_schema_rename(node: AssetNode, change: dict) -> tuple[AssetNode, list[str]]:
    node = deepcopy(node)
    removed = change.get("removed", [])
    added = change.get("added", [])
    breakages = []

    new_fields = []
    for field in node.schema_fields:
        if field in removed:
            breakages.append(f"Field '{field}' renamed - downstream references may break")
            idx = removed.index(field)
            if idx < len(added):
                new_fields.append(added[idx])
        else:
            new_fields.append(field)

    for field in added:
        if field not in new_fields:
            new_fields.append(field)

    node.schema_fields = new_fields
    return node, breakages


def _apply_schema_remove(node: AssetNode, change: dict) -> tuple[AssetNode, list[str]]:
    node = deepcopy(node)
    removed = change.get("removed", [])
    breakages = []

    node.schema_fields = [f for f in node.schema_fields if f not in removed]
    for field in removed:
        breakages.append(f"Field '{field}' removed - downstream consumers will fail")

    return node, breakages


def _apply_owner_missing(node: AssetNode, change: dict) -> tuple[AssetNode, list[str]]:
    node = deepcopy(node)
    node.owner = None
    breakages = ["No owner assigned - incident resolution will be delayed"]
    return node, breakages


def _apply_pipeline_failure(node: AssetNode, change: dict) -> tuple[AssetNode, list[str]]:
    node = deepcopy(node)
    node.status = "failed"
    breakages = ["Pipeline failed - downstream data will be stale"]
    return node, breakages


def _apply_dataset_deprecation(node: AssetNode, change: dict) -> tuple[AssetNode, list[str]]:
    node = deepcopy(node)
    node.status = "deprecated"
    breakages = ["Dataset deprecated - all consumers must migrate"]
    return node, breakages


def apply_scenario(snapshot: GraphSnapshot, request: ScenarioRequest) -> ScenarioResult:
    node = snapshot.nodes.get(request.asset_urn)
    if not node:
        return ScenarioResult(
            asset_urn=request.asset_urn,
            scenario_type=request.scenario_type,
            applied_change=request.change,
            predicted_breakages=["Asset not found in graph"],
            predicted_severity="low",
            confidence=0.5
        )

    breakages = []
    modified_node = node

    if request.scenario_type == "schema_rename":
        modified_node, breakages = _apply_schema_rename(node, request.change)
    elif request.scenario_type == "schema_remove":
        modified_node, breakages = _apply_schema_remove(node, request.change)
    elif request.scenario_type == "owner_missing":
        modified_node, breakages = _apply_owner_missing(node, request.change)
    elif request.scenario_type == "pipeline_failure":
        modified_node, breakages = _apply_pipeline_failure(node, request.change)
    elif request.scenario_type == "dataset_deprecation":
        modified_node, breakages = _apply_dataset_deprecation(node, request.change)
    elif request.scenario_type == "auto_detected":
        if "removed" in request.change:
            modified_node, breakages = _apply_schema_remove(node, request.change)
        elif request.change.get("owner") is None:
            modified_node, breakages = _apply_owner_missing(node, request.change)

    snapshot.nodes[request.asset_urn] = modified_node

    severity = "low"
    if len(breakages) >= 3 or node.criticality == "critical":
        severity = "critical"
    elif len(breakages) >= 2 or node.criticality == "high":
        severity = "high"
    elif len(breakages) >= 1:
        severity = "medium"

    return ScenarioResult(
        asset_urn=request.asset_urn,
        scenario_type=request.scenario_type,
        applied_change=request.change,
        predicted_breakages=breakages,
        predicted_severity=severity,
        confidence=0.85
    )