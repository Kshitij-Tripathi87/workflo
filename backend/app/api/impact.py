from fastapi import APIRouter, HTTPException, Depends
from app.models.scenario import ScenarioResult
from app.models.impact import ImpactReport
from app.services.graph_builder import build_snapshot
from app.engine.impact_engine import analyze_impact
from app.core.exceptions import CortexError
from app.middleware.auth import get_current_user, require_role
from app.core.auth import User

router = APIRouter(prefix="/impact", tags=["impact"])


@router.post("/analyze", response_model=ImpactReport)
def analyze(scenario_result: ScenarioResult, user: User = Depends(require_role("analyst"))):
    """Analyze the impact of a scenario."""
    try:
        # Build graph snapshot
        snapshot = build_snapshot([scenario_result.asset_urn])

        if scenario_result.asset_urn not in snapshot.nodes:
            raise HTTPException(status_code=404, detail="Asset not found in graph")

        # Analyze impact
        report = analyze_impact(snapshot, scenario_result)
        return report

    except CortexError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{impact_id}", response_model=ImpactReport)
def get_impact(impact_id: str, user: User = Depends(require_role("viewer"))):
    """Get an impact report by ID (placeholder - reports are stateless)."""
    raise HTTPException(status_code=404, detail="Impact reports are stateless - use /analyze")