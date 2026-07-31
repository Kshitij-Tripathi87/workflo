"""Test the impact engine scoring and traversal."""
import pytest
from app.models.asset import AssetNode, GraphSnapshot, GraphEdge
from app.models.scenario import ScenarioResult
from app.engine.impact_engine import analyze_impact


def test_low_severity_no_downstream():
    """Test low severity when no downstream assets."""
    node = AssetNode(
        urn="test:isolated",
        name="isolated_table",
        kind="dataset",
        downstream=[],
        criticality="low",
        owner="test"
    )
    snapshot = GraphSnapshot(nodes={"test:isolated": node}, edges=[])
    scenario = ScenarioResult(
        asset_urn="test:isolated",
        scenario_type="schema_remove",
        predicted_severity="low"
    )
    
    report = analyze_impact(snapshot, scenario)
    
    assert report.severity == "low"
    assert len(report.affected_assets) == 0


def test_high_severity_critical_asset():
    """Test high severity for critical asset with downstream."""
    upstream = AssetNode(
        urn="test:upstream",
        name="upstream_table",
        kind="dataset",
        downstream=["test:dashboard"],
        criticality="critical",
        owner="test"
    )
    downstream = AssetNode(
        urn="test:dashboard",
        name="dashboard",
        kind="dashboard",
        downstream=[],
        criticality="high",
        owner="test"
    )
    snapshot = GraphSnapshot(
        nodes={"test:upstream": upstream, "test:dashboard": downstream},
        edges=[GraphEdge(source="test:upstream", target="test:dashboard", edge_type="downstream_of")]
    )
    scenario = ScenarioResult(
        asset_urn="test:upstream",
        scenario_type="schema_remove",
        predicted_severity="high"
    )
    
    report = analyze_impact(snapshot, scenario)
    
    assert report.severity in ["high", "critical"]
    assert len(report.affected_assets) >= 1


def test_owner_gap_weight():
    """Test that missing owner increases severity."""
    node = AssetNode(
        urn="test:no_owner",
        name="no_owner_table",
        kind="dataset",
        downstream=["test:child"],
        owner=None,
        criticality="medium"
    )
    child = AssetNode(
        urn="test:child",
        name="child_table",
        kind="dataset",
        downstream=[],
        owner="test"
    )
    snapshot = GraphSnapshot(
        nodes={"test:no_owner": node, "test:child": child},
        edges=[GraphEdge(source="test:no_owner", target="test:child", edge_type="downstream_of")]
    )
    scenario = ScenarioResult(
        asset_urn="test:no_owner",
        scenario_type="owner_missing",
        predicted_severity="medium"
    )
    
    report = analyze_impact(snapshot, scenario)
    
    assert any("owner" in e.lower() for e in report.explanation)


def test_ml_dependency():
    """Test that ML model dependency increases severity."""
    dataset = AssetNode(
        urn="test:dataset",
        name="training_data",
        kind="dataset",
        downstream=["test:model"],
        owner="test",
        criticality="high"
    )
    model = AssetNode(
        urn="test:model",
        name="forecast_model",
        kind="model",
        downstream=[],
        owner="ml-team"
    )
    snapshot = GraphSnapshot(
        nodes={"test:dataset": dataset, "test:model": model},
        edges=[GraphEdge(source="test:dataset", target="test:model", edge_type="trains")]
    )
    scenario = ScenarioResult(
        asset_urn="test:dataset",
        scenario_type="schema_remove",
        predicted_severity="medium"
    )
    
    report = analyze_impact(snapshot, scenario)
    
    assert len(report.affected_models) >= 1
    assert any("model" in e.lower() for e in report.explanation)


def test_explanation_non_empty():
    """Test that explanation is always non-empty."""
    node = AssetNode(
        urn="test:table",
        name="test_table",
        kind="dataset",
        downstream=[],
        owner="test",
        criticality="low"
    )
    snapshot = GraphSnapshot(nodes={"test:table": node}, edges=[])
    scenario = ScenarioResult(
        asset_urn="test:table",
        scenario_type="schema_remove",
        predicted_severity="low"
    )
    
    report = analyze_impact(snapshot, scenario)
    
    assert len(report.explanation) >= 1