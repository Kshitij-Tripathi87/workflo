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
from app.services.audit_service import record_event
from app.services.run_service import RunService
from app.core.config import settings
from app.core.rate_limit import check_tenant_rate_limit
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


def _extract_receipt_dict(summary_receipt) -> Optional[dict]:
    """Best-effort receipt dict out of the stored summary.

    The executor stores SandboxRunResult.to_json() under summary.receipt,
    whose 'receipt' key holds the SignedReceipt dict; earlier/mock paths
    may store the receipt dict directly. Returns None when neither shape
    holds a SignedReceipt — the caller treats that as "nothing to log".
    """
    if not isinstance(summary_receipt, dict):
        return None
    if "sandbox_id" in summary_receipt and "signature" in summary_receipt:
        return summary_receipt
    inner = summary_receipt.get("receipt")
    if isinstance(inner, dict) and "sandbox_id" in inner:
        return inner
    return None


def _append_receipt_to_transparency_log(receipt_dict: dict, run_id: str) -> None:
    """Append the receipt's canonical fingerprint to the transparency log.

    Best-effort and off the request path by design (a logging outage must
    not fail customer runs), but failures ARE audit-visible.
    """
    if not settings.transparency_log_path:
        return
    try:
        from pathlib import Path as _Path

        from sandbox_isolation.transparency import (
            LocalTransparencyLog,
            receipt_fingerprint,
        )
        from workflo_schema.sandbox import SignedReceipt

        receipt = SignedReceipt(**receipt_dict)
        leaf = receipt_fingerprint(receipt.canonical_payload())
        log = LocalTransparencyLog(_Path(settings.transparency_log_path))
        record = log.append(leaf)
        asyncio.ensure_future(record_event(
            action="transparency.append",
            outcome="success",
            actor_type="system",
            project_id=None,
            resource_type="run",
            resource_id=run_id,
            detail={"tree_size": record.tree_size, "seq": record.seq},
        ))
    except Exception as e:  # noqa: BLE001 — transparency must not fail runs
        asyncio.ensure_future(record_event(
            action="transparency.append",
            outcome="error",
            actor_type="system",
            resource_type="run",
            resource_id=run_id,
            detail={"error": f"{type(e).__name__}: {e}"},
        ))


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
            run = await service.get_run(run_id)
            if run:
                # RLS defense-in-depth: background sessions don't inherit a
                # request's tenant binding — set it from the run itself.
                await db_module.set_tenant_context(db, run.project_id)
            result_json = json.loads(result.to_json())
            await service.complete_run(run_id, {
                "status": "completed",
                # RunStatus.receipt is a dict; to_json() returns a string.
                "receipt": result_json,
            })
            receipt_dict = _extract_receipt_dict(result_json)
            if receipt_dict:
                _append_receipt_to_transparency_log(receipt_dict, run_id)
    except Exception as e:
        async with db_module.async_session_factory() as db:
            service = RunService(db)
            run = await service.get_run(run_id)
            if run:
                await db_module.set_tenant_context(db, run.project_id)
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

    # Per-tenant submission ceiling: one noisy project cannot starve the
    # shared worker capacity (SOC 2 CC6.1 — resource isolation).
    if settings.rate_limit_runs_per_minute > 0:
        allowed, retry_after = check_tenant_rate_limit(api_key.project_id)
        if not allowed:
            await record_event(
                action="run.create",
                outcome="denied",
                actor_type="api_key",
                actor_id=api_key.id,
                project_id=api_key.project_id,
                detail={"reason": "rate_limited", "retry_after": retry_after},
            )
            raise HTTPException(
                status_code=429,
                detail=f"Run submission rate limit exceeded for this project",
                headers={"Retry-After": str(retry_after)},
            )

    service = RunService(db)
    # enqueue=False: the frozen contract executes in-process in the
    # background task below; the legacy queue path is not used.
    run = await service.create_run(api_key.project_id, spec.model_dump(), enqueue=False)
    await record_event(
        action="run.create",
        outcome="success",
        actor_type="api_key",
        actor_id=api_key.id,
        project_id=api_key.project_id,
        resource_type="run",
        resource_id=run.id,
        detail={"goal": run.goal},
    )
    asyncio.create_task(_execute_run(run.id, request))
    return RunStatus(run_id=run.id, status="queued", created_at=run.started_at)


