"""Test the writeback service."""
import pytest
import os
from pathlib import Path
from app.models.impact import ImpactReport
from app.models.recommendation import Recommendation
from app.models.artifact import ArtifactDraft
from app.services.writeback_service import WritebackService


@pytest.fixture
def temp_writeback(tmp_path):
    """Create a temporary writeback service."""
    path = tmp_path / "test_writeback.jsonl"
    service = WritebackService(str(path))
    yield service, path
    # Cleanup
    if path.exists():
        path.unlink()


def test_record_resolution(temp_writeback):
    """Test recording a resolution."""
    service, path = temp_writeback
    
    impact = ImpactReport(
        asset_urn="test:table",
        affected_assets=["test:downstream"],
        severity="high",
        reason="Test impact",
        explanation=["Test explanation"]
    )
    rec = Recommendation(
        impact_id=impact.impact_id,
        action_type="patch_sql",
        title="Test fix",
        rationale="Test rationale"
    )
    artifact = ArtifactDraft(
        recommendation_id=rec.recommendation_id,
        artifact_type="sql",
        title="Test SQL",
        body="-- Test SQL"
    )
    
    record = service.record_resolution(
        asset_urn="test:table",
        impact_report=impact,
        recommendation=rec,
        artifact=artifact
    )
    
    assert record.record_id is not None
    assert record.asset_urn == "test:table"
    assert record.status == "triaged"
    assert record.linked_artifact == artifact.artifact_id
    assert path.exists()


def test_get_resolutions(temp_writeback):
    """Test getting resolutions for an asset."""
    service, path = temp_writeback
    
    impact = ImpactReport(
        asset_urn="test:table",
        severity="low",
        reason="Test",
        explanation=[]
    )
    rec = Recommendation(
        impact_id=impact.impact_id,
        action_type="patch_sql",
        title="Test",
        rationale="Test"
    )
    
    service.record_resolution(
        asset_urn="test:table",
        impact_report=impact,
        recommendation=rec
    )
    
    records = service.get_resolutions("test:table")
    
    assert len(records) >= 1
    assert records[0].asset_urn == "test:table"


def test_get_record(temp_writeback):
    """Test getting a specific record by ID."""
    service, path = temp_writeback
    
    impact = ImpactReport(
        asset_urn="test:table",
        severity="low",
        reason="Test",
        explanation=[]
    )
    rec = Recommendation(
        impact_id=impact.impact_id,
        action_type="patch_sql",
        title="Test",
        rationale="Test"
    )
    
    record = service.record_resolution(
        asset_urn="test:table",
        impact_report=impact,
        recommendation=rec
    )
    
    retrieved = service.get_record(record.record_id)
    
    assert retrieved is not None
    assert retrieved.record_id == record.record_id


def test_update_status(temp_writeback):
    """Test updating a record's status."""
    service, path = temp_writeback
    
    impact = ImpactReport(
        asset_urn="test:table",
        severity="low",
        reason="Test",
        explanation=[]
    )
    rec = Recommendation(
        impact_id=impact.impact_id,
        action_type="patch_sql",
        title="Test",
        rationale="Test"
    )
    
    record = service.record_resolution(
        asset_urn="test:table",
        impact_report=impact,
        recommendation=rec
    )
    
    updated = service.update_status(record.record_id, "fixed")
    
    assert updated is not None
    assert updated.status == "fixed"