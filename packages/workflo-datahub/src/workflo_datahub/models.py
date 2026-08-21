"""Pydantic models for DataHub metadata — the contract between DataHub and Tenant Shield."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


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
