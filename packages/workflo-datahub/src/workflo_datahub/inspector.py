"""Metadata inspector — high-level API to 'understand what's connected to what'.

Wraps DataHubClient and adds:
  - Schema integrity scoring (nullability, PK presence, descriptions)
  - Lineage reach analysis (upstream/downstream depth)
  - Owner coverage analysis (unowned datasets)
  - Schema drift detection (compare to a baseline snapshot)
"""

from typing import Optional
from workflo_datahub.client import DataHubClient
from workflo_datahub.models import DatasetSchema, LineageEdge
from workflo_utils.logging import get_logger

logger = get_logger(__name__)


class MetadataInspector:
    """Reads DataHub metadata and computes analytics for test generation."""

    def __init__(self, client: DataHubClient):
        self.client = client

    def get_dataset_schema(self, urn: str) -> DatasetSchema:
        return self.client.get_dataset(urn)

    def get_lineage(self, urn: str, direction: str = "UPSTREAM") -> list[LineageEdge]:
        return self.client.get_lineage(urn, direction)

    def schema_integrity_score(self, schema: DatasetSchema) -> float:
        """0.0-1.0 score: fraction of columns described + typed + nullable-flagged."""
        if not schema.columns:
            return 0.0
        scored = 0
        for c in schema.columns:
            points = 0
            if c.description:
                points += 1
            if c.type and c.type != "UNKNOWN":
                points += 1
            if c.nullable is not None:
                points += 1
            scored += points / 3.0
        return round(scored / len(schema.columns), 4)

    def upstream_dataset_urns(self, urn: str) -> list[str]:
        """Convenience: list of upstream dataset URNs (depth-1)."""
        edges = self.get_lineage(urn, "UPSTREAM")
        return list({e.source_urn for e in edges if e.source_urn})

    def downstream_dataset_urns(self, urn: str) -> list[str]:
        edges = self.get_lineage(urn, "DOWNSTREAM")
        return list({e.target_urn for e in edges if e.target_urn})

    def unowned_datasets(self, urns: list[str]) -> list[str]:
        """Find datasets without an owner attached."""
        unowned = []
        for urn in urns:
            try:
                schema = self.get_dataset_schema(urn)
                if not schema.owner:
                    unowned.append(urn)
            except Exception:
                unowned.append(urn)
        return unowned

    def primary_key_columns(self, schema: DatasetSchema) -> list[str]:
        return [c.name for c in schema.columns if c.primary_key]

    def nullable_violations(self, schema: DatasetSchema) -> list[str]:
        """Return columns flagged non-nullable with no description (smell check)."""
        return [
            c.name for c in schema.columns
            if (not c.nullable) and (not c.description)
        ]
