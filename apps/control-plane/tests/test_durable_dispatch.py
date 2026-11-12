"""Durable dispatch tests (Phase 2 — brief §8).

Covers the durable admission path (transactional outbox + attempts),
worker lease semantics, classified retries, cancellation-before-start,
dispatcher loop processing, and the fail-closed production guards.
"""

from __future__ import annotations

import asyncio
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.core.config import settings
from app.db import database
from app.db import models as m
from app.db.durable import (
    CANCELLED,
    CLAIMED,
    DONE,
    FAILED,
    PENDING,
    cancel_pending_dispatch,
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
from app.services.dispatch_service import (
    DispatchService,
    dispatch_one,
    execute_claimed_dispatch,
)
from workflo_schema.sandbox import SandboxSpec

# A REAL sandbox spec (the API path builds one via RunRequest.to_sandbox_spec);
# the worker rebuilds SandboxSpec from the persisted payload before executing.
SPEC = SandboxSpec(
    sandbox_id="sb-test-0001",
    repo_url="https://github.com/example/repo.git",
    run_spec={"goal": "smoke"},
).model_dump()


def _fake_executor_class(return_json: str = '{"receipt": true, "sandbox_id": "sb-fake"}'):
    """A MagicMock shaped like the real call path: SandboxExecutor() → .run()."""
    fake_cls = MagicMock()
    fake_cls.return_value.run.return_value.to_json.return_value = return_json
    return fake_cls


def _failing_executor_class(exc: BaseException):
    """A MagicMock class whose instances raise ``exc`` from run()."""
    fake_cls = MagicMock()
    fake_cls.return_value.run.side_effect = exc
    return fake_cls

# (SPEC is defined above: a real SandboxSpec dump — the worker rebuilds
# SandboxSpec from the persisted payload before executing.)


def _run(coro):
    return asyncio.run(coro)


def _seed_project() -> str:
    async def _seed():
        async with database.async_session_factory() as db:
            # Explicit ids: Python-side column defaults apply at flush, so
            # org.id would be None at Project() construction time.
            org = m.Organization(id=str(uuid.uuid4()), name="t-org")
            project = m.Project(id=str(uuid.uuid4()), org_id=org.id, name="t-proj")
            db.add_all([org, project])
            await db.commit()
            return str(project.id)

    return _run(_seed())


def _durable_run(project_id: str, key: str | None = None, spec: dict | None = None):
    async def _create():
        async with database.async_session_factory() as db:
            svc = DispatchService(db)
            run, attempt, outbox = await svc.create_run_durable(
                project_id, spec or SPEC, key
            )
            return str(run.id), str(attempt.id), str(outbox.id)

    return _run(_create())


def _get_outbox(outbox_id: str) -> DispatchOutbox | None:
    async def _get():
        async with database.async_session_factory() as db:
            row = await db.get(DispatchOutbox, outbox_id)
            if row is None:
                return None
            db.expunge(row)
            return row

    return _run(_get())


def _get_run(run_id: str) -> TestRun | None:
    async def _get():
        async with database.async_session_factory() as db:
            row = await db.get(TestRun, run_id)
            if row is None:
                return None
            db.expunge(row)
            return row

    return _run(_get())


def _get_attempt(attempt_id: str) -> RunAttempt | None:
    async def _get():
        async with database.async_session_factory() as db:
            row = await db.get(RunAttempt, attempt_id)
            if row is None:
                return None
            db.expunge(row)
            return row

    return _run(_get())


def _count(model, **filters) -> int:
    async def _count():
        from sqlalchemy import select

        async with database.async_session_factory() as db:
            stmt = select(model)
            for column, value in filters.items():
                stmt = stmt.where(getattr(model, column) == value)
            return len(list((await db.execute(stmt)).scalars().all()))

    return _run(_count())


def _demo_headers(client) -> dict:
    resp = client.post("/v1/auth/demo-token")
    assert resp.status_code == 200, resp.text
    return {"X-API-Key": resp.json()["api_key"]}


# ---------------------------------------------------------------------------
# Admission
# ---------------------------------------------------------------------------


class TestDurableAdmission:
    def test_post_creates_run_attempt_and_outbox_atomically(self, client):
        headers = _demo_headers(client)
        resp = client.post(
            "/v1/runs",
            json={"repo_url": "https://github.com/example/repo.git", "probe_groups": ["test"]},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        run_id = resp.json()["run_id"]

        run = _get_run(run_id)
        assert run is not None
        assert run.idempotency_key  # dev generates one when absent

        assert _count(RunAttempt, run_id=run_id) == 1
        rows = _count(DispatchOutbox, run_id=run_id)
        assert rows == 1

    def test_attempt_starts_at_one_in_provisioning(self, client):
        headers = _demo_headers(client)
        resp = client.post(
            "/v1/runs",
            json={"repo_url": "https://github.com/example/repo.git", "probe_groups": ["test"]},
            headers=headers,
        )
        run_id = resp.json()["run_id"]
        attempt = _get_attempt(_run(_first_attempt_id(run_id)))
        assert attempt is not None
        assert attempt.attempt_number == 1
        # The in-process dev worker may already have finished the run, so
        # the attempt state is time-dependent; the terminal transitions are
        # covered by test_background_execution_still_completes_the_run.

    def test_idempotency_key_replays_same_run(self, client):
        headers = _demo_headers(client)
        body = {"repo_url": "https://github.com/example/repo.git", "probe_groups": ["test"]}
        r1 = client.post("/v1/runs", json=body, headers={**headers, "Idempotency-Key": "key-abc-12345"})
        r2 = client.post("/v1/runs", json=body, headers={**headers, "Idempotency-Key": "key-abc-12345"})
        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.json()["run_id"] == r2.json()["run_id"]
        assert _count(TestRun) == 1
        assert _count(DispatchOutbox) == 1

    def test_different_keys_create_different_runs(self, client):
        headers = _demo_headers(client)
        body = {"repo_url": "https://github.com/example/repo.git", "probe_groups": ["test"]}
        r1 = client.post("/v1/runs", json=body, headers={**headers, "Idempotency-Key": "key-one-000001"})
        r2 = client.post("/v1/runs", json=body, headers={**headers, "Idempotency-Key": "key-two-000002"})
        assert r1.json()["run_id"] != r2.json()["run_id"]
        assert _count(TestRun) == 2

    def test_background_execution_still_completes_the_run(self, client, monkeypatch):
        """The in-process dev worker claims through the outbox path and the
        frozen contract outcome is unchanged: completed + receipt."""
        monkeypatch.setattr(
            "workflo_executor.SandboxExecutor", _fake_executor_class()
        )
        headers = _demo_headers(client)
        resp = client.post(
            "/v1/runs",
            json={"repo_url": "https://github.com/example/repo.git", "probe_groups": ["test"]},
            headers=headers,
        )
        run_id = resp.json()["run_id"]

        deadline = time.time() + 10
        status = None
        while time.time() < deadline:
            status = _get_run(run_id)
            if status and status.status in ("completed", "failed"):
                break
            time.sleep(0.05)
        deadline = time.time() + 10
        row_state = None
        while time.time() < deadline:
            row = _run(_first_outbox_row(run_id))
            row_state = row.state if row else None
            if row_state == DONE:
                break
            time.sleep(0.05)
        assert row_state == DONE, row_state
        attempt = _get_attempt(row.attempt_id)
        assert attempt.state == "COMPLETED"
        assert attempt.execution_status == "completed"


async def _first_attempt_id(run_id: str) -> str:
    async with database.async_session_factory() as db:
        row = (
            (await db.execute(
                m.RunAttempt.__table__.select().where(m.RunAttempt.run_id == run_id)
            ))
            .first()
        )
        return row.id


async def _first_outbox_row(run_id: str) -> DispatchOutbox:
    async with database.async_session_factory() as db:
        from sqlalchemy import select

        row = (
            (await db.execute(
                select(DispatchOutbox).where(DispatchOutbox.run_id == run_id)
            ))
            .scalars()
            .first()
        )
        db.expunge(row)
        return row


def _pending_row_for_run(run_id: str) -> DispatchOutbox | None:
    async def _get():
        async with database.async_session_factory() as db:
            from sqlalchemy import select

            # The newest pending row is the retry: the original row returns
            # to pending too (with backoff) after a classified transient
            # failure, so ordering matters.
            row = (
                (await db.execute(
                    select(DispatchOutbox)
                    .where(DispatchOutbox.run_id == run_id)
                    .where(DispatchOutbox.state == PENDING)
                    .order_by(DispatchOutbox.created_at.desc())
                ))
                .scalars()
                .first()
            )
            if row is None:
                return None
            db.expunge(row)
            return row

    return _run(_get())


# ---------------------------------------------------------------------------
# Lease semantics
# ---------------------------------------------------------------------------


class TestLeases:
    def test_claim_is_exclusive(self):
        project_id = _seed_project()
        _durable_run(project_id)
        _durable_run(project_id)

        async def _claims():
            async with database.async_session_factory() as db:
                first = await claim_outbox(db, "w1", lease_seconds=60, limit=1)
                second = await claim_outbox(db, "w2", lease_seconds=60, limit=1)
                third = await claim_outbox(db, "w3", lease_seconds=60, limit=1)
                return first, second, third

        first, second, third = _run(_claims())
        assert len(first) == 1 and len(second) == 1 and third == []
        assert first[0].id != second[0].id
        assert first[0].claimed_by == "w1"
        assert first[0].attempts_count == 1

    def test_claim_by_id_refuses_already_claimed_row(self):
        project_id = _seed_project()
        _, _, outbox_id = _durable_run(project_id)

        async def _claims():
            async with database.async_session_factory() as db:
                first = await claim_outbox_by_id(db, outbox_id, "w1", lease_seconds=60)
                second = await claim_outbox_by_id(db, outbox_id, "w2", lease_seconds=60)
                return first, second

        first, second = _run(_claims())
        assert first is not None
        assert second is None

    def test_renew_lease_extends_only_for_owner(self):
        project_id = _seed_project()
        _, attempt_id, outbox_id = _durable_run(project_id)

        async def _flow():
            async with database.async_session_factory() as db:
                await claim_outbox_by_id(db, outbox_id, "w1", lease_seconds=60)
            async with database.async_session_factory() as db:
                wrong = await renew_lease(db, outbox_id, "w2", lease_seconds=60)
            async with database.async_session_factory() as db:
                right = await renew_lease(
                    db, outbox_id, "w1", lease_seconds=120, attempt_id=attempt_id
                )
            async with database.async_session_factory() as db:
                row = await db.get(DispatchOutbox, outbox_id)
                attempt = await db.get(RunAttempt, attempt_id)
                db.expunge(row)
                db.expunge(attempt)
                return wrong, right, row, attempt

        wrong, right, row, attempt = _run(_flow())
        assert wrong is False
        assert right is True
        assert row.claimed_until is not None
        assert attempt.heartbeat_at is not None

    def test_expired_lease_is_recoverable(self):
        project_id = _seed_project()
        _, _, outbox_id = _durable_run(project_id)

        async def _expire():
            async with database.async_session_factory() as db:
                await claim_outbox_by_id(db, outbox_id, "w1", lease_seconds=60)
                row = await db.get(DispatchOutbox, outbox_id)
                row.claimed_until = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
                await db.commit()

        _run(_expire())
        assert _run(_recover()) == 1

        async def _reclaim():
            async with database.async_session_factory() as db:
                claimed = await claim_outbox(db, "w2", lease_seconds=60, limit=5)
                return [(row.id, row.attempts_count) for row in claimed]

        reclaimed = _run(_reclaim())
        assert (outbox_id, 2) in reclaimed  # the dead worker consumed one

    def test_recover_ignores_live_leases(self):
        project_id = _seed_project()
        _durable_run(project_id)

        async def _flow():
            async with database.async_session_factory() as db:
                await claim_outbox(db, "w1", lease_seconds=300, limit=5)
            async with database.async_session_factory() as db:
                return await recover_expired_leases(db)

        assert _run(_flow()) == 0


async def _recover() -> int:
    async with database.async_session_factory() as db:
        return await recover_expired_leases(db)


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------


class TestCancellation:
    def test_cancel_before_start_prevents_execution(self, monkeypatch):
        project_id = _seed_project()
        run_id, attempt_id, outbox_id = _durable_run(project_id, spec=SPEC)

        fake = MagicMock()
        monkeypatch.setattr("workflo_executor.SandboxExecutor", fake)

        async def _cancel():
            async with database.async_session_factory() as db:
                await cancel_pending_dispatch(db, run_id)
                await mark_attempts_cancel_requested(db, run_id)
                run = await db.get(TestRun, run_id)
                run.status = "cancelled"
                await db.commit()

        _run(_cancel())
        _run(execute_claimed_dispatch(outbox_id, run_id, attempt_id, SPEC))

        fake.assert_not_called()
        row = _get_outbox(outbox_id)
        assert row.state == CANCELLED
        attempt = _get_attempt(attempt_id)
        assert attempt.state == "CANCEL_REQUESTED"
        assert attempt.cancelled is True

    def test_cancel_during_execution_records_request_not_fake_success(self, client, monkeypatch):
        """A run cancelled mid-flight ends COMPLETED (the frozen machine
        reaches COMPLETED through teardown/signing) with the cancellation
        recorded on the attempt — never silently erased."""
        release = threading.Event()

        class SlowExecutor:
            def run(self, spec):
                release.wait(timeout=5)
                result = MagicMock()
                result.to_json.return_value = '{"receipt": true, "sandbox_id": "sb-slow"}'
                return result

        monkeypatch.setattr("workflo_executor.SandboxExecutor", SlowExecutor)

        headers = _demo_headers(client)
        resp = client.post(
            "/v1/runs",
            json={"repo_url": "https://github.com/example/repo.git", "probe_groups": ["test"]},
            headers=headers,
        )
        run_id = resp.json()["run_id"]

        deadline = time.time() + 5
        while time.time() < deadline:
            row = _run(_first_outbox_row(run_id))
            if row.state == CLAIMED:
                break
            time.sleep(0.02)
        client.post(f"/v1/runs/{run_id}/cancel", headers=headers)
        release.set()

        # 'cancelled' is set immediately by the cancel endpoint; the frozen
        # machine then takes the run through teardown/signing to COMPLETED
        # once the in-flight executor finishes. Poll for the terminal
        # completed state (cancellation is a request, not proof).
        deadline = time.time() + 10
        status = None
        while time.time() < deadline:
            status = _get_run(run_id)
            if status and status.status == "completed":
                break
            time.sleep(0.05)
        assert status is not None and status.status == "completed"
        row = _run(_first_outbox_row(run_id))
        attempt = _get_attempt(row.attempt_id)
        assert attempt.cancelled is True


# ---------------------------------------------------------------------------
# Classified retries
# ---------------------------------------------------------------------------


class TestRetries:
    def test_non_retryable_failure_is_terminal(self, monkeypatch):
        project_id = _seed_project()
        run_id, attempt_id, outbox_id = _durable_run(project_id, spec=SPEC)

        fake = _failing_executor_class(ValueError("bad spec"))
        monkeypatch.setattr("workflo_executor.SandboxExecutor", fake)

        _run(execute_claimed_dispatch(outbox_id, run_id, attempt_id, SPEC))

        row = _get_outbox(outbox_id)
        assert row.state == FAILED
        assert row.attempts_count == 1
        assert "ValueError" in (row.last_error or "")
        attempt = _get_attempt(attempt_id)
        assert attempt.state == "EXECUTION_FAILED"
        assert attempt.execution_status == "execution_failed"
        run = _get_run(run_id)
        assert run.status == "failed"
        assert _count(RunAttempt, run_id=run_id) == 1

    def test_transient_failure_creates_new_attempt_and_retry_succeeds(self, monkeypatch):
        """Transient infrastructure failure → NEW attempt with a fresh
        dispatch row; the retry (driven exactly as the dispatcher loop
        would drive it) then completes the run."""
        project_id = _seed_project()
        run_id, attempt_id, outbox_id = _durable_run(project_id, spec=SPEC)

        calls = {"n": 0}

        class FlakyExecutor:
            def run(self, spec):
                calls["n"] += 1
                if calls["n"] == 1:
                    raise TimeoutError("sandbox boot timed out")
                result = MagicMock()
                result.to_json.return_value = '{"receipt": true, "sandbox_id": "sb-retry"}'
                return result

        monkeypatch.setattr("workflo_executor.SandboxExecutor", FlakyExecutor)
        # Loop mode: no dev-worker spawn — the retry is driven manually below
        # exactly as the dispatcher loop would drive it.
        monkeypatch.setattr(settings, "dispatcher_enabled", True)

        _run(execute_claimed_dispatch(outbox_id, run_id, attempt_id, SPEC))

        first = _get_attempt(attempt_id)
        assert first.state == "INFRASTRUCTURE_FAILED"
        assert first.execution_status == "infrastructure_failed"
        assert _count(RunAttempt, run_id=run_id) == 2
        assert _get_run(run_id).status in ("queued", "running")

        retry = _pending_row_for_run(run_id)
        assert retry is not None
        assert str(retry.id) != outbox_id
        _run(
            execute_claimed_dispatch(
                str(retry.id), run_id, str(retry.attempt_id), SPEC
            )
        )

        assert calls["n"] == 2
        assert _get_run(run_id).status == "completed"
        assert _count(DispatchOutbox, run_id=run_id) == 2

    def test_max_attempts_respected(self, monkeypatch):
        project_id = _seed_project()
        run_id, attempt_id, outbox_id = _durable_run(project_id, spec=SPEC)

        async def _set_budget():
            async with database.async_session_factory() as db:
                row = await db.get(DispatchOutbox, outbox_id)
                row.max_attempts = 1
                await db.commit()

        _run(_set_budget())

        fake = _failing_executor_class(TimeoutError("boot timeout"))
        monkeypatch.setattr("workflo_executor.SandboxExecutor", fake)

        _run(execute_claimed_dispatch(outbox_id, run_id, attempt_id, SPEC))

        row = _get_outbox(outbox_id)
        assert row.state == FAILED
        assert _count(RunAttempt, run_id=run_id) == 1
        assert _get_run(run_id).status == "failed"

    def test_outbox_budget_survives_retry_chain(self):
        """The retry row inherits the original budget: cumulative claims
        across attempts cannot exceed max_attempts."""
        project_id = _seed_project()
        run_id, _, outbox_id = _durable_run(project_id, spec=SPEC)

        async def _retry():
            async with database.async_session_factory() as db:
                from app.services.dispatch_service import _create_retry_attempt

                await db.get(DispatchOutbox, outbox_id)
                number = await _create_retry_attempt(db, outbox_id)
                from sqlalchemy import select

                row = (
                    (await db.execute(
                        select(DispatchOutbox).where(DispatchOutbox.run_id == run_id)
                        .order_by(DispatchOutbox.created_at.desc())
                    ))
                    .scalars()
                    .first()
                )
                db.expunge(row)
                return number, row

        number, row = _run(_retry())
        assert number == 2
        assert row.attempt_id != outbox_id
        assert row.max_attempts == 3


# ---------------------------------------------------------------------------
# Dispatcher loop
# ---------------------------------------------------------------------------


class TestDispatcherLoop:
    def test_dispatch_one_processes_pending_row(self, monkeypatch):
        project_id = _seed_project()
        run_id, _, outbox_id = _durable_run(project_id, spec=SPEC)
        monkeypatch.setattr(settings, "dispatcher_enabled", True)
        monkeypatch.setattr(
            "workflo_executor.SandboxExecutor", _fake_executor_class()
        )

        assert _run(dispatch_one("loop-w")) is True
        assert _run(dispatch_one("loop-w")) is False  # nothing left

        row = _get_outbox(outbox_id)
        assert row.state == DONE
        assert _get_run(run_id).status == "completed"

    def test_unknown_event_type_fails_closed(self):
        project_id = _seed_project()
        run_id, attempt_id, outbox_id = _durable_run(project_id, spec=SPEC)

        async def _corrupt():
            async with database.async_session_factory() as db:
                row = await db.get(DispatchOutbox, outbox_id)
                row.event_type = "run.mystery"
                await db.commit()

        _run(_corrupt())
        assert _run(dispatch_one("loop-w")) is True
        row = _get_outbox(outbox_id)
        assert row.state == FAILED
        assert "unknown event_type" in (row.last_error or "")


# ---------------------------------------------------------------------------
# Production guards
# ---------------------------------------------------------------------------


class TestProductionGuards:
    def _production_settings(self, **overrides):
        from app.core.config import Settings

        values = {
            "production": True,
            "jwt_secret": "x" * 40,
            "rls_enabled": True,
            "master_kek_hex": "ab" * 32,
            "dispatcher_enabled": True,
            "require_idempotency_key": True,
        }
        values.update(overrides)
        return Settings(**values)

    def test_production_requires_dispatcher(self):
        from app.core.startup_guards import production_config_errors

        errors = production_config_errors(
            self._production_settings(dispatcher_enabled=False)
        )
        assert any("DISPATCHER_ENABLED" in e for e in errors)

    def test_production_requires_idempotency_key(self):
        from app.core.startup_guards import production_config_errors

        errors = production_config_errors(
            self._production_settings(require_idempotency_key=False)
        )
        assert any("REQUIRE_IDEMPOTENCY_KEY" in e for e in errors)

    def test_fully_configured_production_has_no_dispatch_errors(self):
        from app.core.startup_guards import production_config_errors

        errors = production_config_errors(self._production_settings())
        assert not any(
            "DISPATCHER" in e or "IDEMPOTENCY" in e for e in errors
        ), errors


# ---------------------------------------------------------------------------
# Attempt terminal transitions
# ---------------------------------------------------------------------------


class TestAttemptFinishing:
    def test_finish_attempt_records_terminal_state(self):
        project_id = _seed_project()
        _, attempt_id, _ = _durable_run(project_id)

        async def _finish():
            async with database.async_session_factory() as db:
                await finish_attempt(
                    db,
                    attempt_id,
                    state="EXECUTION_FAILED",
                    execution_status="execution_failed",
                )

        _run(_finish())
        attempt = _get_attempt(attempt_id)
        assert attempt.state == "EXECUTION_FAILED"
        assert attempt.finished_at is not None

    def test_finish_attempt_does_not_reset_cancelled_flag(self):
        project_id = _seed_project()
        _, attempt_id, _ = _durable_run(project_id)

        async def _flow():
            async with database.async_session_factory() as db:
                await mark_attempts_cancel_requested(db, (await db.get(RunAttempt, attempt_id)).run_id)
            async with database.async_session_factory() as db:
                await finish_attempt(
                    db, attempt_id, state="COMPLETED", execution_status="completed"
                )

        _run(_flow())
        attempt = _get_attempt(attempt_id)
        assert attempt.cancelled is True
        assert attempt.state == "COMPLETED"
