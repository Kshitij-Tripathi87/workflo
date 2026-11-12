"""Durable dispatch mechanics: transactional outbox + worker leases.

Implements the brief §8 dispatch requirements at the database layer:

- **Transactional outbox** — rows are created by ``DispatchService`` in the
  same transaction as the run + attempt; this module only claims and
  completes them.
- **Worker leases / heartbeats** — a claim is time-bounded; a claimant must
  renew (heartbeat) while it works. An expired lease makes the row
  claimable again, so worker loss recovers instead of hanging forever.
- **Classified retries** — :func:`fail_outbox` reschedules only what its
  caller classifies as transient; the retry executes as a NEW attempt.

All functions are session-based (no session creation here) and commit
explicitly so each state change is durable the moment it returns.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DispatchOutbox, RunAttempt

# Outbox states
PENDING = "pending"
CLAIMED = "claimed"
DONE = "done"
FAILED = "failed"
CANCELLED = "cancelled"

# Attempt states that no worker may still be executing.
ATTEMPT_TERMINAL_STATES = frozenset(
    {
        "COMPLETED",
        "INFRASTRUCTURE_FAILED",
        "EXECUTION_FAILED",
        "TEARDOWN_FAILED",
        "ATTESTATION_FAILED",
        "REJECTED",
    }
)


def _utcnow_naive() -> datetime:
    """Naive UTC — matches the ORM convention (see app.db.models._now)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_worker_id(prefix: str = "worker") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


