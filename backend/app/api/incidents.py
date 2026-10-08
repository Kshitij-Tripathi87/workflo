from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.models import AssetSummary, FixDraft, Incident
from app.connectors.datahub.client import DataHubClient
from app.services.incident_detector import detect_incident
from app.services.impact_analyzer import analyze_blast_radius
from app.services.fix_generator import generate_fix
from app.core.exceptions import CortexError
from app.middleware.auth import get_current_user, require_role
from app.core.auth import User

router = APIRouter(prefix="/incidents", tags=["incidents"])
client = DataHubClient()


class DetectRequest(BaseModel):
    urn: str


class GenerateFixRequest(BaseModel):
    incident: Incident


@router.post("/detect", response_model=Incident | None)
def detect(payload: DetectRequest, user: User = Depends(require_role("analyst"))):
    urn = payload.urn
    if not urn:
        raise HTTPException(status_code=400, detail="urn is required")
    try:
        asset = client.get_asset(urn)
    except CortexError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except KeyError:
        raise HTTPException(status_code=404, detail="Asset not found")

    summary = AssetSummary(
        urn=asset["urn"],
        name=asset["name"],
        description=asset.get("description"),
        owner=asset.get("owner"),
        schema_fields=asset.get("schema_fields", []),
    )
    incident, _scenario = detect_incident(
        summary,
        client.get_expected_schema(urn),
        client.get_schema(urn),
    )
    if incident is None:
        return None
    return analyze_blast_radius(incident, client.get_downstream_assets(urn))

@router.post("/{incident_id}/generate-fix", response_model=FixDraft)
def generate_fix_for_incident(incident_id: str, payload: GenerateFixRequest, user: User = Depends(require_role("analyst"))):
    incident = payload.incident
    # Enforce id match when provided, to handle the case where the client
    # passes an explicit incident_id and a payload id that differs.
    if incident.incident_id != incident_id:
        raise HTTPException(
            status_code=400,
            detail=(
                f"incident_id path mismatch: path={incident_id} != payload={incident.incident_id}"
            ),
        )
    return generate_fix(incident)
