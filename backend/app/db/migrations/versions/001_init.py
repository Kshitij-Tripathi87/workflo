"""Initial schema: resolutions and future_plans.

Revision ID: 001
Revises: None
Create date: 2026-07-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "resolutions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("asset_urn", sa.Text(), nullable=False),
        sa.Column("plan_id", sa.Text(), nullable=True),
        sa.Column("scenario_type", sa.Text(), nullable=True),
        sa.Column("ranked_action", sa.Text(), nullable=True),
        sa.Column("severity", sa.Integer(), nullable=True),
        sa.Column("predicted_effort", sa.Integer(), nullable=True),
        sa.Column("predicted_benefit", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("artifact_type", sa.Text(), nullable=True),
        sa.Column("artifact_body", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("created_by", sa.String(length=255), nullable=False, server_default="system"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_resolutions_asset", "resolutions", ["asset_urn"])
    op.create_index("idx_resolutions_created", "resolutions", [sa.text("created_at DESC")])
    op.create_index("idx_resolutions_status", "resolutions", ["status"])

    op.create_table(
        "future_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("plan_id", sa.Text(), nullable=False, unique=True),
        sa.Column("asset_urn", sa.Text(), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False, server_default="minimize incident risk"),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("explanation", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("candidates", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("ranked_choice", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_future_plans_asset", "future_plans", ["asset_urn"])
    op.create_index("idx_future_plans_created", "future_plans", [sa.text("created_at DESC")])


def downgrade() -> None:
    op.drop_index("idx_future_plans_created", table_name="future_plans")
    op.drop_index("idx_future_plans_asset", table_name="future_plans")
    op.drop_table("future_plans")
    op.drop_index("idx_resolutions_status", table_name="resolutions")
    op.drop_index("idx_resolutions_created", table_name="resolutions")
    op.drop_index("idx_resolutions_asset", table_name="resolutions")
    op.drop_table("resolutions")
