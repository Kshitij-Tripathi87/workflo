from datetime import datetime, timezone
from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class SOC2ControlStatus(BaseModel):
    control_id: str  # e.g., "CC6.1", "CC7.2"
    name: str
    description: str
    status: Literal["compliant", "warning", "non_compliant"]
    score: float = Field(ge=0.0, le=100.0)
    audited_assets_count: int
    violating_assets: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)


class ComplianceReport(BaseModel):
    report_id: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    overall_compliance_score: float = Field(ge=0.0, le=100.0)
    status: Literal["passing", "needs_review", "failing"]
    controls: Dict[str, SOC2ControlStatus] = Field(default_factory=dict)
    total_assets: int
    unowned_critical_assets: List[str] = Field(default_factory=list)
    schema_drift_count: int = 0
    cryptographic_receipt_coverage_pct: float = 100.0
