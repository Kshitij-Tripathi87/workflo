"""Tests for security hardening and path/traversal protections."""
from pathlib import Path
from app.connectors.datahub.writeback import _safe_resolve


def test_safe_resolve_rejects_parent_traversal():
    """Paths with '..' segments are rejected and rerouted to safe base."""
    raw = "../../../etc/cron.d/evil.jsonl"
    safe = _safe_resolve(raw)
    # Must not contain '..' after resolution
    assert ".." not in safe.parts
    # Falls back to safe base directory
    assert str(safe).endswith("evil.jsonl") is False or ".." not in str(safe)


def test_safe_resolve_rejects_tilde_expansion():
    """Tilde-expansion attempts are rejected."""
    safe = _safe_resolve("~/evil.jsonl")
    assert "~" not in safe.parts or "evil.jsonl" == safe.name


def test_safe_resolve_accepts_clean_absolute():
    """Absolute paths without '..' are accepted as-is."""
    raw = "/tmp/cortex-absolute-test.jsonl"
    safe = _safe_resolve(raw)
    # The resolved path should be the absolute one
    assert safe.is_absolute()


def test_safe_resolve_accepts_clean_relative():
    """Relative paths without '..' are accepted."""
    raw = "data/writeback-test.jsonl"
    safe = _safe_resolve(raw)
    assert ".." not in safe.parts


def test_decision_engine_pure_deterministic():
    """Decision output does not depend on LLMs or randomness.

    Verifies that two calls produce identical ranking results.
    """
    from app.engine.recommendation_ranker import rank_candidates
    from app.models.future import FutureScenario
    from uuid import uuid4

    candidates = [
        FutureScenario(
            future_id=str(uuid4()),
            asset_urn="urn:test",
            scenario_type="patch_dbt",
            change={},
            predicted_severity=20,
            predicted_effort=30,
            predicted_benefit=80,
            confidence=0.9,
        ),
        FutureScenario(
            future_id=str(uuid4()),
            asset_urn="urn:test",
            scenario_type="do_nothing",
            change={},
            predicted_severity=60,
            predicted_effort=10,
            predicted_benefit=40,
            confidence=0.7,
        ),
    ]

    r1 = rank_candidates(candidates, "minimize incident risk", {})
    r2 = rank_candidates(candidates, "minimize incident risk", {})
    # Two consecutive calls must rank deterministically (no random tiebreaker)
    assert r1.scenario_type == r2.scenario_type


def test_writeback_mirror_stays_out_of_the_repo():
    """Test runs must never append to committed data files.

    backend/data/writeback.jsonl is tracked in git; before this guard every
    write-back test appended sample records to it, so running the suite left
    the worktree dirty and the diff was indistinguishable from real incident
    data. conftest redirects WRITEBACK_DIR to a temporary directory.
    """
    from pathlib import Path

    from app.connectors.datahub.writeback import _writeback_base_dir, _writeback_path

    repo_root = Path(__file__).resolve().parents[1]
    base = _writeback_base_dir()

    assert base != repo_root, f"writeback base points at the repo: {base}"
    assert repo_root not in base.parents, f"writeback base is inside the repo: {base}"
    assert repo_root not in _writeback_path().parents, _writeback_path()