async def claim_outbox(
    db: AsyncSession,
    worker_id: str,
    *,
    lease_seconds: int = 300,
    limit: int = 1,
) -> list[DispatchOutbox]:
    """Atomically claim up to ``limit`` pending, available outbox rows.

    The claim is a single guarded UPDATE per candidate row (atomic in both
    PostgreSQL and SQLite): a row is claimable only while it is pending,
    past its ``available_at`` backoff, and not inside an unexpired lease.
    ``attempts_count`` is incremented at claim time, so a worker that dies
    mid-execution still consumes one attempt.
    """
    now = _utcnow_naive()
    candidate_ids = (
        (
            await db.execute(
                select(DispatchOutbox.id)
                .where(DispatchOutbox.state == PENDING)
                .where(DispatchOutbox.available_at <= now)
                .where(
                    or_(
                        DispatchOutbox.claimed_until.is_(None),
                        DispatchOutbox.claimed_until < now,
                    )
                )
                .order_by(DispatchOutbox.created_at.asc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )

    claimed: list[DispatchOutbox] = []
    for row_id in candidate_ids:
        result = await db.execute(
            update(DispatchOutbox)
            .where(DispatchOutbox.id == row_id)
            .where(DispatchOutbox.state == PENDING)
            .where(
                or_(
                    DispatchOutbox.claimed_until.is_(None),
                    DispatchOutbox.claimed_until < now,
                )
            )
            .values(
                state=CLAIMED,
                claimed_by=worker_id,
                claimed_until=now + timedelta(seconds=lease_seconds),
                attempts_count=DispatchOutbox.attempts_count + 1,
                updated_at=now,
            )
        )
        if result.rowcount == 1:
            claimed.append(row_id)

    if not claimed:
        return []

    rows = (
        (
            await db.execute(
                select(DispatchOutbox).where(DispatchOutbox.id.in_(claimed))
            )
        )
        .scalars()
        .all()
    )
    await db.commit()
    return sorted(rows, key=lambda row: row.created_at)


async def claim_outbox_by_id(
    db: AsyncSession,
    outbox_id: str,
    worker_id: str,
    *,
    lease_seconds: int = 300,
) -> DispatchOutbox | None:
    """Claim one specific row (the in-process dev worker path)."""
    now = _utcnow_naive()
    result = await db.execute(
        update(DispatchOutbox)
        .where(DispatchOutbox.id == outbox_id)
        .where(DispatchOutbox.state == PENDING)
        .where(
            or_(
                DispatchOutbox.claimed_until.is_(None),
                DispatchOutbox.claimed_until < now,
            )
        )
        .values(
            state=CLAIMED,
            claimed_by=worker_id,
            claimed_until=now + timedelta(seconds=lease_seconds),
            attempts_count=DispatchOutbox.attempts_count + 1,
            updated_at=now,
        )
    )
    if result.rowcount != 1:
        await db.rollback()
        return None
    await db.commit()
    row = await db.get(DispatchOutbox, outbox_id)
    return row


async def renew_lease(
    db: AsyncSession,
    outbox_id: str,
    worker_id: str,
    *,
    lease_seconds: int = 300,
    attempt_id: str | None = None,
) -> bool:
    """Heartbeat: extend the claim if (and only if) we still own it."""
    now = _utcnow_naive()
    result = await db.execute(
        update(DispatchOutbox)
        .where(DispatchOutbox.id == outbox_id)
        .where(DispatchOutbox.state == CLAIMED)
        .where(DispatchOutbox.claimed_by == worker_id)
        .values(
            claimed_until=now + timedelta(seconds=lease_seconds),
            updated_at=now,
        )
    )
    renewed = result.rowcount == 1
    if renewed and attempt_id:
        await db.execute(
            update(RunAttempt)
            .where(RunAttempt.id == attempt_id)
            .values(
                heartbeat_at=now,
                lease_until=now + timedelta(seconds=lease_seconds),
                updated_at=now,
            )
        )
    await db.commit()
    return renewed


async def complete_outbox(db: AsyncSession, outbox_id: str) -> bool:
    result = await db.execute(
        update(DispatchOutbox)
        .where(DispatchOutbox.id == outbox_id)
        .where(DispatchOutbox.state == CLAIMED)
        .values(state=DONE, claimed_until=None, updated_at=_utcnow_naive())
    )
    await db.commit()
    return result.rowcount == 1


async def fail_outbox(
    db: AsyncSession,
    outbox_id: str,
    error: str,
    *,
    transient: bool,
    retry_backoff_seconds: int = 30,
) -> str:
    """Record a claimed row's failure.

    Returns ``"retry"`` when the failure was classified transient and the
    attempt budget allows one more try (the caller then creates the NEW
    attempt + outbox row), otherwise ``"terminal"``.
    """
    now = _utcnow_naive()
    row = await db.get(DispatchOutbox, outbox_id)
    if row is None:
        return "terminal"
    if transient and row.attempts_count < row.max_attempts:
        row.state = PENDING
        row.claimed_by = None
        row.claimed_until = None
        row.available_at = now + timedelta(seconds=retry_backoff_seconds)
        row.last_error = error
        row.updated_at = now
        await db.commit()
        return "retry"
    row.state = FAILED
    row.claimed_until = None
    row.last_error = error
    row.updated_at = now
    await db.commit()
    return "terminal"


async def cancel_pending_dispatch(db: AsyncSession, run_id: str) -> int:
    """Cancel every still-pending dispatch row for a run (cancellation
    request before execution). Returns the number of rows cancelled."""
    now = _utcnow_naive()
    result = await db.execute(
        update(DispatchOutbox)
        .where(DispatchOutbox.run_id == run_id)
        .where(DispatchOutbox.state == PENDING)
        .values(state=CANCELLED, updated_at=now)
    )
    await db.commit()
    return result.rowcount


async def mark_attempts_cancel_requested(db: AsyncSession, run_id: str) -> int:
    """Record the cancellation request on every non-terminal attempt.

    Cancellation is a request, not proof of termination (brief §5): the
    attempt carries CANCEL_REQUESTED until its (Phase 3) graceful-stop and
    teardown path completes. Terminal attempts are never rewritten.
    """
    now = _utcnow_naive()
    result = await db.execute(
        update(RunAttempt)
        .where(RunAttempt.run_id == run_id)
        .where(RunAttempt.state.notin_(ATTEMPT_TERMINAL_STATES))
        .where(RunAttempt.state != "CANCEL_REQUESTED")
        .values(state="CANCEL_REQUESTED", cancelled=True, updated_at=now)
    )
    await db.commit()
    return result.rowcount


async def recover_expired_leases(db: AsyncSession) -> int:
    """Return expired claims to the pending queue (worker-loss recovery)."""
    now = _utcnow_naive()
    result = await db.execute(
        update(DispatchOutbox)
        .where(DispatchOutbox.state == CLAIMED)
        .where(DispatchOutbox.claimed_until.isnot(None))
        .where(DispatchOutbox.claimed_until < now)
        .values(state=PENDING, claimed_by=None, claimed_until=None, updated_at=now)
    )
    await db.commit()
    return result.rowcount


async def finish_attempt(
    db: AsyncSession,
    attempt_id: str,
    *,
    state: str,
    execution_status: str | None = None,
    cancelled: bool = False,
    sandbox_id: str | None = None,
) -> bool:
    """Move an attempt to a terminal (or explicitly recorded) state."""
    now = _utcnow_naive()
    values: dict = {
        "state": state,
        "updated_at": now,
        "finished_at": now if state in ATTEMPT_TERMINAL_STATES else None,
    }
    if execution_status is not None:
        values["execution_status"] = execution_status
    if cancelled:
        values["cancelled"] = True
    if sandbox_id is not None:
        values["sandbox_id"] = sandbox_id
    result = await db.execute(
        update(RunAttempt).where(RunAttempt.id == attempt_id).values(**values)
    )
    await db.commit()
    return result.rowcount == 1
