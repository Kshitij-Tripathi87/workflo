from uuid import uuid4

from app.models.scenario import ScenarioRequest
from app.models import AssetSummary, Incident


def detect_incident(asset: AssetSummary, expected_schema: list[str], current_schema: list[str]) -> tuple[Incident | None, ScenarioRequest | None]:
    """
    Detect incidents and return both an Incident and a ScenarioRequest.
    The ScenarioRequest can be fed into the scenario engine for simulation.
    """
    if not asset.owner:
        incident = Incident(
            incident_id=str(uuid4()),
            incident_type="ownership_gap",
            severity="medium",
            asset_urn=asset.urn,
            reason="No owner is assigned to this asset.",
            blast_radius=[],
        )
        scenario = ScenarioRequest(
            asset_urn=asset.urn,
            scenario_type="owner_missing",
            change={"owner": None},
            notes="Auto-detected ownership gap"
        )
        return incident, scenario

    if expected_schema != current_schema:
        removed = [f for f in expected_schema if f not in current_schema]
        added = [f for f in current_schema if f not in expected_schema]
        severity = "critical" if len(removed) > 1 else "high"
        
        incident = Incident(
            incident_id=str(uuid4()),
            incident_type="schema_drift",
            severity=severity,
            asset_urn=asset.urn,
            reason=f"Schema mismatch detected. Removed: {removed}. Added: {added}.",
            blast_radius=[],
        )
        
        if removed:
            scenario = ScenarioRequest(
                asset_urn=asset.urn,
                scenario_type="schema_remove",
                change={"removed": removed, "added": added},
                notes="Auto-detected schema drift"
            )
        else:
            scenario = ScenarioRequest(
                asset_urn=asset.urn,
                scenario_type="schema_rename",
                change={"removed": [], "added": added},
                notes="Auto-detected schema change"
            )
        return incident, scenario

    return None, None