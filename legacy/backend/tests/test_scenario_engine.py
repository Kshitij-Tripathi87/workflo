"""Test the scenario engine with all 5 scenario types."""
import pytest
from app.models.asset import AssetNode, GraphSnapshot
from app.models.scenario import ScenarioRequest
from app.engine.scenario_engine import apply_scenario


def make_snapshot(node: AssetNode) -> GraphSnapshot:
    """Helper to create a snapshot with one node."""
    return GraphSnapshot(nodes={node.urn: node}, edges=[])


def test_schema_remove():
    """Test schema_remove scenario."""
    node = AssetNode(
        urn="test:orders",
        name="orders",
        schema_fields=["id", "name", "total"],
        criticality="high"
    )
    snapshot = make_snapshot(node)
    request = ScenarioRequest(
        asset_urn="test:orders",
        scenario_type="schema_remove",
        change={"removed": ["name"]}
    )
    
    result = apply_scenario(snapshot, request)
    
    assert result.scenario_type == "schema_remove"
    assert len(result.predicted_breakages) >= 1
    assert "name" not in snapshot.nodes["test:orders"].schema_fields


def test_schema_rename():
    """Test schema_rename scenario."""
    node = AssetNode(
        urn="test:orders",
        name="orders",
        schema_fields=["id", "customer_name", "total"],
        criticality="medium"
    )
    snapshot = make_snapshot(node)
    request = ScenarioRequest(
        asset_urn="test:orders",
        scenario_type="schema_rename",
        change={"removed": ["customer_name"], "added": ["name"]}
    )
    
    result = apply_scenario(snapshot, request)
    
    assert result.scenario_type == "schema_rename"
    assert "name" in snapshot.nodes["test:orders"].schema_fields


def test_owner_missing():
    """Test owner_missing scenario."""
    node = AssetNode(
        urn="test:customers",
        name="customers",
        owner="analytics",
        criticality="high"
    )
    snapshot = make_snapshot(node)
    request = ScenarioRequest(
        asset_urn="test:customers",
        scenario_type="owner_missing",
        change={"owner": None}
    )
    
    result = apply_scenario(snapshot, request)
    
    assert result.scenario_type == "owner_missing"
    assert snapshot.nodes["test:customers"].owner is None


def test_pipeline_failure():
    """Test pipeline_failure scenario."""
    node = AssetNode(
        urn="test:pipeline",
        name="etl_sync",
        kind="pipeline",
        status="running",
        criticality="critical"
    )
    snapshot = make_snapshot(node)
    request = ScenarioRequest(
        asset_urn="test:pipeline",
        scenario_type="pipeline_failure",
        change={"status": "failed"}
    )
    
    result = apply_scenario(snapshot, request)
    
    assert result.scenario_type == "pipeline_failure"
    assert snapshot.nodes["test:pipeline"].status == "failed"
    assert result.predicted_severity == "critical"


def test_dataset_deprecation():
    """Test dataset_deprecation scenario."""
    node = AssetNode(
        urn="test:legacy_table",
        name="legacy_table",
        status="active",
        criticality="low"
    )
    snapshot = make_snapshot(node)
    request = ScenarioRequest(
        asset_urn="test:legacy_table",
        scenario_type="dataset_deprecation",
        change={"status": "deprecated"}
    )
    
    result = apply_scenario(snapshot, request)
    
    assert result.scenario_type == "dataset_deprecation"
    assert snapshot.nodes["test:legacy_table"].status == "deprecated"


def test_idempotence():
    """Test that applying same scenario twice gives same result."""
    node = AssetNode(
        urn="test:orders",
        name="orders",
        schema_fields=["id", "name"],
        criticality="medium"
    )
    snapshot = make_snapshot(node)
    request = ScenarioRequest(
        asset_urn="test:orders",
        scenario_type="schema_remove",
        change={"removed": ["name"]}
    )
    
    result1 = apply_scenario(snapshot, request)
    result2 = apply_scenario(snapshot, request)
    
    assert result1.predicted_breakages == result2.predicted_breakages
    assert result1.predicted_severity == result2.predicted_severity