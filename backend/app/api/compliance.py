"""SOC 2 Compliance Center API Endpoints."""

from fastapi import APIRouter
from app.connectors.datahub.mock_store import MOCK_ASSETS
from app.services.graph_builder import build_snapshot
from app.engine.compliance import compliance_engine
from app.models.compliance import ComplianceReport

router = APIRouter(prefix="/compliance", tags=["Compliance"])


@router.get("/report", response_model=ComplianceReport)
async def get_compliance_report():
    """Run an audit across all catalog assets and return the live SOC 2 compliance report."""
    snapshot = build_snapshot(list(MOCK_ASSETS.keys()))
    return compliance_engine.evaluate_compliance(snapshot)
