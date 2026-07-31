"""Orchestrates the Cortex Benchmark 2026 run.

For each repo in the corpus:
  - Parse manifest.json with the dbt parser
  - For each change in changes.json, build a ScenarioResult, run
    analyze_impact, and capture latency + verdict
  - Aggregate metrics and write REPORT.md

Usage:
    python -m backend.tests.benchmark.run_benchmark \
        --corpus backend/tests/benchmark/corpus \
        --output backend/tests/benchmark/results
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import List

from app.connectors.dbt.parser import parse_manifest
from app.engine.impact_engine import analyze_impact
from app.models.scenario import ScenarioResult
from app.models.impact import ImpactReport

from .metrics import (
    EXPECTED_SEVERITY,
    EvaluationRecord,
    aggregate,
    render_report,
)


SCENARIO_TYPE_FOR_CHANGE = {
    "no_change": "auto_detected",
    "add_column": "auto_detected",
    "add_not_null": "auto_detected",
    "type_change": "schema_rename",
    "column_rename": "schema_rename",
    "column_remove": "schema_remove",
}


def _scenario_for_change(asset_urn: str, change: dict) -> ScenarioResult:
    return ScenarioResult(
        asset_urn=asset_urn,
        scenario_type=SCENARIO_TYPE_FOR_CHANGE.get(
            change["change_type"], "auto_detected"
        ),
        applied_change={
            "change_type": change["change_type"],
            "affected_column": change.get("affected_column"),
            "new_value": change.get("new_value"),
        },
        predicted_breakages=[],
        predicted_severity=EXPECTED_SEVERITY.get(change["change_type"], "low"),
        confidence=0.85,
    )


def evaluate_repo(repo_dir: Path) -> List[EvaluationRecord]:
    """Parse the manifest and run all changes against the engine."""
    manifest_path = repo_dir / "manifest.json"
    changes_path = repo_dir / "changes.json"
    if not manifest_path.exists() or not changes_path.exists():
        return []

    nodes_by_urn, _ = parse_manifest(manifest_path)
    changes = json.loads(changes_path.read_text(encoding="utf-8"))
    records: List[EvaluationRecord] = []

    try:
        repo_id = int(repo_dir.name.split("-")[-1])
    except ValueError:
        repo_id = -1

    for change in changes:
        asset_urn = change["asset_urn"]
        expected_severity = EXPECTED_SEVERITY.get(change["change_type"], "low")
        actual_affected_count = 0
        try:
            actual_affected_count = len(get_all_downstream_simple(nodes_by_urn, asset_urn))
        except Exception:
            actual_affected_count = -1

        try:
            scenario = _scenario_for_change(asset_urn, change)
            start = time.perf_counter()
            report: ImpactReport = analyze_impact(
                _build_snapshot(nodes_by_urn, asset_urn), scenario
            )
            latency_ms = (time.perf_counter() - start) * 1000.0
            records.append(
                EvaluationRecord(
                    repo_id=repo_id,
                    change_id=change["change_id"],
                    change_type=change["change_type"],
                    asset_urn=asset_urn,
                    expected_severity=expected_severity,
                    predicted_severity=report.severity,
                    predicted_affected_count=len(report.affected_assets),
                    actual_affected_count=actual_affected_count,
                    latency_ms=latency_ms,
                    confidence=report.confidence,
                )
            )
        except Exception as exc:
            records.append(
                EvaluationRecord(
                    repo_id=repo_id,
                    change_id=change["change_id"],
                    change_type=change["change_type"],
                    asset_urn=asset_urn,
                    expected_severity=expected_severity,
                    predicted_severity="low",
                    predicted_affected_count=0,
                    actual_affected_count=actual_affected_count,
                    latency_ms=0.0,
                    confidence=0.0,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )

    return records


def get_all_downstream_simple(nodes_by_urn: dict, start_urn: str) -> list[str]:
    """BFS over downstream edges."""
    visited: set[str] = set()
    queue = [start_urn]
    out: list[str] = []
    while queue:
        urn = queue.pop(0)
        if urn in visited:
            continue
        visited.add(urn)
        node = nodes_by_urn.get(urn)
        if not node:
            continue
        for ds in node.downstream:
            if ds not in visited:
                queue.append(ds)
                out.append(ds)
    return out


def _build_snapshot(nodes_by_urn: dict, center_urn: str):
    """Build a minimal GraphSnapshot containing the center plus its neighbors."""
    from app.models.asset import AssetNode, GraphEdge, GraphSnapshot

    active: dict[str, AssetNode] = {}
    edges: list[GraphEdge] = []

    center = nodes_by_urn.get(center_urn)
    if not center:
        return GraphSnapshot(nodes={}, edges=[])

    active[center_urn] = center
    for up in center.upstream:
        n = nodes_by_urn.get(up)
        if n:
            active[up] = n
            edges.append(
                GraphEdge(source=up, target=center_urn, edge_type="upstream_of", confidence=0.95)
            )
    for ds in center.downstream:
        n = nodes_by_urn.get(ds)
        if n:
            active[ds] = n
            edges.append(
                GraphEdge(source=center_urn, target=ds, edge_type="downstream_of", confidence=0.95)
            )

    return GraphSnapshot(nodes=active, edges=edges)


def run_corpus(corpus_dir: Path) -> List[EvaluationRecord]:
    repo_dirs = sorted(p for p in corpus_dir.iterdir() if p.is_dir())
    all_records: List[EvaluationRecord] = []
    for repo_dir in repo_dirs:
        all_records.extend(evaluate_repo(repo_dir))
    return all_records


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Cortex Benchmark")
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", type=str, default="synthetic")
    args = parser.parse_args()

    if not args.corpus.exists():
        print(f"[err] corpus directory not found: {args.corpus}", file=sys.stderr)
        return 1

    records = run_corpus(args.corpus)
    summary = aggregate(records)

    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "records.json").write_text(
        json.dumps([r.__dict__ for r in records], indent=2, default=str)
    )
    (args.output / "REPORT.md").write_text(render_report(summary, source=args.source))

    print(f"[ok] Wrote {len(records)} evaluation records")
    print(f"[ok] REPORT.md at {args.output / 'REPORT.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
