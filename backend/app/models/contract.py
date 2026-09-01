from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class ColumnConstraint(BaseModel):
    name: str
    data_type: str
    nullable: bool = True
    is_primary_key: bool = False
    description: Optional[str] = None


class ContractSpec(BaseModel):
    dataset_urn: str
    dataset_name: str
    platform: str = "snowflake"
    owner: Optional[str] = None
    columns: List[ColumnConstraint] = Field(default_factory=list)
    upstream_lineage: List[str] = Field(default_factory=list)
    criticality: str = "medium"
    soc2_controls: List[str] = Field(default_factory=lambda: ["CC6.1", "CC7.2"])


class GeneratedContractTest(BaseModel):
    test_id: str
    dataset_urn: str
    dataset_name: str
    test_code: str
    test_type: Literal["schema_integrity", "lineage_continuity", "ownership_governance", "full_suite"]
    soc2_controls: List[str] = Field(default_factory=lambda: ["CC6.1", "CC7.2"])
    integrity_score: float = Field(default=100.0, ge=0.0, le=100.0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ContractExecutionResult(BaseModel):
    dataset_urn: str
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    skipped_tests: int = 0
    duration_seconds: float = 0.0
    status: Literal["passed", "failed", "warning"] = "passed"
    findings: List[Dict[str, Any]] = Field(default_factory=list)
    receipt_id: Optional[str] = None
    soc2_compliance_met: bool = True
