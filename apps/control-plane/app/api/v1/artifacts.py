"""Artifact listing and metadata endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.database import get_db
from app.db.models import Artifact, TestRun, TestResultRecord

router = APIRouter(prefix="/runs", tags=["artifacts"])


@router.get("/{run_id}/artifacts")
async def list_artifacts(run_id: str, db: AsyncSession = Depends(get_db)):
    run = await db.get(TestRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    stmt = select(Artifact).where(Artifact.run_id == run_id)
    result = await db.execute(stmt)
    artifacts = result.scalars()
    return [
        {
            "id": a.id,
            "type": a.type,
            "storage_path": a.storage_path,
            "metadata": a.metadata_json,
        }
        for a in artifacts
    ]


@router.get("/{run_id}/results")
async def get_results(run_id: str, db: AsyncSession = Depends(get_db)):
    run = await db.get(TestRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    # Use explicit SELECT to avoid lazy-loading issues with async SQLAlchemy
    stmt = select(TestResultRecord).where(TestResultRecord.run_id == run_id)
    result = await db.execute(stmt)
    return [
        {
            "nodeid": r.nodeid,
            "status": r.status,
            "duration": r.duration,
            "markers": r.markers,
            "soc2_controls": r.soc2_controls,
            "assertion": r.assertion,
            "error": r.error,
        }
        for r in result.scalars()
    ]


@router.get("/{run_id}/report")
async def get_report_link(run_id: str, db: AsyncSession = Depends(get_db)):
    """Return a link to the SOC2 compliance report for this run."""
    run = await db.get(TestRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    # In production, this returns a presigned S3 URL
    # For now, return a placeholder
    return {
        "run_id": run_id,
        "report_url": f"/reports/{run_id}/soc2.html",
        "format": "html",
        "generated": run.summary_json is not None,
    }
