"""Metadata inspector — high-level API to 'understand what's connected to what'.

Wraps DataHubClient and adds:
  - Schema integrity scoring (nullability, PK presence, descriptions)
  - Lineage reach analysis (upstream/downstream depth)
  - Owner coverage analysis (unowned datasets)
  - Schema drift detection (compare to a baseline snapshot)
"""

from typing import Optional
from workflo_datahub.client import DataHubClient
from workflo_datahub.models import (
    BlastRadiusReport,
    ColumnDrift,
    DatasetSchema,
    DriftSeverity,
    DriftType,
    LineageEdge,
    SchemaDiff,
)
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

    def detect_schema_drift(self, baseline: DatasetSchema, current: DatasetSchema) -> SchemaDiff:
        """Detect schema differences between baseline and current dataset snapshots."""
        drifts: list[ColumnDrift] = []
        baseline_cols = {c.name: c for c in baseline.columns}
        current_cols = {c.name: c for c in current.columns}

        # 1. Removed columns (in baseline but missing in current)
        for name, base_col in baseline_cols.items():
            if name not in current_cols:
                is_pk = base_col.primary_key
                severity = DriftSeverity.CRITICAL if is_pk else DriftSeverity.HIGH
                drifts.append(
                    ColumnDrift(
                        column_name=name,
                        drift_type=DriftType.REMOVED,
                        old_value=f"{base_col.type} (nullable={base_col.nullable})",
                        new_value=None,
                        severity=severity,
                        breaking=True,
                        description=f"Column '{name}' was dropped from dataset schema.",
                    )
                )

        # 2. Added columns (in current but not in baseline)
        for name, curr_col in current_cols.items():
            if name not in baseline_cols:
                # If non-nullable column is added without default, it may be breaking
                is_breaking = not curr_col.nullable
                severity = DriftSeverity.MEDIUM if is_breaking else DriftSeverity.LOW
                drifts.append(
                    ColumnDrift(
                        column_name=name,
                        drift_type=DriftType.ADDED,
                        old_value=None,
                        new_value=f"{curr_col.type} (nullable={curr_col.nullable})",
                        severity=severity,
                        breaking=is_breaking,
                        description=f"New column '{name}' added with type {curr_col.type}.",
                    )
                )

        # 3. Modified columns (present in both)
        for name, base_col in baseline_cols.items():
            if name in current_cols:
                curr_col = current_cols[name]
                # Type change
                if base_col.type.upper() != curr_col.type.upper():
                    drifts.append(
                        ColumnDrift(
                            column_name=name,
                            drift_type=DriftType.TYPE_CHANGED,
                            old_value=base_col.type,
                            new_value=curr_col.type,
                            severity=DriftSeverity.CRITICAL if base_col.primary_key else DriftSeverity.HIGH,
                            breaking=True,
                            description=f"Column '{name}' type changed from {base_col.type} to {curr_col.type}.",
                        )
                    )
                # Nullability change
                if base_col.nullable != curr_col.nullable:
                    # Changing from nullable=True to nullable=False is breaking
                    is_breaking = (base_col.nullable and not curr_col.nullable)
                    severity = DriftSeverity.HIGH if is_breaking else DriftSeverity.LOW
                    drifts.append(
                        ColumnDrift(
                            column_name=name,
                            drift_type=DriftType.NULLABLE_CHANGED,
                            old_value=f"nullable={base_col.nullable}",
                            new_value=f"nullable={curr_col.nullable}",
                            severity=severity,
                            breaking=is_breaking,
                            description=f"Column '{name}' nullability changed from {base_col.nullable} to {curr_col.nullable}.",
                        )
                    )
                # Description change
                if base_col.description != curr_col.description and (base_col.description or curr_col.description):
                    drifts.append(
                        ColumnDrift(
                            column_name=name,
                            drift_type=DriftType.DESCRIPTION_CHANGED,
                            old_value=base_col.description,
                            new_value=curr_col.description,
                            severity=DriftSeverity.LOW,
                            breaking=False,
                            description=f"Column '{name}' documentation updated.",
                        )
                    )

        # Calculate risk score and summary
        diff = SchemaDiff(
            dataset_urn=current.urn or baseline.urn,
            baseline_name=baseline.name,
            current_name=current.name,
            drifts=drifts,
            breaking_changes=any(d.breaking for d in drifts),
        )
        diff.drift_score = self.calculate_drift_risk(diff)
        diff.summary = (
            f"Detected {len(drifts)} drift items ({sum(1 for d in drifts if d.breaking)} breaking). "
            f"Risk score: {diff.drift_score:.2f}."
        )
        return diff

    def calculate_drift_risk(self, diff: SchemaDiff) -> float:
        """Compute a normalized risk score (0.0 to 1.0) based on severity and breaking changes."""
        if not diff.drifts:
            return 0.0

        weights = {
            DriftSeverity.LOW: 0.1,
            DriftSeverity.MEDIUM: 0.3,
            DriftSeverity.HIGH: 0.6,
            DriftSeverity.CRITICAL: 1.0,
        }

        total_weight = sum(weights[d.severity] for d in diff.drifts)
        # Cap at 1.0
        score = min(1.0, total_weight / 2.0)
        if diff.breaking_changes:
            score = max(score, 0.65)
        return round(score, 2)

    def detect_lineage_blast_radius(self, root_urn: str, max_depth: int = 5) -> BlastRadiusReport:
        """Analyze downstream lineage blast radius for a given dataset URN with cycle protection."""
        visited: set[str] = set()
        queue: list[tuple[str, int]] = [(root_urn, 0)]
        affected: list[str] = []
        furthest_depth = 0

        while queue:
            curr_urn, depth = queue.pop(0)
            if curr_urn in visited or depth > max_depth:
                continue
            visited.add(curr_urn)

            if curr_urn != root_urn:
                affected.append(curr_urn)
                furthest_depth = max(furthest_depth, depth)

            if depth < max_depth:
                downstream_edges = self.get_lineage(curr_urn, "DOWNSTREAM")
                for edge in downstream_edges:
                    target = edge.target_urn
                    if target and target not in visited:
                        queue.append((target, depth + 1))

        critical_path = furthest_depth >= 2 or len(affected) >= 3
        return BlastRadiusReport(
            root_urn=root_urn,
            affected_datasets=affected,
            max_depth=furthest_depth,
            critical_path_impacted=critical_path,
            summary=f"Blast radius contains {len(affected)} downstream datasets across {furthest_depth} hops.",
        )
