"""Pydantic models for DataHub metadata — the contract between DataHub and Tenant Shield."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class DriftType(str, Enum):
    ADDED = "ADDED"
    REMOVED = "REMOVED"
    TYPE_CHANGED = "TYPE_CHANGED"
    NULLABLE_CHANGED = "NULLABLE_CHANGED"
    DESCRIPTION_CHANGED = "DESCRIPTION_CHANGED"


class DriftSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ColumnDrift(BaseModel):
    column_name: str
    drift_type: DriftType
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    severity: DriftSeverity = DriftSeverity.LOW
    breaking: bool = False
    description: str = ""


class SchemaDiff(BaseModel):
    dataset_urn: str
    baseline_name: str = ""
    current_name: str = ""
    drifts: list[ColumnDrift] = Field(default_factory=list)
    drift_score: float = 0.0  # 0.0 to 1.0 risk score
    breaking_changes: bool = False
    summary: str = ""


class BlastRadiusReport(BaseModel):
    root_urn: str
    affected_datasets: list[str] = Field(default_factory=list)
    max_depth: int = 0
    critical_path_impacted: bool = False
    summary: str = ""


class ColumnInfo(BaseModel):
    name: str
    type: str = Field(description="DataHub-native type string, e.g. 'STRING', 'INT', 'TIMESTAMP'")
    nullable: bool = True
    description: str = ""
    primary_key: bool = False
    foreign_key_to: Optional[str] = Field(default=None, description="If FK, 'dataset.column' string")


class DatasetSchema(BaseModel):
    urn: str = Field(description="DataHub URN, e.g. 'urn:li:dataset:(urn:li:dataPlatform:postgres,public.users,PROD)'")
    name: str
    platform: str = Field(default="", description="Data platform, e.g. 'postgres', 'snowflake', 'bigquery'")
    columns: list[ColumnInfo] = Field(default_factory=list)
    owner: str = ""
    description: str = ""
    last_updated: Optional[datetime] = None


class LineageEdge(BaseModel):
    source_urn: str
    target_urn: str
    source_dataset: str = ""
    target_dataset: str = ""
    column_mappings: list[dict] = Field(default_factory=list, description="[{'source': 'col_a', 'target': 'col_b'}]")


class DataHubEntity(BaseModel):
    urn: str
    type: str = Field(description="dataset, chart, dashboard, mlmodel, etc.")
    name: str
    platform: str = ""
    description: str = ""


class TestArtifact(BaseModel):
    """A single generated test artifact — stored in examples/ for judges."""
    test_name: str
    test_code: str
    dataset_urn: str
    description: str
    soc2_controls: list[str] = Field(default_factory=list)
