from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.receipt import SignedReceipt

# NOTE: this vocabulary is the *action* vocabulary (it already contains
# do_nothing/patch_sql/... actions), and must stay a superset of the actions
# `future_search_engine._build_candidates` emits. It was missing
# "assign_owner", which made generate_futures() raise ValidationError for any
# asset without an owner - i.e. exactly the flagship scenario.
ScenarioType = Literal[
    "schema_rename",
    "schema_remove",
    "owner_missing",
    "pipeline_failure",
    "dataset_deprecation",
    "do_nothing",
    "assign_owner",
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
    change: dict = Field(default_factory=dict)
    predicted_severity: int = Field(ge=0, le=100)
    predicted_effort: int = Field(ge=0, le=100)
    predicted_benefit: int = Field(ge=0, le=100)
    predicted_blast_radius: int = Field(default=0, ge=0)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)
    affected_dashboards: int = Field(default=0, ge=0)
    affected_models: int = Field(default=0, ge=0)
    affected_pipelines: int = Field(default=0, ge=0)


class PolicyResultSummary(BaseModel):
    """Compact summary of policy evaluation, attached to a FuturePlan."""
    verdict: str = "pass"
    results: list[dict] = Field(default_factory=list)


class FuturePlan(BaseModel):
    """Ranked plan containing candidate futures and the best choice."""
    plan_id: str
    asset_urn: str
    objective: str
    candidates: list[FutureScenario]
    ranked_choice: FutureScenario
    rationale: str
    explanation: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    policy_result: PolicyResultSummary | None = None
    receipt: SignedReceipt | None = None
