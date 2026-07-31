"""SQLAlchemy ORM models for the Cortex database."""

import uuid
from datetime import datetime
from sqlalchemy import (
    String,
    Integer,
    Float,
    Text,
    DateTime,
    Index,
    Boolean,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.session import Base


class Resolution(Base):
    """A persisted resolution / future-search plan outcome."""

    __tablename__ = "resolutions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    asset_urn: Mapped[str] = mapped_column(Text, nullable=False)
    plan_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    scenario_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    ranked_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    predicted_effort: Mapped[int | None] = mapped_column(Integer, nullable=True)
    predicted_benefit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    artifact_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    created_by: Mapped[str] = mapped_column(String(255), nullable=False, default="system")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_resolutions_asset", "asset_urn"),
        Index("idx_resolutions_created", "created_at"),
        Index("idx_resolutions_status", "status"),
    )


class FuturePlanRecord(Base):
    """A persisted future-search plan with all candidates (for history)."""

    __tablename__ = "future_plans"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    plan_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    asset_urn: Mapped[str] = mapped_column(Text, nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False, default="minimize incident risk")
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    candidates: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    ranked_choice: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_future_plans_asset", "asset_urn"),
        Index("idx_future_plans_created", "created_at"),
    )


class AssetState(Base):
    """Last-known state of an asset as observed by the Autopilot.

    The Autopilot writes here whenever it polls a connector so the next
    polling cycle can detect changes by diffing schema_hash / owner / etc.
    """

    __tablename__ = "asset_states"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    asset_urn: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    connector: Mapped[str] = mapped_column(String(64), nullable=False, default="datahub")
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner: Mapped[str | None] = mapped_column(Text, nullable=True)
    schema_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    schema_fields: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    change_frequency: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    past_incidents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        Index("idx_asset_states_urn", "asset_urn"),
        Index("idx_asset_states_connector", "connector"),
        Index("idx_asset_states_last_seen", "last_seen"),
    )


class AutopilotTaskDB(Base):
    """Persistent record of every Autopilot task execution.

    Mirrors AutopilotTask (Pydantic) on disk so the audit log survives
    process restarts and can be queried via the API.
    """

    __tablename__ = "autopilot_tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    task_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    trigger_type: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    asset_urn: Mapped[str] = mapped_column(Text, nullable=False)
    connector: Mapped[str] = mapped_column(String(64), nullable=False, default="datahub")
    complexity: Mapped[str | None] = mapped_column(String(16), nullable=True)
    verdict: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    result_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    steps_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("idx_autopilot_tasks_asset", "asset_urn"),
        Index("idx_autopilot_tasks_status", "status"),
        Index("idx_autopilot_tasks_created", "created_at"),
    )
