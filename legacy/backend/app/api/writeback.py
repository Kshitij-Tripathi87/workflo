
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import User
from app.core.exceptions import CortexError
from app.middleware.auth import require_role
from app.models.artifact import ArtifactDraft
from app.models.impact import ImpactReport
from app.models.recommendation import Recommendation
from app.models.writeback import WritebackRecord
from app.services.datahub_writeback import record_verdict_assertion
from app.services.writeback_service import writeback_service

router = APIRouter(prefix="/writeback", tags=["writeback"])


@router.post("", response_model=WritebackRecord)
def write_resolution(
    asset_urn: str,
    impact_report: ImpactReport,
    recommendation: Recommendation,
    artifact: ArtifactDraft | None = None,
    user: User = Depends(require_role("analyst")),
):
    """Record a resolution to the writeback log."""
    try:
        record = writeback_service.record_resolution(
            asset_urn=asset_urn,
            impact_report=impact_report,
            recommendation=recommendation,
            artifact=artifact,
            created_by=user.subject
        )
        return record
    except CortexError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class VerdictAssertionRequest(BaseModel):
    """Request body for the verdict-assertion writeback endpoint."""
    asset_urn: str
    asset_name: str
    verdict: str
    reason: str
    severity: str = "medium"
    blast_radius: int = 0
    run_id: str | None = None


class VerdictAssertionResponse(BaseModel):
    """Response payload — what was written to DataHub."""
    run_id: str
    asset_urn: str
    verdict: str
    written_to_datahub: bool


@router.post("/assertion", response_model=VerdictAssertionResponse)
async def write_verdict_assertion(
    payload: VerdictAssertionRequest,
    user: User = Depends(require_role("analyst")),
):
    """Cherry #2 — record a Cortex verdict as a DataHub assertion.

    Persists to the JSONL log always; also writes tags + documentation
    to DataHub when a real client is configured. Future agents or
    humans viewing the asset in DataHub will see the verdict history.
    """
    from app.connectors.datahub.adapter import adapter

    try:
        result = await record_verdict_assertion(
            asset_urn=payload.asset_urn,
            asset_name=payload.asset_name,
            verdict=payload.verdict,
            reason=payload.reason,
            severity=payload.severity,
            blast_radius=payload.blast_radius,
            run_id=payload.run_id,
            created_by=user.subject,
        )
        return VerdictAssertionResponse(
            run_id=result["run_id"],
            asset_urn=result["urn"],
            verdict=result["verdict"],
            written_to_datahub=adapter.async_client is not None,
        )
    except CortexError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{record_id}", response_model=WritebackRecord)
def get_resolution(record_id: str, user: User = Depends(require_role("viewer"))):
    """Get a specific resolution record."""
    record = writeback_service.get_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return record


@router.get("/assets/{urn}/resolutions", response_model=list[WritebackRecord])
def get_asset_resolutions(urn: str, user: User = Depends(require_role("viewer"))):
    """Get all resolutions for an asset."""
    return writeback_service.get_resolutions(urn)
