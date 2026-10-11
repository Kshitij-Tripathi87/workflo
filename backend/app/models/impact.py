from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class ImpactReport(BaseModel):
    """Blast-radius analysis result."""
    impact_id: str = Field(default_factory=lambda: str(uuid4()))
    asset_urn: str
    affected_assets: list[str] = Field(default_factory=list)
    affected_dashboards: list[str] = Field(default_factory=list)
    affected_models: list[str] = Field(default_factory=list)
    affected_pipelines: list[str] = Field(default_factory=list)
    severity: Literal["low", "medium", "high", "critical"] = "low"
    reason: str = ""
    confidence: float = 0.8
    explanation: list[str] = Field(default_factory=list)
