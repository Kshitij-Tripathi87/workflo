"""Audit service — writes security-relevant events to the audit_events table.

SOC 2 CC7.2/CC7.3: the control plane must be able to answer "who accessed
what, when, from where" per tenant without trusting application logs.

Design rules:

  - Events are written on a DEDICATED session (not the request's), so an
    audit record survives rollback of the business transaction — a failed
    login must still produce an event.
  - Write failures NEVER break the request path; they are logged to stderr
    with the full event payload (a missing DB row is a monitoring alert,
    not a reason to deny a customer action).
  - detail_json is BOUNDED (values truncated) and must never carry
    secrets: no raw keys, tokens, passwords, or repo contents.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import database
from app.db.models import AuditEvent

# Hard cap on any string value stored in detail_json — keeps the audit row
# small even if a caller passes something pathological (e.g. a log tail).
_MAX_DETAIL_VALUE = 512


def _bound_detail(detail: Optional[dict]) -> dict:
    """Coerce to a JSON-safe dict with bounded string values.

    Never raises: audit bounding must not break the request path.
    """
    if not detail:
        return {}
    out: dict[str, Any] = {}
    for key, value in detail.items():
        try:
            if isinstance(value, str) and len(value) > _MAX_DETAIL_VALUE:
                value = value[: _MAX_DETAIL_VALUE - 3] + "..."
            # Round-trip through JSON to prove serializability; fall back to repr.
            json.dumps(value)
            out[str(key)] = value
        except (TypeError, ValueError):
            out[str(key)] = repr(value)[:_MAX_DETAIL_VALUE]
    return out


async def record_event(
    *,
    action: str,
    outcome: str,
    actor_type: str,
    actor_id: Optional[str] = None,
    organization_id: Optional[str] = None,
    project_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    detail: Optional[dict] = None,
    request_id: Optional[str] = None,
    client_ip: Optional[str] = None,
    db: Optional[AsyncSession] = None,
) -> None:
    """Append one audit event. Best-effort: logs to stderr on failure.

    ``db`` is accepted for testability (caller-owned session); in
    production paths pass None so the event commits independently of the
    request transaction.
    """
    event = AuditEvent(
        action=action,
        outcome=outcome,
        actor_type=actor_type,
        actor_id=actor_id,
        organization_id=organization_id,
        project_id=project_id,
        resource_type=resource_type,
        resource_id=resource_id,
        detail_json=_bound_detail(detail),
        request_id=request_id,
        client_ip=client_ip,
    )

    async def _write(session: AsyncSession) -> None:
        session.add(event)
        await session.commit()

    try:
        if db is not None:
            await _write(db)
        else:
            # Late binding: tests rediect database.async_session_factory per
            # fixture — read it at call time, not import time.
            async with database.async_session_factory() as session:
                await _write(session)
    except Exception as exc:  # noqa: BLE001 — audit must not break requests
        payload = {
            "audit_write_failed": True,
            "error": f"{type(exc).__name__}: {exc}",
            "event": {
                "action": action,
                "outcome": outcome,
                "actor_type": actor_type,
                "actor_id": actor_id,
                "project_id": project_id,
                "resource_type": resource_type,
                "resource_id": resource_id,
            },
        }
        print(json.dumps(payload, sort_keys=True), file=sys.stderr)


async def list_events(
    db: AsyncSession,
    *,
    project_id: Optional[str] = None,
    organization_id: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = 100,
) -> list[AuditEvent]:
    """Read audit events, newest first. Always tenant-scoped by the caller."""
    stmt = select(AuditEvent).order_by(AuditEvent.occurred_at.desc()).limit(min(limit, 1000))
    if project_id:
        stmt = stmt.where(AuditEvent.project_id == project_id)
    if organization_id:
        stmt = stmt.where(AuditEvent.organization_id == organization_id)
    if action:
        stmt = stmt.where(AuditEvent.action == action)
    result = await db.execute(stmt)
    return list(result.scalars())
