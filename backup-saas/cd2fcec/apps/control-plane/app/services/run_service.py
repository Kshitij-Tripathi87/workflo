"""Service-layer logic for test run management."""

from typing import Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import utc_now
from app.db.models import TestRun, TestResultRecord
from app.db.queue import run_queue
from workflo_schema import RunSummary


class RunService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_run(self, project_id: str, spec: dict, enqueue: bool = True) -> TestRun:
        """Create a new test run and (legacy path) enqueue it.

        The frozen-contract path (POST /v1/runs) executes the run in-process
        in a background task, so it passes enqueue=False. The legacy queue
        path (worker engine polling) is kept for backwards compatibility.
        """
        record = TestRun(
            project_id=project_id,
            goal=spec.get("goal", "smoke"),
            status="queued",
            spec_json=spec,
        )
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)

        if enqueue:
            # Enqueue with run_id injected
            spec["run_id"] = record.id
            await run_queue.enqueue(spec)

        return record

    async def get_run(self, run_id: str) -> Optional[TestRun]:
        return await self.db.get(TestRun, run_id)

    async def update_status(self, run_id: str, status: str) -> bool:
        stmt = update(TestRun).where(TestRun.id == run_id).values(status=status)
        if status in ("completed", "failed", "cancelled"):
            stmt = stmt.values(finished_at=utc_now())
        await self.db.execute(stmt)
        await self.db.commit()
        return True

    async def append_logs(self, run_id: str, log_line: str) -> None:
        run = await self.db.get(TestRun, run_id)
        if run:
            run.logs = (run.logs or "") + log_line + "\n"
            if run.status == "queued":
                run.status = "running"
            await self.db.commit()

    async def complete_run(self, run_id: str, summary: dict) -> bool:
        run = await self.db.get(TestRun, run_id)
        if not run:
            return False
        run.summary_json = summary
        run.status = summary.get("status", "completed")
        run.finished_at = utc_now()
        await self.db.commit()
        return True

    async def fail_run(self, run_id: str, error: str) -> bool:
        run = await self.db.get(TestRun, run_id)
        if not run:
            return False
        run.status = "failed"
        run.summary_json = {"error": error}
        run.finished_at = utc_now()
        await self.db.commit()
        return True

    async def cancel_run(self, run_id: str) -> bool:
        return await self.update_status(run_id, "cancelled")

    async def list_runs(self, project_id: str | None = None, limit: int = 20) -> list[TestRun]:
        stmt = select(TestRun).order_by(TestRun.started_at.desc()).limit(limit)
        if project_id:
            stmt = stmt.where(TestRun.project_id == project_id)
        result = await self.db.execute(stmt)
        return list(result.scalars())

    async def add_results(self, run_id: str, results: list[dict]) -> None:
        for r in results:
            record = TestResultRecord(
                run_id=run_id,
                nodeid=r.get("nodeid", ""),
                status=r.get("status", "unknown"),
                duration=r.get("duration", 0.0),
                markers=r.get("markers", []),
                soc2_controls=r.get("soc2_controls", []),
                assertion=r.get("assertion", ""),
                error=r.get("error"),
            )
            self.db.add(record)
        await self.db.commit()
