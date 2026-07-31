from pydantic import BaseModel, Field
from typing import List, Dict, Literal, Optional
from datetime import datetime

ScenarioType = Literal[
    "schema_rename",
    "schema_remove",
    "owner_missing",
    "pipeline_failure",
    "dataset_deprecation",
    "do_nothing",
    "patch_sql",
    "patch_dbt",
    "patch_dag",
    "create_temp_view",
    "archive_asset",
    "escalate",
]


class FutureScenario(BaseModel):
    """A candidate future state with predicted outcomes."""
    future_id: str
    asset_urn: str
    scenario_type: ScenarioType
    change: Dict = Field(default_factory=dict)
    predicted_severity: int = Field(ge=0, le=100)
    predicted_effort: int = Field(ge=0, le=100)
    predicted_benefit: int = Field(ge=0, le=100)
    predicted_blast_radius: int = Field(default=0, ge=0)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: List[str] = Field(default_factory=list)
    affected_dashboards: int = Field(default=0, ge=0)
    affected_models: int = Field(default=0, ge=0)
    affected_pipelines: int = Field(default=0, ge=0)


class PolicyResultSummary(BaseModel):
    """Compact summary of policy evaluation, attached to a FuturePlan."""
    verdict: str = "pass"
    results: List[Dict] = Field(default_factory=list)


class FuturePlan(BaseModel):
    """Ranked plan containing candidate futures and the best choice."""
    plan_id: str
    asset_urn: str
    objective: str
    candidates: List[FutureScenario]
    ranked_choice: FutureScenario
    rationale: str
    explanation: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    policy_result: Optional[PolicyResultSummary] = None