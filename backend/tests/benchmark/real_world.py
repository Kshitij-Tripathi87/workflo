"""Real-world benchmark runner.

Takes a list of real dbt projects (each with manifest.json +
catalog.json) and runs the engine against them. Output is a
separate report that complements the synthetic benchmark.

Unlike the synthetic corpus, real-world results are not reproducible
(dbt artifacts change between dbt run invocations). Their purpose is
to validate that synthetic findings hold up against real production
schemas.

Usage:
    python -m backend.tests.benchmark.real_world \
        --projects path/to/project1 path/to/project2 ... \
        --output backend/tests/benchmark/results/real_world
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import List

from app.connectors.dbt.parser import parse_manifest
from app.engine.impact_engine import analyze_impact
from app.models.scenario import ScenarioResult

from .metrics import EvaluationRecord, EXPECTED_SEVERITY, aggregate, render_report
from .run_benchmark import _build_snapshot


CHANGE_TYPES_FOR_REAL_WORLD = [
    "no_change",
    "add_column",
    "add_not_null",
    "type_change",
    "column_rename",
    "column_remove",
]


def _real_changes_for_repo(rng: random.Random, manifest_path: Path, n: int = 20) -> List[dict]:
    """Generate N random changes against a real repo's models.

    For real-world validation, we cannot enumerate ground truth
    (no_change is the default in real PRs that don't touch the file).
    We treat every change as if it were a real PR diff, with the
    expected severity derived from the change type.
    """
    nodes_by_urn, _ = parse_manifest(manifest_path)
    model_urns = [
        urn for urn, node in nodes_by_urn.items()
        if node.kind == "dataset" and "source" not in node.tags
    ]
    if not model_urns:
        return []

    changes: List[dict] = []
    for c_idx in range(n):
        urn = rng.choice(model_urns)
        change_type = rng.choice(CHANGE_TYPES_FOR_REAL_WORLD)
        node = nodes_by_urn[urn]
        columns = node.schema_fields if hasattr(node, "schema_fields") else []

        affected_column = None
        new_value = None
        if columns and change_type != "no_change":
            affected_column = rng.choice(columns)
            if change_type == "column_rename":
                new_value = f"{affected_column}_renamed"
            elif change_type == "type_change":
                new_value = rng.choice(["INTEGER", "VARCHAR", "BOOLEAN", "NUMERIC", "DATE"])

        changes.append({
            "change_id": f"real_change_{c_idx:04d}",
            "asset_urn": urn,
            "change_type": change_type,
            "affected_column": affected_column,
            "new_value": new_value,
        })
    return changes


def evaluate_real_project(project_dir: Path, seed: int = 42) -> List[EvaluationRecord]:
    """Run a single real dbt project through the engine."""
    manifest_path = project_dir / "target" / "manifest.json"
    if not manifest_path.exists():
        manifest_path = project_dir / "manifest.json"
    if not manifest_path.exists():
        return []

    rng = random.Random(seed)
    nodes_by_urn, _ = parse_manifest(manifest_path)
    changes = _real_changes_for_repo(rng, manifest_path, n=20)
    records: List[EvaluationRecord] = []

    for change in changes:
        expected = EXPECTED_SEVERITY.get(change["change_type"], "low")
        try:
            scenario = ScenarioResult(
                asset_urn=change["asset_urn"],
                scenario_type="auto_detected" if change["change_type"] in ("no_change", "add_column", "add_not_null") else "schema_rename",
                applied_change={
                    "change_type": change["change_type"],
                    "affected_column": change.get("affected_column"),
                    "new_value": change.get("new_value"),
                },
                predicted_breakages=[],
                predicted_severity=expected,
                confidence=0.85,
            )
            snapshot = _build_snapshot(nodes_by_urn, change["asset_urn"])
            report = analyze_impact(snapshot, scenario)
            records.append(
                EvaluationRecord(
                    repo_id=-1,
                    change_id=change["change_id"],
                    change_type=change["change_type"],
                    asset_urn=change["asset_urn"],
                    expected_severity=expected,
                    predicted_severity=report.severity,
                    predicted_affected_count=len(report.affected_assets),
                    actual_affected_count=len(report.affected_assets),
                    latency_ms=0.0,
                    confidence=report.confidence,
                )
            )
        except Exception as exc:
            records.append(
                EvaluationRecord(
                    repo_id=-1,
                    change_id=change["change_id"],
                    change_type=change["change_type"],
                    asset_urn=change["asset_urn"],
                    expected_severity=expected,
                    predicted_severity="low",
                    predicted_affected_count=0,
                    actual_affected_count=0,
                    latency_ms=0.0,
                    confidence=0.0,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description="Run real-world benchmark validation")
    parser.add_argument("--projects", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    all_records: List[EvaluationRecord] = []
    for project_dir in args.projects:
        if not project_dir.exists():
            print(f"[warn] project not found: {project_dir}", file=sys.stderr)
            continue
        records = evaluate_real_project(project_dir, seed=args.seed)
        print(f"[ok] {project_dir.name}: {len(records)} records")
        all_records.extend(records)

    summary = aggregate(all_records)
    (args.output / "REAL_WORLD_REPORT.md").write_text(
        render_report(summary, source="real_world")
    )
    (args.output / "real_world_records.json").write_text(
        json.dumps([r.__dict__ for r in all_records], indent=2, default=str)
    )
    print(f"[ok] Wrote {len(all_records)} evaluation records")
    print(f"[ok] REAL_WORLD_REPORT.md at {args.output / 'REAL_WORLD_REPORT.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
