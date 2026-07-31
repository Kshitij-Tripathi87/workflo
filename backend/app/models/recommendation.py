from typing import List, Literal, Optional
from pydantic import BaseModel, Field
from uuid import uuid4

RecommendationAction = Literal[
    "patch_sql",
    "patch_dbt",
    "patch_dag",
    "assign_owner",
    "create_temp_view",
    "rollback_change",
    "archive_asset",
    "escalate"
]


class Recommendation(BaseModel):
    """Remediation plan recommendation."""
    recommendation_id: str = Field(default_factory=lambda: str(uuid4()))
    impact_id: str
    action_type: RecommendationAction
    title: str
    rationale: str
    confidence: float = 0.7
    risk: Literal["low", "medium", "high", "critical"] = "medium"
    artifacts: List[str] = Field(default_factory=list)
    fallback_action: Optional[RecommendationAction] = None