# Models package - re-export legacy symbols for backward compatibility
from app.models.asset import AssetNode, GraphEdge, GraphSnapshot, Severity
from app.models.scenario import ScenarioRequest, ScenarioResult
from app.models.impact import ImpactReport
from app.models.recommendation import Recommendation
from app.models.artifact import ArtifactDraft
from app.models.writeback import WritebackRecord, WritebackStatus
from app.models.contract import ContractSpec, GeneratedContractTest, ContractExecutionResult, ColumnConstraint
from app.models.receipt import SignedReceipt, TeardownProof, ReceiptVerificationResponse
from app.models.compliance import SOC2ControlStatus, ComplianceReport

# Legacy re-exports for backward compatibility
from pydantic import BaseModel, Field
from typing import List, Literal, Optional


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


__all__ = [
    "AssetNode",
    "GraphEdge",
    "GraphSnapshot",
    "Severity",
    "ScenarioRequest",
    "ScenarioResult",
    "ImpactReport",
    "Recommendation",
    "ArtifactDraft",
    "WritebackRecord",
    "WritebackStatus",
    "AssetSummary",
    "Incident",
    "FixDraft",
    "ContractSpec",
    "GeneratedContractTest",
    "ContractExecutionResult",
    "ColumnConstraint",
    "SignedReceipt",
    "TeardownProof",
    "ReceiptVerificationResponse",
    "SOC2ControlStatus",
    "ComplianceReport",
]