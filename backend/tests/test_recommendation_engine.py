"""Test the recommendation engine."""
import pytest
from app.models.impact import ImpactReport
from app.services.recommendation_engine import recommend_action


def test_schema_remove_recommendation():
    """Test recommendation for schema_remove scenario."""
    impact = ImpactReport(
        asset_urn="test:table",
        affected_assets=["test:downstream"],
        affected_dashboards=[],
        affected_models=[],
        severity="high",
        explanation=["Downstream assets affected"]
    )
    
    rec = recommend_action(impact, "schema_remove")
    
    assert rec.action_type in ["patch_sql", "create_temp_view"]
    assert rec.rationale != ""


def test_owner_missing_recommendation():
    """Test recommendation for owner_missing scenario."""
    impact = ImpactReport(
        asset_urn="test:table",
        affected_assets=[],
        severity="medium",
        explanation=["No owner assigned"]
    )
    
    rec = recommend_action(impact, "owner_missing")
    
    assert rec.action_type == "assign_owner"
    assert "owner" in rec.rationale.lower()


def test_pipeline_failure_recommendation():
    """Test recommendation for pipeline_failure scenario."""
    impact = ImpactReport(
        asset_urn="test:pipeline",
        affected_assets=["test:downstream"],
        severity="critical",
        explanation=["Pipeline failed"]
    )
    
    rec = recommend_action(impact, "pipeline_failure")
    
    assert rec.action_type in ["patch_dag", "rollback_change"]


def test_critical_severity_escalation():
    """Test that critical severity may trigger escalation fallback."""
    impact = ImpactReport(
        asset_urn="test:critical",
        affected_assets=["a", "b", "c", "d", "e"],
        affected_dashboards=["dash1"],
        affected_models=["model1"],
        severity="critical",
        explanation=["Multiple critical dependencies"]
    )
    
    rec = recommend_action(impact, "schema_remove")
    
    assert rec.risk == "critical"
    assert rec.fallback_action in ["escalate", "patch_dbt"]


def test_confidence_computation():
    """Test that confidence is computed reasonably."""
    impact = ImpactReport(
        asset_urn="test:table",
        affected_assets=[],
        severity="low",
        explanation=[]
    )
    
    rec = recommend_action(impact, "schema_rename")
    
    assert 0.5 <= rec.confidence <= 0.95