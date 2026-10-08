"""Test the artifact generator."""
import pytest
from app.models.recommendation import Recommendation
from app.services.artifact_generator import generate_artifact


def test_sql_artifact_for_patch_sql():
    """Test SQL artifact generated for patch_sql action."""
    rec = Recommendation(
        impact_id="test:impact",
        action_type="patch_sql",
        title="Patch SQL",
        rationale="Update queries"
    )
    
    artifact = generate_artifact(rec, "schema_remove", "orders")
    
    assert artifact.artifact_type == "sql"
    assert "orders" in artifact.body


def test_dbt_artifact_for_patch_dbt():
    """Test dbt artifact generated for patch_dbt action."""
    rec = Recommendation(
        impact_id="test:impact",
        action_type="patch_dbt",
        title="Patch dbt",
        rationale="Update model"
    )
    
    artifact = generate_artifact(rec, "schema_rename", "orders_summary")
    
    assert artifact.artifact_type == "dbt"
    assert "dbt" in artifact.body.lower() or "model" in artifact.body.lower()


def test_dag_artifact_for_pipeline_failure():
    """Test DAG artifact for pipeline failure."""
    rec = Recommendation(
        impact_id="test:impact",
        action_type="patch_dag",
        title="Patch DAG",
        rationale="Fix pipeline"
    )
    
    artifact = generate_artifact(rec, "pipeline_failure", "etl_sync")
    
    assert artifact.artifact_type == "dag"
    assert "airflow" in artifact.body.lower() or "dag" in artifact.body.lower()


def test_markdown_artifact_for_escalate():
    """Test markdown artifact for escalation."""
    rec = Recommendation(
        impact_id="test:impact",
        action_type="escalate",
        title="Escalate",
        rationale="Human review needed"
    )
    
    artifact = generate_artifact(rec, "auto_detected", "unknown_table")
    
    assert artifact.artifact_type == "markdown"


def test_yaml_artifact_for_assign_owner():
    """Test YAML artifact for owner assignment."""
    rec = Recommendation(
        impact_id="test:impact",
        action_type="assign_owner",
        title="Assign Owner",
        rationale="Need stewardship"
    )
    
    artifact = generate_artifact(rec, "owner_missing", "customers")
    
    assert artifact.artifact_type == "yaml"
    assert "owner" in artifact.body.lower() or "ownership" in artifact.body.lower()