from typing import List, Literal, Optional
from pydantic import BaseModel, Field

from app.core.validators import CortexURN

Severity = Literal["low", "medium", "high", "critical"]
AssetKind = Literal["dataset", "pipeline", "dashboard", "model", "feature"]
EdgeType = Literal["upstream_of", "downstream_of", "owns", "feeds", "trains", "powers"]


class AssetNode(BaseModel):
    """Canonical internal asset representation - the digital twin primitive."""
    urn: CortexURN
    name: str = Field(min_length=1, max_length=255)
    kind: AssetKind = "dataset"
    owner: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = Field(default=None, max_length=2000)
    schema_fields: List[str] = Field(default_factory=list, max_length=500)
    upstream: List[CortexURN] = Field(default_factory=list, max_length=1000)
    downstream: List[CortexURN] = Field(default_factory=list, max_length=1000)
    tags: List[str] = Field(default_factory=list, max_length=100)
    quality_signals: List[str] = Field(default_factory=list, max_length=100)
    governance_signals: List[str] = Field(default_factory=list, max_length=100)
    freshness: Optional[str] = Field(default=None, max_length=64)
    criticality: Severity = "medium"
    status: Optional[str] = Field(default=None, max_length=64)


class GraphEdge(BaseModel):
    """Directed edge in the asset graph."""
    source: CortexURN
    target: CortexURN
    edge_type: EdgeType
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class GraphSnapshot(BaseModel):
    """Snapshot of the asset graph for reasoning."""
    nodes: dict[CortexURN, AssetNode] = Field(default_factory=dict)
    edges: List[GraphEdge] = Field(default_factory=list, max_length=10_000)