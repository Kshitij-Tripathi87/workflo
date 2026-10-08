"""Resolution repository - persistence boundary for Resolution records."""

from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Resolution
from app.models.writeback import WritebackRecord


class ResolutionRepo:
    """Repository for Resolution persistence."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        asset_urn: str,
        *,
        plan_id: str | None = None,
        scenario_type: str | None = None,
        ranked_action: str | None = None,
        severity: int | None = None,
        predicted_effort: int | None = None,
        predicted_benefit: int | None = None,
        confidence: float | None = None,
        artifact_type: str | None = None,
        artifact_body: str | None = None,
        status: str = "open",
        created_by: str = "system",
    ) -> Resolution:
        """Create a new resolution record."""
        record = Resolution(
            asset_urn=asset_urn,
            plan_id=plan_id,
            scenario_type=scenario_type,
            ranked_action=ranked_action,
            severity=severity,
            predicted_effort=predicted_effort,
            predicted_benefit=predicted_benefit,
            confidence=confidence,
            artifact_type=artifact_type,
            artifact_body=artifact_body,
            status=status,
            created_by=created_by,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def get_by_id(self, record_id: UUID) -> Resolution | None:
        result = await self.session.execute(
            select(Resolution).where(Resolution.id == record_id)
        )
        return result.scalar_one_or_none()

    async def list_for_asset(self, asset_urn: str, limit: int = 50) -> list[Resolution]:
        result = await self.session.execute(
            select(Resolution)
            .where(Resolution.asset_urn == asset_urn)
            .order_by(desc(Resolution.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def update_status(self, record_id: UUID, status: str) -> Resolution | None:
        record = await self.get_by_id(record_id)
        if record is None:
            return None
        record.status = status
        await self.session.flush()
        return record

    def to_writeback_record(self, record: Resolution) -> WritebackRecord:
        """Convert a DB Resolution row to a WritebackRecord (API model)."""
        summary = (
            f"Cortex resolution for {record.asset_urn}: "
            f"action={record.ranked_action}, "
            f"severity={record.severity}, "
            f"confidence={record.confidence}"
        )
        return WritebackRecord(
            record_id=str(record.id),
            asset_urn=record.asset_urn,
            status=record.status,  # type: ignore[arg-type]
            summary=summary,
            linked_artifact=None,
            affected_assets=[],
            created_by=record.created_by,
            created_at=record.created_at,
        )
