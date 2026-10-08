from fastapi import APIRouter, HTTPException, Depends
from app.models.recommendation import Recommendation
from app.models.artifact import ArtifactDraft
from app.services.artifact_generator import generate_artifact
from app.middleware.auth import get_current_user, require_role
from app.core.auth import User

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


@router.post("/generate", response_model=ArtifactDraft)
def generate(
    recommendation: Recommendation,
    scenario_type: str = "auto_detected",
    asset_name: str = "asset",
    user: User = Depends(require_role("analyst"))
):
    """Generate an artifact from a recommendation."""
    try:
        artifact = generate_artifact(
            recommendation=recommendation,
            scenario_type=scenario_type,
            asset_name=asset_name
        )
        return artifact
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{artifact_id}", response_model=ArtifactDraft)
def get_artifact(artifact_id: str, user: User = Depends(require_role("viewer"))):
    """Get an artifact by ID (placeholder - artifacts are stateless)."""
    raise HTTPException(status_code=404, detail="Artifacts are stateless - use /generate")


@router.get("/{artifact_id}/download")
def download_artifact(artifact_id: str, user: User = Depends(require_role("viewer"))):
    """Download artifact file (placeholder)."""
    raise HTTPException(status_code=404, detail="Download not implemented")