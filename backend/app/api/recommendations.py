from fastapi import APIRouter, HTTPException, Depends
from app.models.impact import ImpactReport
from app.models.recommendation import Recommendation
from app.services.recommendation_engine import recommend_action
from app.middleware.auth import get_current_user, require_role
from app.core.auth import User

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.post("/generate", response_model=Recommendation)
def generate(impact_report: ImpactReport, scenario_type: str = "auto_detected", user: User = Depends(require_role("analyst"))):
    """Generate a recommendation based on impact analysis."""
    try:
        recommendation = recommend_action(impact_report, scenario_type)
        return recommendation
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{recommendation_id}", response_model=Recommendation)
def get_recommendation(recommendation_id: str, user: User = Depends(require_role("viewer"))):
    """Get a recommendation by ID (placeholder - recommendations are stateless)."""
    raise HTTPException(status_code=404, detail="Recommendations are stateless - use /generate")