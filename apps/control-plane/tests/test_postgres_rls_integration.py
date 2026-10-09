"""Real PostgreSQL integration test for forced RLS and API-key authentication.

This test is skipped only when WORKFLO_TEST_POSTGRES_URL is not configured.
The authoritative Control Plane CI workflow provisions an isolated PostgreSQL
service, installs the schema/policies, grants a non-owner runtime role, and
sets the URL so this test must run there.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import envelope
from app.core.config import settings
from app.db import database
from app.db.models import ApiKey
from app.services.api_key_service import ApiKeyService


POSTGRES_URL = os.environ.get("WORKFLO_TEST_POSTGRES_URL", "").strip()
pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="requires WORKFLO_TEST_POSTGRES_URL; CI provisions the authoritative PostgreSQL service",
)


@pytest.mark.asyncio
async def test_real_postgres_forced_rls_and_api_key_auth(monkeypatch):
    """A real Postgres role can authenticate a key without retaining global row access."""
    monkeypatch.setattr(settings, "rls_enabled", True)
    monkeypatch.setattr(settings, "master_kek_hex", "a" * 64)
    monkeypatch.setattr(settings, "kek_provider", "static")
    envelope.reset_provider()

    runtime_engine = create_async_engine(POSTGRES_URL, pool_size=2, max_overflow=0)
    sessions = async_sessionmaker(runtime_engine, expire_on_commit=False)
    monkeypatch.setattr(database, "engine", runtime_engine)

    try:
        db_check = await database.verify_production_database()
        assert db_check["status"] == "verified"
        assert db_check["runtime_role"] == "workflo_runtime"
        assert db_check["rls_policies"] == 8

        # Create two tenants as the normal, non-owner runtime role. The app
        # must bind the target project before writing under FORCE RLS.
        async with sessions() as session:
            service = ApiKeyService(session)
            key_a, record_a = await service.create_key(
                "p4-tenant-a", label="tenant-a", scopes=["run_tests"]
            )
            key_b, record_b = await service.create_key(
                "p4-tenant-b", label="tenant-b", scopes=["run_tests"]
            )
            assert record_a.project_id == "p4-tenant-a"
            assert record_b.project_id == "p4-tenant-b"

        # The dedicated API-key SELECT policy is enabled only for auth. The
        # service must turn it off, bind each candidate project for decryption,
        # verify the secret, then bind the matched project before last_used.
        async with sessions() as session:
            await database.set_api_key_lookup_mode(session, enabled=True)
            record = await ApiKeyService(session).validate_key(key_a)
            assert record is not None
            assert record.id == record_a.id
            assert record.project_id == "p4-tenant-a"

        async with sessions() as session:
            result = await session.execute(select(ApiKey))
            visible_without_tenant = list(result.scalars())
            assert visible_without_tenant == [], (
                "API keys must remain invisible outside the authentication lookup "
                "and without an explicit project context"
            )

        async with sessions() as session:
            await database.set_tenant_context(session, "p4-tenant-a")
            result = await session.execute(select(ApiKey))
            visible_for_a = list(result.scalars())
            assert [row.project_id for row in visible_for_a] == ["p4-tenant-a"]

        async with sessions() as session:
            await database.set_tenant_context(session, "p4-tenant-b")
            result = await session.execute(select(ApiKey))
            visible_for_b = list(result.scalars())
            assert [row.project_id for row in visible_for_b] == ["p4-tenant-b"]

        async with sessions() as session:
            await database.set_api_key_lookup_mode(session, enabled=True)
            invalid = await ApiKeyService(session).validate_key("wfl_invalid_p4_test_key")
            assert invalid is None
    finally:
        envelope.reset_provider()
        await runtime_engine.dispose()
