"""Run submission and status endpoints — frozen contract (docs/api_contract.md v1).

POST /v1/runs  : accept a RunRequest, queue it, return RunStatus(status=queued).
                 Actual execution happens in a background task (in-process
                 SandboxExecutor — "single-process execution only" per the
                 contract; Redis/Celery is the deferred production path).
GET  /v1/runs/{run_id} : poll RunStatus. completed -> receipt present (test
                 outcomes live in the receipt); failed -> error present and
                 receipt absent (infrastructure crash, not test failure).

Legacy endpoints (complete/logs/cancel/list) are kept for the worker
streamer's queue-mode callbacks and the dashboard; they are NOT part of
the frozen v1 surface and will be removed in v2.
"""

import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from workflo_schema import RunStatus as LegacyRunStatusEnum
from workflo_schema.api import RunRequest, RunStatus

from app.db import database as db_module
from app.db.database import get_db
from app.db.models import ApiKey, TestRun
from app.services.run_service import RunService
from app.core.security import require_api_key

router = APIRouter(prefix="/runs", tags=["runs"])


class CreateRunResponse(BaseModel):
    run_id: str
    status: LegacyRunStatusEnum = LegacyRunStatusEnum.QUEUED


class RunStatusResponse(BaseModel):
    run_id: str
    goal: str
    status: LegacyRunStatusEnum
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    summary: Optional[dict] = None
    logs: Optional[str] = None


class CompleteRunRequest(BaseModel):
    status: str = "completed"
    error: Optional[str] = None
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    deselected: int = 0
    positive_controls_passed: int = 0
    duration_seconds: float = 0.0


async def _execute_run(run_id: str, request: RunRequest) -> None:
    """Background task: run the sandbox executor and persist the outcome.

    Uses a FRESH DB session (the request's session is closed by then).
    On success the signed receipt is stored; on any exception the run is
    marked failed with the error message — and NO receipt. The contract's
    status semantics are strict here:
        completed + receipt   = sandbox ran; outcomes live in the receipt
        failed + error        = infrastructure crash; no receipt produced
    A run whose sandbox ran but had failing tests is COMPLETED with the
    receipt — test failures are NOT infrastructure failures.
    """
    try:
        spec = request.to_sandbox_spec()
        from workflo_executor import SandboxExecutor

        executor = SandboxExecutor()
        # SandboxExecutor.run is blocking (docker/git subprocesses); run it
        # off the event loop so the API stays responsive while sandboxes run.
        result = await asyncio.to_thread(executor.run, spec)

        async with db_module.async_session_factory() as db:
            service = RunService(db)
            await service.complete_run(run_id, {
                "status": "completed",
                # RunStatus.receipt is a dict; to_json() returns a string.
                "receipt": json.loads(result.to_json()),
            })
    except Exception as e:
        async with db_module.async_session_factory() as db:
            service = RunService(db)
            await service.fail_run(run_id, f"{type(e).__name__}: {e}")


@router.post("", response_model=RunStatus, status_code=200)
async def create_run(
    request: RunRequest,
    api_key: ApiKey = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Queue a new run. Returns the initial RunStatus (status: queued).

    Validation failures (e.g. `web` probe group without start_command/port)
    surface as 400 via RunRequest.to_sandbox_spec() — the same fail-fast
    pre-container check the CLI performs.
    """
    try:
        spec = request.to_sandbox_spec()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    service = RunService(db)
    # enqueue=False: the frozen contract executes in-process in the
    # background task below; the legacy queue path is not used.
    run = await service.create_run(api_key.project_id, spec.model_dump(), enqueue=False)
    asyncio.create_task(_execute_run(run.id, request))
    return RunStatus(run_id=run.id, status="queued", created_at=run.started_at)


@router.get("/{run_id}", response_model=RunStatus)
async def get_run(run_id: str, db: AsyncSession = Depends(get_db)):
    """Poll for the latest status of a run.

    Returns RunStatus per the frozen contract:
      - completed: receipt is the full signed receipt (test outcomes inside)
      - failed:    error message, receipt is null (infra crash)
      - queued/running: neither field
    """
    service = RunService(db)
    run = await service.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    if run.status == "completed":
        receipt = (run.summary_json or {}).get("receipt")
        return RunStatus(
            run_id=run.id,
            status="completed",
            created_at=run.started_at,
            receipt=receipt,
            error=None,
        )
    if run.status == "failed":
        return RunStatus(
            run_id=run.id,
            status="failed",
            created_at=run.started_at,
            receipt=None,
            error=(run.summary_json or {}).get("error") or "run failed",
        )
    return RunStatus(
        run_id=run.id,
        status=run.status if run.status in ("queued", "running") else "failed",
        created_at=run.started_at,
        receipt=None,
        error=None,
    )


# --------------------------------------------------------------------
# Legacy endpoints (NOT in the frozen v1 contract) — kept for the worker
# streamer's queue-mode callbacks and the dashboard. Will be removed in v2.
# --------------------------------------------------------------------


@router.get("", response_model=list[CreateRunResponse])
async def list_runs(db: AsyncSession = Depends(get_db), limit: int = 20, api_key: ApiKey = Depends(require_api_key)):
    service = RunService(db)
    runs = await service.list_runs(project_id=api_key.project_id, limit=limit)
    return [CreateRunResponse(run_id=r.id, status=LegacyRunStatusEnum(r.status)) for r in runs]


@router.get("/{run_id}/legacy", response_model=RunStatusResponse)
async def get_run_legacy(run_id: str, db: AsyncSession = Depends(get_db)):
    """Legacy status view (dashboard shape) — not part of frozen v1."""
    service = RunService(db)
    run = await service.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return RunStatusResponse(
        run_id=run.id,
        goal=run.goal,
        status=LegacyRunStatusEnum(run.status),
        started_at=run.started_at.isoformat() if run.started_at else None,
        finished_at=run.finished_at.isoformat() if run.finished_at else None,
        summary=run.summary_json or None,
        logs=run.logs or None,
    )


@router.post("/{run_id}/complete")
async def complete_run(run_id: str, req: CompleteRunRequest, db: AsyncSession = Depends(get_db)):
    service = RunService(db)
    summary = req.model_dump()
    if req.error:
        await service.fail_run(run_id, req.error)
    else:
        await service.complete_run(run_id, summary)
    return {"run_id": run_id, "status": "completed"}


@router.post("/{run_id}/logs")
async def append_logs(run_id: str, log_line: str = "", db: AsyncSession = Depends(get_db)):
    service = RunService(db)
    await service.append_logs(run_id, log_line)
    return {"run_id": run_id, "ack": True}


@router.post("/{run_id}/cancel")
async def cancel_run(run_id: str, db: AsyncSession = Depends(get_db)):
    service = RunService(db)
    await service.cancel_run(run_id)
    return {"run_id": run_id, "status": "cancelled"}
