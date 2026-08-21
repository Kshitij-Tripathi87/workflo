"""Tenant Shield DataHub integration package.

Connects to DataHub via GraphQL API (direct) or MCP Server to read
metadata (datasets, schemas, lineage, ownership). Used by the test
generator to produce metadata-aware pytest tests that work on the
first try, and by the result writer to write assertions back.
"""

from workflo_datahub.client import DataHubClient
from workflo_datahub.models import DatasetSchema, ColumnInfo, LineageEdge, DataHubEntity, TestArtifact
from workflo_datahub.inspector import MetadataInspector
from workflo_datahub.writeback import ResultWriteback
from workflo_datahub.generator import TestGenerator

__all__ = [
    "DataHubClient",
    "MetadataInspector",
    "ResultWriteback",
    "TestGenerator",
    "DatasetSchema",
    "ColumnInfo",
    "LineageEdge",
    "DataHubEntity",
    "TestArtifact",
]

__version__ = "0.1.0"
