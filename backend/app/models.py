from typing import List, Literal, Optional
from pydantic import BaseModel, Field

class AssetSummary(BaseModel):
    urn: str
    name: str
    description: Optional[str] = None
    owner: Optional[str] = None
    schema_fields: List[str] = Field(default_factory=list)

class Incident(BaseModel):
    incident_id: str
    incident_type: Literal["schema_drift", "ownership_gap"]
    severity: Literal["low", "medium", "high", "critical"]
    asset_urn: str
    reason: str
    blast_radius: List[str] = Field(default_factory=list)
    status: Literal["open", "triaged", "fixed", "dismissed"] = "open"

class FixDraft(BaseModel):
    incident_id: str
    title: str
    summary: str
    artifact_type: Literal["sql", "dbt", "dag", "yaml", "markdown"]
    artifact_body: str
    confidence: float = 0.0
