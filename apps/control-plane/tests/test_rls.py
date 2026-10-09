"""RLS defense-in-depth tests (SOC 2 CC6.1).

The policies live in db/rls/001_tenant_rls.sql and are installed by the
one-off schema bootstrap using a separate schema-owner role. Here we lock
the application contract that feeds them: set_tenant_context binds the
session GUC on Postgres, and is a strict no-op elsewhere — including when
rls_enabled is False (default dev/test posture).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config import settings
from app.db.database import set_tenant_context


def _session(dialect: str):
    session = MagicMock()
    session.bind = MagicMock()
    session.bind.dialect.name = dialect
    session.execute = AsyncMock()
    return session


class TestSetTenantContext:
    async def test_noop_when_disabled(self, monkeypatch):
        monkeypatch.setattr(settings, "rls_enabled", False)
        session = _session("postgresql")
        await set_tenant_context(session, "proj-1")
        session.execute.assert_not_called()

    async def test_noop_on_sqlite_even_when_enabled(self, monkeypatch):
        monkeypatch.setattr(settings, "rls_enabled", True)
        session = _session("sqlite")
        await set_tenant_context(session, "proj-1")
        session.execute.assert_not_called()

    async def test_binds_guc_on_postgres_when_enabled(self, monkeypatch):
        monkeypatch.setattr(settings, "rls_enabled", True)
        session = _session("postgresql")
        await set_tenant_context(session, "proj-42")
        session.execute.assert_awaited_once()
        stmt, params = session.execute.await_args.args
        # Transaction-local (true) is load-bearing: connection pools must
        # never leak one tenant's context into another request.
        assert "set_config('app.current_project_id'" in str(stmt)
        assert ", true)" in str(stmt)
        assert params == {"pid": "proj-42"}

    async def test_empty_project_binds_empty_string(self, monkeypatch):
        """Unset tenant -> NULLIF('') is NULL -> deny-by-default policies."""
        monkeypatch.setattr(settings, "rls_enabled", True)
        session = _session("postgresql")
        await set_tenant_context(session, None)
        _stmt, params = session.execute.await_args.args
        assert params == {"pid": ""}


class TestPolicySqlShipsAndIsReferenced:
    def test_policy_file_exists_and_covers_tenant_tables(self):
        from pathlib import Path

        sql_path = (
            Path(__file__).resolve().parents[1] / "db" / "rls" / "001_tenant_rls.sql"
        )
        assert sql_path.exists(), "RLS policy SQL is missing"
        sql = sql_path.read_text(encoding="utf-8")
        for table in ("projects", "api_keys", "test_runs",
                      "test_results", "artifacts", "audit_events"):
            assert f"ALTER TABLE {table}" in sql
            assert f"tenant_isolation_{table}" in sql or (
                table == "audit_events" and "tenant_isolation_audit_" in sql
            )
        assert "FORCE ROW LEVEL SECURITY" in sql
        assert "current_setting('app.current_project_id', true)" in sql
