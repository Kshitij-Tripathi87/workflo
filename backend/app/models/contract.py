from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ColumnConstraint(BaseModel):
    name: str
    data_type: str
    nullable: bool = True
    is_primary_key: bool = False
    description: str | None = None


class ContractSpec(BaseModel):
    dataset_urn: str
    dataset_name: str
    platform: str = "snowflake"
    owner: str | None = None
    columns: list[ColumnConstraint] = Field(default_factory=list)
    upstream_lineage: list[str] = Field(default_factory=list)
    criticality: str = "medium"
    soc2_controls: list[str] = Field(default_factory=lambda: ["CC6.1", "CC7.2"])


class GeneratedContractTest(BaseModel):
    test_id: str
    dataset_urn: str
    dataset_name: str
    test_code: str
    test_type: Literal["schema_integrity", "lineage_continuity", "ownership_governance", "full_suite"]
    soc2_controls: list[str] = Field(default_factory=lambda: ["CC6.1", "CC7.2"])
    integrity_score: float = Field(default=100.0, ge=0.0, le=100.0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ContractExecutionResult(BaseModel):
    dataset_urn: str
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    skipped_tests: int = 0
    duration_seconds: float = 0.0
    status: Literal["passed", "failed", "warning"] = "passed"
    findings: list[dict[str, Any]] = Field(default_factory=list)
    receipt_id: str | None = None
    soc2_compliance_met: bool = True
