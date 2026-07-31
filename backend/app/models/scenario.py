from typing import Dict, Literal, Optional
from pydantic import BaseModel, Field
from uuid import uuid4

ScenarioType = Literal[
    "schema_rename",
    "schema_remove",
    "owner_missing",
    "pipeline_failure",
    "dataset_deprecation",
    "auto_detected"
]


class ScenarioRequest(BaseModel):
    """Request to simulate a hypothetical change."""
    asset_urn: str
    scenario_type: ScenarioType
    change: Dict = Field(default_factory=dict)
    notes: Optional[str] = None


class ScenarioResult(BaseModel):
    """Result of applying a scenario simulation."""
    scenario_id: str = Field(default_factory=lambda: str(uuid4()))
    asset_urn: str
    scenario_type: str
    applied_change: Dict = Field(default_factory=dict)
    predicted_breakages: list[str] = Field(default_factory=list)
    predicted_severity: Literal["low", "medium", "high", "critical"] = "low"
    confidence: float = 0.85