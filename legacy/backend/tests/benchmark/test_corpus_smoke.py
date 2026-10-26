"""Smoke test for the benchmark pipeline.

Generates a tiny corpus, runs the orchestrator, and asserts that the
engine returns valid results. Used by CI to catch regressions in the
benchmark scaffolding without paying the cost of the full 10,000
evaluation run.

Run with: pytest backend/tests/benchmark/test_corpus_smoke.py
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from .repo_generator import generate_corpus
from .run_benchmark import run_corpus, evaluate_repo
from .metrics import (
    aggregate,
    EvaluationRecord,
    EXPECTED_SEVERITY,
)


@pytest.fixture(scope="module")
def tiny_corpus(tmp_path_factory) -> Path:
    """Generate a 2-repo x 30-change corpus for the smoke test.

    30 changes per repo gives > 95% probability of hitting every
    change type under the weighted distribution, so the smoke test
    exercises all engine paths.
    """
    out = tmp_path_factory.mktemp("tiny_corpus")
    generate_corpus(
        num_repos=2,
        num_changes_per_repo=30,
        seed=42,
        output_dir=out,
    )
    return out


def test_corpus_generation(tiny_corpus: Path) -> None:
    """Generator wrote the expected number of repos and changes."""
    repo_dirs = sorted(p for p in tiny_corpus.iterdir() if p.is_dir())
    assert len(repo_dirs) == 2
    for repo_dir in repo_dirs:
        manifest = json.loads((repo_dir / "manifest.json").read_text())
        changes = json.loads((repo_dir / "changes.json").read_text())
        assert manifest["metadata"]["project_name"]
        assert len(changes) == 30


def test_run_corpus_returns_records(tiny_corpus: Path) -> None:
    """The orchestrator returns one record per change."""
    records = run_corpus(tiny_corpus)
    assert len(records) == 60  # 2 repos * 30 changes


def test_records_have_required_fields(tiny_corpus: Path) -> None:
    """Each record has all fields populated (no None where required)."""
    records = run_corpus(tiny_corpus)
    for rec in records:
        assert rec.repo_id >= 0
        assert rec.change_id
        assert rec.change_type in EXPECTED_SEVERITY
        assert rec.asset_urn
        assert rec.expected_severity in {"low", "medium", "high", "critical"}
        assert rec.predicted_severity in {"low", "medium", "high", "critical"}
        assert rec.latency_ms >= 0.0


def test_aggregate_runs_without_error(tiny_corpus: Path) -> None:
    """aggregate() produces a Summary with populated stats."""
    records = run_corpus(tiny_corpus)
    summary = aggregate(records)
    assert summary.n_total == 60
    assert summary.latency.n == 60
    assert summary.severity.n == 60
    assert summary.latency.p50_ms >= 0.0


def test_engine_handles_no_change(tiny_corpus: Path) -> None:
    """no_change changes should never raise KeyError."""
    repo_dir = next(p for p in tiny_corpus.iterdir() if p.is_dir())
    records = evaluate_repo(repo_dir)
    no_change_records = [r for r in records if r.change_type == "no_change"]
    assert no_change_records
    for rec in no_change_records:
        assert rec.error is None
