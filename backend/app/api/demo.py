from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Any, Dict, Optional

from app.models.scenario import ScenarioRequest, ScenarioResult
from app.models.impact import ImpactReport
from app.models.recommendation import Recommendation
from app.models.artifact import ArtifactDraft
from app.models.writeback import WritebackRecord
from app.connectors.datahub.client import DataHubClient
from app.services.graph_builder import build_snapshot
from app.engine.scenario_engine import apply_scenario
from app.engine.impact_engine import analyze_impact
from app.services.recommendation_engine import recommend_action
from app.services.artifact_generator import generate_artifact
from app.services.writeback_service import writeback_service
from app.middleware.auth import get_current_user, require_role
from app.core.auth import User
from app.core.exceptions import CortexError

router = APIRouter(prefix="/demo", tags=["demo"])
client = DataHubClient()


class DemoRequest(BaseModel):
    """Request to run the full demo flow."""
    asset_urn: str
    scenario_type: str = "schema_remove"
    change: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None


class DemoResponse(BaseModel):
    """Response containing the full demo flow result."""
    asset: dict
    scenario: ScenarioResult
    impact: ImpactReport
    recommendation: Recommendation
    artifact: ArtifactDraft
    writeback: WritebackRecord


@router.post("/run", response_model=DemoResponse)
def run_demo(request: DemoRequest, user: User = Depends(require_role("analyst"))):
    """
    Run the full Cortex demo flow in one call.
    This is the endpoint for judge demos - one button to prove the whole system works.
    """
    try:
        # Step 1: Load asset
        asset = client.get_asset(request.asset_urn)

        # Step 2: Build graph snapshot
        snapshot = build_snapshot([request.asset_urn])

        # Step 3: Create and apply scenario (deepcopy to avoid mutation)
        from copy import deepcopy
        candidate_snapshot = deepcopy(snapshot)
        scenario_request = ScenarioRequest(
            asset_urn=request.asset_urn,
            scenario_type=request.scenario_type,
            change=request.change or {},
            notes=request.notes
        )
        scenario_result = apply_scenario(candidate_snapshot, scenario_request)

        # Step 4: Analyze impact
        impact_report = analyze_impact(candidate_snapshot, scenario_result)

        # Step 5: Generate recommendation
        recommendation = recommend_action(impact_report, request.scenario_type)

        # Step 6: Generate artifact
        artifact = generate_artifact(
            recommendation=recommendation,
            scenario_type=request.scenario_type,
            asset_name=asset["name"]
        )

        # Step 7: Write back resolution
        writeback_record = writeback_service.record_resolution(
            asset_urn=request.asset_urn,
            impact_report=impact_report,
            recommendation=recommendation,
            artifact=artifact,
            created_by=user.subject,
        )

        return DemoResponse(
            asset=asset,
            scenario=scenario_result,
            impact=impact_report,
            recommendation=recommendation,
            artifact=artifact,
            writeback=writeback_record
        )

    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"Asset not found: {e}")
    except CortexError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")
