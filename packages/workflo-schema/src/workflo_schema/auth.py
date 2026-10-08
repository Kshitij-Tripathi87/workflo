"""Auth and org models — shared between Backend and Dashboard."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

from workflo_schema.enums import PlanTier, ApiKeyScope


class Organization(BaseModel):
    id: str
    name: str
    plan_tier: PlanTier = PlanTier.FREE
    created_at: Optional[datetime] = None


class Project(BaseModel):
    id: str
    org_id: str
    name: str
    config_json: dict = Field(default_factory=dict, description="Default env vars, base URLs, tenant IDs")


class ApiKey(BaseModel):
    id: str
    project_id: str
    label: str = Field(default="", description="User-defined label, e.g. 'CI-Pipeline-Key'")
    scopes: list[ApiKeyScope] = Field(default_factory=list)
    last_used: Optional[datetime] = None
    expires_at: Optional[datetime] = None

    def has_scope(self, scope: ApiKeyScope) -> bool:
        return scope in self.scopes