@router.get("/{run_id}", response_model=RunStatus)
async def get_run(
    run_id: str,
    api_key: ApiKey = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Poll for the latest status of a run.

    Tenant isolation (BOLA): the run must belong to the caller's project —
    404 (not 403) so run IDs of other projects are not enumerable.

    Returns RunStatus per the frozen contract:
      - completed: receipt is the full signed receipt (test outcomes inside)
      - failed:    error message, receipt is null (infra crash)
      - queued/running: neither field
    """
    service = RunService(db)
    run = await service.get_run(run_id)
    if not run or run.project_id != api_key.project_id:
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


async def _get_own_run(run_id: str, api_key: ApiKey, db: AsyncSession) -> TestRun:
    """Legacy endpoints share one check: the run must belong to the
    caller's project. 404-on-mismatch keeps run IDs non-enumerable
    across tenants."""
    service = RunService(db)
    run = await service.get_run(run_id)
    if not run or run.project_id != api_key.project_id:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/{run_id}/legacy", response_model=RunStatusResponse)
async def get_run_legacy(
    run_id: str,
    api_key: ApiKey = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Legacy status view (dashboard shape) — not part of frozen v1."""
    run = await _get_own_run(run_id, api_key, db)
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
async def complete_run(
    run_id: str,
    req: CompleteRunRequest,
    api_key: ApiKey = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
):
    run = await _get_own_run(run_id, api_key, db)
    service = RunService(db)
    summary = req.model_dump()
    if req.error:
        await service.fail_run(run.id, req.error)
        outcome_status = "failed"
    else:
        await service.complete_run(run.id, summary)
        outcome_status = "completed"
    await record_event(
        action="run.complete",
        outcome="success",
        actor_type="api_key",
        actor_id=api_key.id,
        project_id=api_key.project_id,
        resource_type="run",
        resource_id=run.id,
        detail={"status": outcome_status},
    )
    return {"run_id": run_id, "status": "completed"}


@router.post("/{run_id}/logs")
async def append_logs(
    run_id: str,
    log_line: str = "",
    api_key: ApiKey = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
):
    run = await _get_own_run(run_id, api_key, db)
    service = RunService(db)
    await service.append_logs(run.id, log_line)
    return {"run_id": run_id, "ack": True}


@router.post("/{run_id}/cancel")
async def cancel_run(
    run_id: str,
    api_key: ApiKey = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
):
    run = await _get_own_run(run_id, api_key, db)
    service = RunService(db)
    await service.cancel_run(run.id)
    await record_event(
        action="run.cancel",
        outcome="success",
        actor_type="api_key",
        actor_id=api_key.id,
        project_id=api_key.project_id,
        resource_type="run",
        resource_id=run.id,
    )
    return {"run_id": run_id, "status": "cancelled"}


@router.get("/{run_id}/proof")
async def get_run_inclusion_proof(
    run_id: str,
    api_key: ApiKey = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Merkle inclusion proof that this run's receipt is in the
    transparency log (SOC 2 CC6.8/CC7.2). Tenant-scoped like every run
    surface; the proof verifies offline against a checkpoint root the
    caller pinned earlier — no trust in the server at verify time.
    """
    run = await _get_own_run(run_id, api_key, db)
    if not settings.transparency_log_path:
        raise HTTPException(
            status_code=404,
            detail="Transparency log is not configured on this control plane",
        )
    receipt_dict = _extract_receipt_dict((run.summary_json or {}).get("receipt"))
    if not receipt_dict:
        raise HTTPException(status_code=404, detail="No signed receipt for this run")

    from pathlib import Path as _Path

    from sandbox_isolation.transparency import (
        LocalTransparencyLog,
        receipt_fingerprint,
    )
    from workflo_schema.sandbox import SignedReceipt

    try:
        leaf = receipt_fingerprint(SignedReceipt(**receipt_dict).canonical_payload())
        log = LocalTransparencyLog(_Path(settings.transparency_log_path))
    except Exception as e:
        # A load failure here is exactly the tamper-detection signal the
        # log exists for — surface it as an error, never as "not found".
        raise HTTPException(
            status_code=500,
            detail=f"Transparency log integrity check failed: {type(e).__name__}",
        ) from e

    proof = log.proof_inclusion(leaf)
    if proof is None:
        raise HTTPException(
            status_code=404,
            detail="Receipt not present in the transparency log",
        )
    return proof
