from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class SOC2ControlStatus(BaseModel):
    control_id: str  # e.g., "CC6.1", "CC7.2"
    name: str
    description: str
    status: Literal["compliant", "warning", "non_compliant"]
    score: float = Field(ge=0.0, le=100.0)
    audited_assets_count: int
    violating_assets: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class ComplianceReport(BaseModel):
    report_id: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    overall_compliance_score: float = Field(ge=0.0, le=100.0)
    status: Literal["passing", "needs_review", "failing"]
    controls: dict[str, SOC2ControlStatus] = Field(default_factory=dict)
    total_assets: int
    unowned_critical_assets: list[str] = Field(default_factory=list)
    schema_drift_count: int = 0
    cryptographic_receipt_coverage_pct: float = 100.0
