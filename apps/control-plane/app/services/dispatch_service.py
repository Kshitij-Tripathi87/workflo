"""Durable run dispatch (Phase 2 — brief §8).

Canonical admission path:

    POST /v1/runs
        → validate spec + tenant + rate limit (unchanged)
        → ONE transaction: TestRun + RunAttempt(1) + DispatchOutbox(pending)
        → API returns queued; the dispatch intent is already durable

Execution side (the "worker"):

    claim outbox row (lease) → heartbeat in short sessions while the
    blocking executor works → complete (receipt) or classify the failure
    (transient → NEW attempt + re-dispatch, bounded; otherwise terminal)

Two worker modes share this exact code path:

- **dispatcher loop** (``dispatcher_enabled=True``): the lifespan-started
  loop claims any pending row. Production requires this mode (startup
  guard) — an admitted run survives API restarts.
- **in-process dev worker** (default): the API spawns one task that claims
  the row it just created. Same claim semantics, single-process only.

Session discipline: no session is held open across the blocking executor
call (the legacy path had the same rule). Every bookkeeping step opens a
fresh session and commits before returning.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from workflo_utils.logging import get_logger

from app.core.config import settings
from app.db import database as db_module
from app.db import durable
from app.db.durable import (
    PENDING,
    cancel_pending_dispatch as _cancel_pending,
    claim_outbox,
    claim_outbox_by_id,
    complete_outbox,
    fail_outbox,
    finish_attempt,
    mark_attempts_cancel_requested,
    new_worker_id,
    recover_expired_leases,
    renew_lease,
)
from app.db.models import DispatchOutbox, RunAttempt, TestRun
from app.services.run_service import RunService

logger = get_logger(__name__)

EVENT_RUN_DISPATCH = "run.dispatch"


class DispatchService:
    """Admission-side durable run creation."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def find_run_by_idempotency(
        self, project_id: str, idempotency_key: str
    ) -> Optional[TestRun]:
        stmt = select(TestRun).where(
            TestRun.project_id == project_id,
            TestRun.idempotency_key == idempotency_key,
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def create_run_durable(
        self,
        project_id: str,
        spec: dict,
        idempotency_key: str | None,
    ) -> tuple[TestRun, RunAttempt, DispatchOutbox]:
        """Persist run + attempt + dispatch intent in ONE transaction.

        The unique constraint ``(project_id, idempotency_key)`` is the
        last line of defense against duplicate admission; callers should
        check :meth:`find_run_by_idempotency` first for the replay path.
        """
        run_id = str(uuid.uuid4())
        attempt_id = str(uuid.uuid4())
        outbox_id = str(uuid.uuid4())

        run = TestRun(
            id=run_id,
            project_id=project_id,
            goal=spec.get("goal", "smoke"),
            status="queued",
            spec_json=spec,
            idempotency_key=idempotency_key,
        )
        attempt = RunAttempt(
            id=attempt_id,
            run_id=run_id,
            project_id=project_id,
            attempt_number=1,
            state="PROVISIONING",
        )
        outbox = DispatchOutbox(
            id=outbox_id,
            run_id=run_id,
            attempt_id=attempt_id,
            project_id=project_id,
            event_type=EVENT_RUN_DISPATCH,
            payload={"spec": spec},
            state=PENDING,
            max_attempts=settings.dispatch_max_attempts,
        )
        self.db.add_all([run, attempt, outbox])
        await self.db.commit()
        await self.db.refresh(run)
        return run, attempt, outbox


# ---------------------------------------------------------------------------
# Receipt/transparency helpers (shared by the API surface and the worker)
# ---------------------------------------------------------------------------


def extract_receipt_dict(summary_receipt) -> Optional[dict]:
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


def _spawn_audit(coro) -> None:
    """Schedule an audit-write coroutine on the running loop, if any."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    asyncio.ensure_future(coro)


async def _audit_transparency_append(run_id: str, outcome: str, detail: dict) -> None:
    from app.services.audit_service import record_event

    await record_event(
        action="transparency.append",
        outcome=outcome,
        actor_type="system",
        project_id=None,
        resource_type="run",
        resource_id=run_id,
        detail=detail,
    )


def append_receipt_to_transparency_log(receipt_dict: dict, run_id: str) -> None:
    """Append the receipt's canonical fingerprint to the transparency log.

    Best-effort and off the request path by design (a logging outage must
    not fail customer runs); the attempt is audit-visible either way —
    identical behavior to the pre-durable-path implementation.
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
        _spawn_audit(
            _audit_transparency_append(
                run_id,
                "success",
                {"tree_size": record.tree_size, "seq": record.seq},
            )
        )
    except Exception as e:  # noqa: BLE001 — transparency must not fail runs
        _spawn_audit(
            _audit_transparency_append(
                run_id, "error", {"error": f"{type(e).__name__}: {e}"}
            )
        )


# ---------------------------------------------------------------------------
# Worker side
# ---------------------------------------------------------------------------

# Only classified transient failures re-dispatch (brief §8: "Retry only
# classified transient stages"). Everything else — including bad specs,
# missing executors, and policy violations — is terminal. A retry is a NEW
# attempt with a NEW sandbox identity, never a resume.
_TRANSIENT_EXCEPTIONS = (TimeoutError, ConnectionError, OSError)


def _is_transient(exc: BaseException) -> bool:
    return isinstance(exc, _TRANSIENT_EXCEPTIONS)


def _build_spec(spec_dict: dict):
    from workflo_schema.sandbox import SandboxSpec

    return SandboxSpec(**spec_dict)


def _heartbeat_loop(outbox_id: str, attempt_id: str, worker_id: str, stop: asyncio.Event):
    """Return a task that renews the lease in short sessions until stopped."""

    async def _beat() -> None:
        interval = max(1, int(settings.dispatch_heartbeat_interval))
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass
            if stop.is_set():
                return
            try:
                async with db_module.async_session_factory() as hb_db:
                    await renew_lease(
                        hb_db,
                        outbox_id,
                        worker_id,
                        lease_seconds=settings.dispatch_lease_seconds,
                        attempt_id=attempt_id,
                    )
            except Exception:  # noqa: BLE001 — a heartbeat hiccup must never kill the run
                logger.warning(
                    "dispatch.heartbeat_failed",
                    extra={"extra_data": {"outbox_id": outbox_id}},
                )

    return asyncio.create_task(_beat())


async def _finalize_success(
    run_id: str, attempt_id: str, outbox_id: str, result
) -> None:
    """Persist the completed attempt + receipt + done outbox row."""
    async with db_module.async_session_factory() as db:
        run = await db.get(TestRun, run_id)
        if run is not None:
            # RLS defense-in-depth: background sessions don't inherit a
            # request's tenant binding — set it from the run itself.
            await db_module.set_tenant_context(db, run.project_id)
        was_cancelled = bool(run is not None and run.status == "cancelled")
        result_json = json.loads(result.to_json())
        service = RunService(db)
        await service.complete_run(
            run_id, {"status": "completed", "receipt": result_json}
        )
        # Cancellation is a request (brief §5): a run cancelled mid-flight
        # that still ran to completion ends COMPLETED with the cancellation
        # recorded on the attempt — the machine reaches COMPLETED through
        # teardown/signing either way, and the flag keeps the history honest.
        receipt = getattr(result, "receipt", None)
        raw_sandbox_id = getattr(receipt, "sandbox_id", None)
        # Durability boundary: only a real string may reach the attempt row;
        # anything else (mock objects, exotic shapes) records as unknown.
        sandbox_id = raw_sandbox_id if isinstance(raw_sandbox_id, str) else None
        await finish_attempt(
            db,
            attempt_id,
            state="COMPLETED",
            execution_status="completed",
            sandbox_id=sandbox_id,
            cancelled=was_cancelled,
        )
        await complete_outbox(db, outbox_id)
        receipt_dict = extract_receipt_dict(result_json)
        if receipt_dict:
            append_receipt_to_transparency_log(receipt_dict, run_id)


async def _finalize_failure(
    run_id: str, attempt_id: str, outbox_id: str, exc: BaseException
) -> None:
    """Classify the failure and persist the outcome durably."""
    error = f"{type(exc).__name__}: {exc}"
    transient = _is_transient(exc)
    async with db_module.async_session_factory() as db:
        run = await db.get(TestRun, run_id)
        if run is not None:
            await db_module.set_tenant_context(db, run.project_id)
        outcome = await fail_outbox(
            db,
            outbox_id,
            error,
            transient=transient,
            retry_backoff_seconds=settings.dispatch_retry_backoff_seconds,
        )
        if outcome == "retry":
            # Transient infrastructure failure → NEW attempt, NEW sandbox.
            await finish_attempt(
                db,
                attempt_id,
                state="INFRASTRUCTURE_FAILED",
                execution_status="infrastructure_failed",
            )
            next_number = await _create_retry_attempt(db, outbox_id)
            logger.warning(
                "dispatch.retry_scheduled",
                extra={"extra_data": {"run_id": run_id, "next_attempt": next_number}},
            )
            should_spawn = not settings.dispatcher_enabled
        else:
            await finish_attempt(
                db,
                attempt_id,
                state="INFRASTRUCTURE_FAILED"
                if transient
                else "EXECUTION_FAILED",
                execution_status="infrastructure_failed"
                if transient
                else "execution_failed",
            )
            service = RunService(db)
            await service.fail_run(run_id, error)
            logger.error(
                "dispatch.terminal_failure",
                extra={"extra_data": {"run_id": run_id, "error": error}},
            )
            should_spawn = False

    if outcome == "retry" and should_spawn:
        await _spawn_follow_on(outbox_id, run_id)


async def _create_retry_attempt(db: AsyncSession, outbox_id: str) -> int:
    """Create the NEXT attempt + a fresh pending dispatch row for a run.

    One transaction: new attempt row + new outbox row (fresh claim budget).
    """
    row = await db.get(DispatchOutbox, outbox_id)
    if row is None:
        return 0
    highest = (
        await db.execute(
            select(func.max(RunAttempt.attempt_number)).where(
                RunAttempt.run_id == row.run_id
            )
        )
    ).scalar() or 0
    attempt = RunAttempt(
        id=str(uuid.uuid4()),
        run_id=row.run_id,
        project_id=row.project_id,
        attempt_number=int(highest) + 1,
        state="PROVISIONING",
    )
    retry_row = DispatchOutbox(
        id=str(uuid.uuid4()),
        run_id=row.run_id,
        attempt_id=attempt.id,
        project_id=row.project_id,
        event_type=EVENT_RUN_DISPATCH,
        payload=row.payload,
        state=PENDING,
        max_attempts=row.max_attempts,
    )
    db.add_all([attempt, retry_row])
    await db.commit()
    return int(highest) + 1


async def _spawn_follow_on(original_outbox_id: str, run_id: str) -> None:
    """In-process dev mode: execute the freshly scheduled retry row.

    The dispatcher loop mode does not need this — the loop claims the new
    pending row on its next pass.
    """
    async with db_module.async_session_factory() as db:
        stmt = (
            select(DispatchOutbox)
            .where(DispatchOutbox.run_id == run_id)
            .where(DispatchOutbox.state == PENDING)
            .order_by(DispatchOutbox.created_at.desc())
            .limit(1)
        )
        pending = (await db.execute(stmt)).scalars().first()
        if pending is None:
            return
        spec_dict = (pending.payload or {}).get("spec") or {}
        outbox_id = str(pending.id)
        run_id = str(pending.run_id)
        attempt_id = str(pending.attempt_id)
    asyncio.create_task(
        execute_claimed_dispatch(outbox_id, run_id, attempt_id, spec_dict)
    )


async def execute_claimed_dispatch(
    outbox_id: str,
    run_id: str,
    attempt_id: str,
    spec_dict: dict,
) -> None:
    """Claim one specific outbox row and execute it (dev worker path)."""
    worker_id = new_worker_id("inproc")
    async with db_module.async_session_factory() as claim_db:
        row = await claim_outbox_by_id(
            claim_db,
            outbox_id,
            worker_id,
            lease_seconds=settings.dispatch_lease_seconds,
        )
        if row is None:
            # Already claimed by another worker, or cancelled before start.
            return
    await execute_payload(outbox_id, run_id, attempt_id, spec_dict, worker_id)


async def execute_payload(
    outbox_id: str,
    run_id: str,
    attempt_id: str,
    spec_dict: dict,
    worker_id: str,
) -> None:
    """Execute an ALREADY-CLAIMED dispatch row (the claim happened once).

    Both worker paths converge here: the dev worker after its own claim,
    the dispatcher loop after ``claim_outbox``. No session is held across
    the blocking executor call; the heartbeat runs in its own short
    sessions.
    """
    # Cancellation before start: the request wins; no sandbox is created.
    async with db_module.async_session_factory() as pre_db:
        run = await pre_db.get(TestRun, run_id)
        if run is not None and run.status == "cancelled":
            await db_module.set_tenant_context(pre_db, run.project_id)
            await finish_attempt(
                pre_db, attempt_id, state="CANCEL_REQUESTED", cancelled=True
            )
            row2 = await pre_db.get(DispatchOutbox, outbox_id)
            if row2 is not None and row2.state == durable.CLAIMED:
                row2.state = durable.CANCELLED
                row2.claimed_until = None
                await pre_db.commit()
            return

    stop = asyncio.Event()
    heartbeat = _heartbeat_loop(outbox_id, attempt_id, worker_id, stop)
    try:
        from workflo_executor import SandboxExecutor

        executor = SandboxExecutor()
        spec = _build_spec(spec_dict)
        # SandboxExecutor.run is blocking (docker/git subprocesses); run it
        # off the event loop so the worker loop stays responsive.
        result = await asyncio.to_thread(executor.run, spec)
    except Exception as e:  # noqa: BLE001 — classified in _finalize_failure
        stop.set()
        try:
            await heartbeat
        except Exception:  # noqa: BLE001
            pass
        await _finalize_failure(run_id, attempt_id, outbox_id, e)
        return

    stop.set()
    try:
        await heartbeat
    except Exception:  # noqa: BLE001
        pass
    await _finalize_success(run_id, attempt_id, outbox_id, result)


async def dispatch_one(worker_id: str | None = None) -> bool:
    """Claim and process at most one pending dispatch. True if work was done."""
    worker_id = worker_id or new_worker_id("loop")
    async with db_module.async_session_factory() as db:
        await recover_expired_leases(db)
        claimed = await claim_outbox(
            db,
            worker_id,
            lease_seconds=settings.dispatch_lease_seconds,
            limit=1,
        )
        if not claimed:
            return False
        row = claimed[0]

    if row.event_type != EVENT_RUN_DISPATCH:
        # Unknown event types are recorded as terminal failures, never
        # silently dropped (fail closed on schema drift).
        async with db_module.async_session_factory() as db:
            await fail_outbox(
                db, str(row.id), f"unknown event_type {row.event_type}", transient=False
            )
        return True

    spec_dict = (row.payload or {}).get("spec") or {}
    # The row is already claimed by THIS worker — execute the payload
    # directly (the dev path's execute_claimed_dispatch would re-claim and
    # silently return, leaving the row claimed forever).
    await execute_payload(
        str(row.id), str(row.run_id), str(row.attempt_id), spec_dict, worker_id
    )
    return True


async def dispatcher_loop(
    worker_id: str | None = None, stop: asyncio.Event | None = None
) -> None:
    """The production worker loop (lifespan-started when enabled)."""
    stop = stop or asyncio.Event()
    worker_id = worker_id or new_worker_id("loop")
    logger.info("dispatch.loop_started", extra={"extra_data": {"worker_id": worker_id}})
    try:
        while not stop.is_set():
            try:
                worked = await dispatch_one(worker_id)
                if not worked:
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=1.0)
                    except asyncio.TimeoutError:
                        pass
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 — the loop must survive
                logger.error(
                    "dispatch.loop_error",
                    extra={"extra_data": {"error": f"{type(e).__name__}: {e}"}},
                )
                try:
                    await asyncio.wait_for(stop.wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    pass
    finally:
        logger.info(
            "dispatch.loop_stopped", extra={"extra_data": {"worker_id": worker_id}}
        )


async def cancel_run_dispatch(db: AsyncSession, run_id: str) -> dict:
    """Cancellation request (brief §5): stop what has not started, record
    the request on what is running. Returns what happened, honestly."""
    cancelled_rows = await _cancel_pending(db, run_id)
    touched_attempts = await mark_attempts_cancel_requested(db, run_id)
    return {
        "pending_dispatches_cancelled": cancelled_rows,
        "attempts_marked": touched_attempts,
    }


__all__ = [
    "DispatchService",
    "EVENT_RUN_DISPATCH",
    "append_receipt_to_transparency_log",
    "cancel_run_dispatch",
    "dispatch_one",
    "dispatcher_loop",
    "execute_claimed_dispatch",
    "execute_payload",
    "extract_receipt_dict",
]
