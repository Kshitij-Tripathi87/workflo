from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

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
    change: dict = Field(default_factory=dict)
    notes: str | None = None


class ScenarioResult(BaseModel):
    """Result of applying a scenario simulation."""
    scenario_id: str = Field(default_factory=lambda: str(uuid4()))
    asset_urn: str
    scenario_type: str
    applied_change: dict = Field(default_factory=dict)
    predicted_breakages: list[str] = Field(default_factory=list)
    predicted_severity: Literal["low", "medium", "high", "critical"] = "low"
    confidence: float = 0.85
