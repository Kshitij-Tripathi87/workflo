from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

ArtifactType = Literal["sql", "dbt", "dag", "yaml", "markdown"]


class ArtifactDraft(BaseModel):
    """Generated remediation artifact."""
    artifact_id: str = Field(default_factory=lambda: str(uuid4()))
    recommendation_id: str
    artifact_type: ArtifactType
    title: str
    body: str
    file_path: str | None = None
    confidence: float = 0.75
