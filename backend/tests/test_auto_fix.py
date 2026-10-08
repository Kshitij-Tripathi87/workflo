"""Smoke test for the auto-fix artifact generator.

Verifies that the cherry #1 feature — auto-fix SQL patches generated
by `artifact_generator.py` — produces realistic output for the
common schema change scenarios.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.models.recommendation import Recommendation  # noqa: E402
from app.services.artifact_generator import generate_artifact  # noqa: E402


def _recommendation(action_type: str = "patch_sql", confidence: float = 0.85) -> Recommendation:
    return Recommendation(
        impact_id="test",
        action_type=action_type,
        title="Test",
        rationale="test",
        confidence=confidence,
        risk="low",
    )


def test_drop_column_artifact_mentions_removed_column() -> None:
    """Removing a column generates a compat-view patch referencing the column."""
    artifact = generate_artifact(
        recommendation=_recommendation(),
        scenario_type="schema_remove",
        asset_name="orders",
        removed_column="customer_name",
    )
    assert artifact.artifact_type == "sql"
    assert artifact.body
    assert "customer_name" in artifact.body
    assert "VIEW" in artifact.body.upper() or "view" in artifact.body


def test_rename_column_artifact_uses_old_and_new_names() -> None:
    """Renaming a column generates an ALTER TABLE with both names."""
    artifact = generate_artifact(
        recommendation=_recommendation(),
        scenario_type="schema_rename",
        asset_name="customer_ltv",
        old_name="clv_score",
        new_name="lifetime_value",
    )
    assert artifact.artifact_type == "sql"
    assert artifact.body
    assert "clv_score" in artifact.body
    assert "lifetime_value" in artifact.body
    assert "RENAME COLUMN" in artifact.body.upper()


def test_type_change_artifact_returns_a_body() -> None:
    """Type change generates some patch (template may be generic)."""
    artifact = generate_artifact(
        recommendation=_recommendation(),
        scenario_type="type_change",
        asset_name="orders",
    )
    assert artifact.body
    assert artifact.artifact_type in {"sql", "dbt", "dag", "markdown"}


def test_example_artifacts_exist() -> None:
    """The example auto-fix files exist on disk for judges to inspect."""
    artifacts_dir = REPO_ROOT / "examples" / "sample_artifacts"
    expected = [
        "auto_fix_column_remove.sql",
        "auto_fix_column_rename.sql",
        "auto_fix_type_change.sql",
    ]
    for name in expected:
        path = artifacts_dir / name
        assert path.exists(), f"Missing example artifact: {path}"
        content = path.read_text()
        assert "AUTO-FIX EXAMPLE" in content
        assert "Cortex Autopilot" in content
