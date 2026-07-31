from typing import List, Literal
from pydantic import BaseModel, Field
from uuid import uuid4


class ImpactReport(BaseModel):
    """Blast-radius analysis result."""
    impact_id: str = Field(default_factory=lambda: str(uuid4()))
    asset_urn: str
    affected_assets: List[str] = Field(default_factory=list)
    affected_dashboards: List[str] = Field(default_factory=list)
    affected_models: List[str] = Field(default_factory=list)
    affected_pipelines: List[str] = Field(default_factory=list)
    severity: Literal["low", "medium", "high", "critical"] = "low"
    reason: str = ""
    confidence: float = 0.8
    explanation: List[str] = Field(default_factory=list)