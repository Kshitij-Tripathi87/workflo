from typing import Literal, Optional
from pydantic import BaseModel, Field
from uuid import uuid4

ArtifactType = Literal["sql", "dbt", "dag", "yaml", "markdown"]


class ArtifactDraft(BaseModel):
    """Generated remediation artifact."""
    artifact_id: str = Field(default_factory=lambda: str(uuid4()))
    recommendation_id: str
    artifact_type: ArtifactType
    title: str
    body: str
    file_path: Optional[str] = None
    confidence: float = 0.75