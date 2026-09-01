"""Generate example test artifacts for the hackathon submission.

This script demonstrates Tenant Shield's metadata-aware test generation
using sample DataHub metadata. It produces example pytest files in
examples/generated-tests/ so judges can evaluate the quality.

Run:
    python examples/generate_examples.py
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ensure package can be imported when run directly
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "datahub-client" / "src"))

from workflo_datahub.generator import TestGenerator
from workflo_datahub.client import DataHubClient
from workflo_datahub.models import DatasetSchema, ColumnInfo, LineageEdge, TestArtifact
from workflo_datahub.inspector import MetadataInspector
from workflo_datahub.writeback import ResultWriteback


# Sample DataHub metadata for a realistic B2B SaaS (WorkFlow Pro):
#  - users table (company1 tenant)
#  - projects table (tenant-scoped via tenant_id FK)

USERS_SCHEMA = DatasetSchema(
    urn="urn:li:dataset:(urn:li:dataPlatform:postgres,public.users,PROD)",
    name="public.users",
    platform="postgres",
    owner="data-team@workflowpro.com",
    description="All users across the multi-tenant SaaS — tenant-scoped.",
    columns=[
        ColumnInfo(name="id", type="INT", nullable=False, description="Primary key", primary_key=True),
        ColumnInfo(name="email", type="STRING", nullable=False, description="User email (unique per tenant)"),
        ColumnInfo(name="tenant_id", type="STRING", nullable=False, description="Tenant identifier for row-level isolation"),
        ColumnInfo(name="role", type="STRING", nullable=False, description="One of: admin, manager, employee"),
        ColumnInfo(name="created_at", type="TIMESTAMP", nullable=False, description="Row creation timestamp"),
        ColumnInfo(name="last_login", type="TIMESTAMP", nullable=True, description="Most recent login (nullable for never-logged-in)"),
    ],
)

PROJECTS_SCHEMA = DatasetSchema(
    urn="urn:li:dataset:(urn:li:dataPlatform:postgres,public.projects,PROD)",
    name="public.projects",
    platform="postgres",
    owner="data-team@workflowpro.com",
    description="Project records — each belongs to a tenant.",
    columns=[
        ColumnInfo(name="id", type="STRING", nullable=False, description="UUID PK", primary_key=True),
        ColumnInfo(name="tenant_id", type="STRING", nullable=False, description="FK to users.tenant_id — row-level isolation key"),
        ColumnInfo(name="name", type="STRING", nullable=False, description="Project name"),
        ColumnInfo(name="status", type="STRING", nullable=True, description="One of: active, archived, draft"),
        ColumnInfo(name="description", type="TEXT", nullable=True, description="Long-form description (nullable)"),
        ColumnInfo(name="created_at", type="TIMESTAMP", nullable=False, description="Creation timestamp"),
    ],
)

USERS_LINEAGE = [
    LineageEdge(
        source_urn="urn:li:dataset:(urn:li:dataPlatform:kafka,events.user_signup,PROD)",
        target_urn="urn:li:dataset:(urn:li:dataPlatform:postgres,public.users,PROD)",
        source_dataset="events.user_signup",
        target_dataset="public.users",
        column_mappings=[
            {"source": "user_id", "target": "id"},
            {"source": "email_address", "target": "email"},
        ],
    ),
]

PROJECTS_LINEAGE = [
    LineageEdge(
        source_urn="urn:li:dataset:(urn:li:dataPlatform:postgres,public.users,PROD)",
        target_urn="urn:li:dataset:(urn:li:dataPlatform:postgres,public.projects,PROD)",
        source_dataset="public.users",
        target_dataset="public.projects",
        column_mappings=[
            {"source": "tenant_id", "target": "tenant_id"},
        ],
    ),
]

AN_EVENT_URN = "urn:li:dataset:(urn:li:dataPlatform:postgres,public.events,PROD)"


def _generate_examples() -> int:
    output_dir = Path(__file__).parent / "generated-tests"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Mock DataHubClient so we don't need a live server for the demo
    with patch.object(DataHubClient, "get_dataset", side_effect=lambda urn, *a, **k: {
        USERS_SCHEMA.urn: USERS_SCHEMA,
        PROJECTS_SCHEMA.urn: PROJECTS_SCHEMA,
    }.get(urn, USERS_SCHEMA)), patch.object(
        DataHubClient, "get_lineage", side_effect=lambda urn, *a, **k: {
            USERS_SCHEMA.urn: USERS_LINEAGE,
            PROJECTS_SCHEMA.urn: PROJECTS_LINEAGE,
        }.get(urn, USERS_LINEAGE),
    ):
        client = DataHubClient(server_url="http://localhost:8080")
        gen = TestGenerator(client)

        # Generate the full suite for both datasets
        artifacts = []
        datasets = [USERS_SCHEMA.urn, PROJECTS_SCHEMA.urn]
        for urn in datasets:
            artifacts.append(gen.generate_schema_tests(urn))
            artifacts.append(gen.generate_lineage_tests(urn, "UPSTREAM"))
            artifacts.append(gen.generate_ownership_tests(urn))

    if not artifacts:
        print("No artifacts generated — check mocks")
        return 1

    # Write each artifact to its own file (respecting pytest's test_ prefix)
    written = []
    for art in artifacts:
        fname = art.test_name + ".py"
        fpath = output_dir / fname
        fpath.write_text(art.test_code, encoding="utf-8")
        written.append(fpath.name)

    # Also produce a manifest the judges can read
    manifest_lines = ["# Generated test artifacts (examples/)\n\n"]
    manifest_lines.append("| File | Dataset | Description | SOC 2 controls |\n")
    manifest_lines.append("|---|---|---|---|\n")
    for a in artifacts:
        manifest_lines.append(
            f"| `{a.test_name}.py` | `{a.dataset_urn[-30:]}` | {a.description} | {', '.join(a.soc2_controls)} |\n"
        )
    (output_dir / "MANIFEST.md").write_text("".join(manifest_lines), encoding="utf-8")

    print(f"Generated {len(written)} test files in {output_dir}:")
    for w in written:
        print(f"  - {w}")
    print()
    print("Next: open examples/generated-tests/test_*.py to see the quality")
    print("      open examples/generated-tests/MANIFEST.md for an index")
    return 0


if __name__ == "__main__":
    raise SystemExit(_generate_examples())
