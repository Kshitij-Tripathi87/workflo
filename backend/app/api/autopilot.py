"""Autopilot API — manual triggering + status inspection.

POST /autopilot/trigger   Run a single Autopilot task synchronously
                          and return the full task result + reasoning steps.
GET  /autopilot/status    Return autopilot health and recent task log.
GET  /autopilot/assets    List asset URNs the autopilot has observed.
"""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.auth import User
from app.middleware.auth import get_current_user, require_role
from app.models.autopilot import AutopilotStatus, AutopilotTask
from app.services.autopilot import get_autopilot

router = APIRouter(prefix="/autopilot", tags=["autopilot"])


class TriggerRequest(BaseModel):
    """Manual trigger for the Autopilot agent."""

    asset_urn: str
    connector: str = "datahub"
    change_type: str = "auto_detected"
    description: Optional[str] = None
    change: dict = Field(default_factory=dict)


class TriggerResponse(BaseModel):
    task: AutopilotTask


@router.post("/trigger", response_model=TriggerResponse)
async def trigger_autopilot(
    request: TriggerRequest,
    user: User = Depends(require_role("analyst")),
):
    """Run one Autopilot task synchronously and return the result."""
    autopilot = get_autopilot()
    change = request.change or {}
    if "change_type" not in change:
        change["change_type"] = request.change_type

    task = AutopilotTask(
        trigger_type="manual",
        asset_urn=request.asset_urn,
        connector=request.connector,
        change=change,
        description=request.description or f"Manual trigger for {request.asset_urn}",
    )
    result = await autopilot.execute_task(task)
    return {"task": result}


@router.get("/status", response_model=AutopilotStatus)
async def autopilot_status(
    user: User = Depends(get_current_user),
):
    """Return the Autopilot's runtime health."""
    return get_autopilot().status()


@router.get("/assets")
async def autopilot_assets(
    user: User = Depends(get_current_user),
):
    """List asset URNs the Autopilot has registered."""
    return {"asset_urns": get_autopilot().context_store.list_registered_assets()}
