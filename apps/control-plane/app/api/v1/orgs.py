"""Organization data export + deletion (SOC 2 CC6.7; GDPR/CCPA right-to-
access and right-to-erasure readiness).

Both endpoints require a Bearer token (user identity, not an API key) and
operate ONLY on the caller's own organization — a user cannot export or
erase another tenant's data.

Deletion is hard-delete via the ORM cascade (org → projects → runs,
results, artifacts, keys, devices), then records the erasure itself in the
audit trail. The transparency log and its Merkle history are NOT touched:
receipts already logged stay provable even after the tenant that produced
them is gone (that's what the log is for — the fingerprints carry no
tenant data).
"""

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_bearer_token
from app.db.database import get_db
from app.db.models import Organization, Project, TestRun
from app.services.audit_service import record_event

router = APIRouter(prefix="/orgs", tags=["orgs"])


async def _own_org(authorization: Optional[str], db: AsyncSession) -> tuple:
    token, user = await verify_bearer_token(authorization, db)
    if not user.org_id:
        raise HTTPException(status_code=404, detail="No organization for this account")
    org = await db.get(Organization, user.org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return token, user, org


@router.get("/{org_id}/export")
async def export_org(
    org_id: str,
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """Export the caller's organization data as one JSON document.

    Credential material exports only as its stored (hashed, and when
    envelope encryption is on, sealed) form — plaintext keys/passwords
    never leave through this API.
    """
    _token, user, org = await _own_org(authorization, db)
    if org.id != org_id:
        raise HTTPException(status_code=404, detail="Organization not found")

    projects = (
        (await db.execute(select(Project).where(Project.org_id == org.id)))
        .scalars().all()
    )
    project_ids = [p.id for p in projects]
    runs = []
    for pid in project_ids:
        rows = (
            (await db.execute(select(TestRun).where(TestRun.project_id == pid)))
            .scalars().all()
        )
        runs.extend(rows)

    await record_event(
        action="org.export",
        outcome="success",
        actor_type="user",
        actor_id=user.id,
        organization_id=org.id,
        resource_type="organization",
        resource_id=org.id,
    )

    return {
        "organization": {
            "id": org.id,
            "name": org.name,
            "plan_tier": org.plan_tier,
            "created_at": org.created_at.isoformat() if org.created_at else None,
        },
        "projects": [
            {"id": p.id, "name": p.name, "config": p.config_json} for p in projects
        ],
        "runs": [
            {
                "id": r.id,
                "project_id": r.project_id,
                "goal": r.goal,
                "status": r.status,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "summary": r.summary_json,
            }
            for r in runs
        ],
    }


@router.delete("/{org_id}")
async def delete_org(
    org_id: str,
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """Hard-delete the caller's organization and everything under it.

    Cascades: projects → (runs, results, artifacts, api_keys, devices).
    Requires the caller to belong to the org. The erasure is audited with
    counts, so the trail shows WHAT was deleted without keeping the data.
    """
    _token, user, org = await _own_org(authorization, db)
    if org.id != org_id:
        raise HTTPException(status_code=404, detail="Organization not found")

    projects = (
        (await db.execute(select(Project).where(Project.org_id == org.id)))
        .scalars().all()
    )
    project_count = len(projects)
    run_count = 0
    for project in projects:
        runs = (
            (await db.execute(select(TestRun).where(TestRun.project_id == project.id)))
            .scalars().all()
        )
        run_count += len(runs)

    # The User row keeps org_id=NULL after this (ON DELETE CASCADE is set
    # on the FK; detach explicitly so the account survives as orgless).
    user.org_id = None
    user.project_id = None
    await db.delete(org)
    await db.commit()

    await record_event(
        action="org.delete",
        outcome="success",
        actor_type="user",
        actor_id=user.id,
        organization_id=org_id,
        resource_type="organization",
        resource_id=org_id,
        detail={"projects_deleted": project_count, "runs_deleted": run_count},
    )
    return {
        "id": org_id,
        "deleted": True,
        "projects_deleted": project_count,
        "runs_deleted": run_count,
    }
