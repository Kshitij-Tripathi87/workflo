"""Tests for the policy evaluation engine."""
import pytest
from app.engine.policy import (
    Policy,
    evaluate_policies,
    combine_verdict,
    policies_from_dicts,
)


def test_no_policies_means_pass():
    """No policies → empty results → verdict pass."""
    results = evaluate_policies(
        policies=[],
        severity=99,
        blast_radius=100,
        has_owner=False,
    )
    assert results == []
    assert combine_verdict(results) == "pass"


def test_severity_threshold_blocks():
    """A policy that limits severity blocks when exceeded."""
    policies = [Policy(name="BlockHighRisk", max_severity=50, action="block")]
    results = evaluate_policies(
        policies=policies, severity=80, blast_radius=0, has_owner=True
    )
    assert len(results) == 1
    assert results[0].verdict == "block"
    assert "severity" in results[0].reason
    assert combine_verdict(results) == "block"


def test_blast_radius_threshold_warns():
    """A policy that warns on large blast radius."""
    policies = [Policy(name="WarnBigBlast", max_blast_radius=5, action="warn")]
    results = evaluate_policies(
        policies=policies, severity=20, blast_radius=12, has_owner=True
    )
    assert len(results) == 1
    assert results[0].verdict == "warn"
    assert "blast radius" in results[0].reason
    assert combine_verdict(results) == "warn"


def test_owner_required_violation():
    """require_owner=True fires when asset has no owner."""
    policies = [Policy(name="RequireOwner", require_owner=True, action="block")]
    results = evaluate_policies(
        policies=policies, severity=10, blast_radius=0, has_owner=False
    )
    assert len(results) == 1
    assert "owner" in results[0].reason


def test_owner_satisfied_no_violation():
    """require_owner passes when asset has an owner."""
    policies = [Policy(name="RequireOwner", require_owner=True, action="block")]
    results = evaluate_policies(
        policies=policies, severity=10, blast_radius=0, has_owner=True
    )
    assert results == []


def test_block_dominates_warn():
    """When multiple policies fire, block wins over warn."""
    policies = [
        Policy(name="A", max_blast_radius=1, action="warn"),
        Policy(name="B", max_severity=10, action="block"),
    ]
    results = evaluate_policies(
        policies=policies, severity=80, blast_radius=5, has_owner=True
    )
    assert len(results) == 2
    assert combine_verdict(results) == "block"


def test_pass_when_all_satisfied():
    """No violations when all policy thresholds are satisfied."""
    policies = [
        Policy(name="A", max_severity=80, max_blast_radius=10, action="block"),
    ]
    results = evaluate_policies(
        policies=policies, severity=40, blast_radius=3, has_owner=True
    )
    assert results == []
    assert combine_verdict(results) == "pass"


def test_policies_from_dicts_skips_invalid():
    """Loader skips malformed policies silently."""
    policies = policies_from_dicts(
        [
            {"name": "Valid", "max_severity": 50, "action": "block"},
            {"not_a_real_field": "junk"},
            {"name": "AlsoValid", "max_blast_radius": 5},
        ]
    )
    assert len(policies) == 2
    assert policies[0].name == "Valid"
    assert policies[1].name == "AlsoValid"


def test_policies_from_dicts_handles_none():
    """None input returns empty list."""
    assert policies_from_dicts(None) == []
