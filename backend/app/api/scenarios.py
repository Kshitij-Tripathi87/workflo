from fastapi import APIRouter, HTTPException, Depends
from app.models.scenario import ScenarioRequest, ScenarioResult
from app.connectors.datahub.client import DataHubClient
from app.services.graph_builder import build_snapshot
from app.engine.scenario_engine import apply_scenario
from app.core.exceptions import CortexError
from app.middleware.auth import get_current_user, require_role
from app.core.auth import User

router = APIRouter(prefix="/scenarios", tags=["scenarios"])
client = DataHubClient()


@router.post("/simulate", response_model=ScenarioResult)
def simulate(request: ScenarioRequest, user: User = Depends(require_role("analyst"))):
    """Simulate a hypothetical change on an asset."""
    try:
        # Build graph snapshot centered on the asset
        snapshot = build_snapshot([request.asset_urn])

        if request.asset_urn not in snapshot.nodes:
            raise HTTPException(status_code=404, detail="Asset not found in graph")

        # Apply the scenario
        result = apply_scenario(snapshot, request)
        return result

    except CortexError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{scenario_id}", response_model=ScenarioResult)
def get_scenario(scenario_id: str, user: User = Depends(require_role("viewer"))):
    """Get a scenario result by ID (placeholder - scenarios are stateless)."""
    raise HTTPException(status_code=404, detail="Scenarios are stateless - use /simulate")