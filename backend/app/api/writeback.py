from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends
from app.models.writeback import WritebackRecord
from app.models.impact import ImpactReport
from app.models.recommendation import Recommendation
from app.models.artifact import ArtifactDraft
from app.services.writeback_service import writeback_service
from app.middleware.auth import get_current_user, require_role
from app.core.auth import User
from app.core.exceptions import CortexError

router = APIRouter(prefix="/writeback", tags=["writeback"])


@router.post("", response_model=WritebackRecord)
def write_resolution(
    asset_urn: str,
    impact_report: ImpactReport,
    recommendation: Recommendation,
    artifact: Optional[ArtifactDraft] = None,
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


@router.get("/{record_id}", response_model=WritebackRecord)
def get_resolution(record_id: str, user: User = Depends(require_role("viewer"))):
    """Get a specific resolution record."""
    record = writeback_service.get_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return record


@router.get("/assets/{urn}/resolutions", response_model=List[WritebackRecord])
def get_asset_resolutions(urn: str, user: User = Depends(require_role("viewer"))):
    """Get all resolutions for an asset."""
    return writeback_service.get_resolutions(urn)