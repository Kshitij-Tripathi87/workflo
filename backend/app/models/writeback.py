from datetime import datetime
from typing import List, Literal, Optional
from pydantic import BaseModel, Field
from uuid import uuid4

WritebackStatus = Literal["open", "triaged", "mitigated", "fixed", "dismissed"]


class WritebackRecord(BaseModel):
    """Resolution record written back to DataHub or audit log."""
    record_id: str = Field(default_factory=lambda: str(uuid4()))
    asset_urn: str
    status: WritebackStatus = "open"
    summary: str
    linked_artifact: Optional[str] = None
    affected_assets: List[str] = Field(default_factory=list)
    created_by: str = "system"
    created_at: datetime = Field(default_factory=datetime.utcnow)