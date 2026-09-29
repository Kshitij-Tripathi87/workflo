"""Audit event read API — tenant-scoped (SOC 2 CC7.3).

GET /v1/audit/events : list audit events for the CALLER'S project only.
    Requires the "admin" scope on the API key — audit trails are an
    auditor/admin surface, not a run surface. There is deliberately no
    cross-project or delete path: the trail is read-only and scoped.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_scope
from app.db.database import get_db
from app.db.models import ApiKey
from app.services import audit_service

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditEventResponse(BaseModel):
    id: str
    occurred_at: str
    actor_type: str
    actor_id: Optional[str]
    organization_id: Optional[str]
    project_id: Optional[str]
    action: str
    resource_type: Optional[str]
    resource_id: Optional[str]
    outcome: str
    detail: dict
    request_id: Optional[str]
    client_ip: Optional[str]


@router.get("/events", response_model=list[AuditEventResponse])
async def list_audit_events(
    action: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    api_key: ApiKey = Depends(require_scope("admin")),
    db: AsyncSession = Depends(get_db),
):
    events = await audit_service.list_events(
        db, project_id=api_key.project_id, action=action, limit=limit
    )
    return [
        AuditEventResponse(
            id=e.id,
            occurred_at=e.occurred_at.isoformat() if e.occurred_at else "",
            actor_type=e.actor_type,
            actor_id=e.actor_id,
            organization_id=e.organization_id,
            project_id=e.project_id,
            action=e.action,
            resource_type=e.resource_type,
            resource_id=e.resource_id,
            outcome=e.outcome,
            detail=e.detail_json or {},
            request_id=e.request_id,
            client_ip=e.client_ip,
        )
        for e in events
    ]
