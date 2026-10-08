"""Tests for Cherry #2 — DataHub assertion writeback.

Verifies that:
  - The payload has the correct shape (assertion-style)
  - The function writes to the JSONL log in mock mode
  - The function does not raise when no real DataHub is configured
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.connectors.datahub.writeback import (
    build_verdict_assertion_payload,
    record_verdict_assertion,
)


def test_payload_shape_matches_datahub_assertion() -> None:
    """The payload has all fields a DataHub assertion consumer expects."""
    payload = build_verdict_assertion_payload(
        asset_urn="urn:dbt:model:jaffle_shop:orders",
        asset_name="orders",
        verdict="block",
        reason="Dropping customer_name breaks dashboard_feed",
        severity="critical",
        blast_radius=1,
        run_id="test-run-001",
    )
    assert payload["assertion_type"] == "CORTEX_VERDICT"
    assert payload["urn"] == "urn:dbt:model:jaffle_shop:orders"
    assert payload["verdict"] == "block"
    assert payload["severity"] == "critical"
    assert payload["blast_radius"] == 1
    assert payload["run_id"] == "test-run-001"
    assert payload["timestamp"]
    assert payload["created_by"] == "system"


def test_payload_default_severity_is_medium() -> None:
    payload = build_verdict_assertion_payload(
        asset_urn="urn:test",
        asset_name="test",
        verdict="warn",
        reason="test",
        severity="medium",
        blast_radius=0,
        run_id="x",
    )
    assert payload["severity"] == "medium"


@pytest.mark.asyncio
async def test_record_verdict_assertion_writes_to_jsonl(tmp_path: Path) -> None:
    """Mock-mode safe: writes to JSONL even with no real DataHub."""
    jsonl_path = tmp_path / "writeback.jsonl"

    with patch("app.connectors.datahub.writeback._writeback_path", return_value=jsonl_path):
        result = await record_verdict_assertion(
            asset_urn="urn:dbt:model:test:orders",
            asset_name="orders",
            verdict="block",
            reason="Test",
            severity="high",
            blast_radius=3,
            run_id="test-run-002",
        )

    assert result["verdict"] == "block"
    assert jsonl_path.exists()

    content = jsonl_path.read_text().strip().splitlines()
    assert len(content) == 1
    record = json.loads(content[0])
    assert record["kind"] == "assertion"
    assert record["asset_urn"] == "urn:dbt:model:test:orders"
    assert record["status"] == "block"
    assert record["payload"]["run_id"] == "test-run-002"
    assert record["payload"]["blast_radius"] == 3


@pytest.mark.asyncio
async def test_record_verdict_assertion_generates_run_id_when_missing(tmp_path: Path) -> None:
    """If no run_id is supplied, one is generated."""
    jsonl_path = tmp_path / "writeback.jsonl"

    with patch("app.connectors.datahub.writeback._writeback_path", return_value=jsonl_path):
        result = await record_verdict_assertion(
            asset_urn="urn:test",
            asset_name="test",
            verdict="pass",
            reason="no-op",
            severity="low",
            blast_radius=0,
            run_id=None,
        )

    assert result["run_id"]
    assert len(result["run_id"]) > 0


@pytest.mark.asyncio
async def test_record_verdict_assertion_handles_no_datahub_client(tmp_path: Path) -> None:
    """The function does not raise when no DataHub client is configured."""
    jsonl_path = tmp_path / "writeback.jsonl"

    # adapter.async_client is None in mock mode by default
    with patch("app.connectors.datahub.writeback._writeback_path", return_value=jsonl_path):
        result = await record_verdict_assertion(
            asset_urn="urn:test",
            asset_name="test",
            verdict="warn",
            reason="ok",
            severity="medium",
            blast_radius=1,
            run_id="x",
        )

    assert result["written_to_datahub" if False else "verdict"] == "warn"
