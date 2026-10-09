"""Production database startup verification: runtime must prove RLS is live."""

from types import SimpleNamespace

import pytest

from app.db import database


RLS_TABLES = (
    "projects", "api_keys", "test_runs", "test_results", "artifacts", "audit_events",
)
RLS_POLICIES = (
    ("projects", "tenant_isolation_projects"),
    ("api_keys", "tenant_isolation_api_keys"),
    ("api_keys", "api_key_auth_lookup"),
    ("test_runs", "tenant_isolation_test_runs"),
    ("test_results", "tenant_isolation_test_results"),
    ("artifacts", "tenant_isolation_artifacts"),
    ("audit_events", "tenant_isolation_audit_select"),
    ("audit_events", "tenant_isolation_audit_insert"),
)


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)


class FakeConnection:
    def __init__(self, *, role=None, tables=None, policies=None):
        self.role = role or ("workflo_runtime", False, False)
        self.tables = tables or [
            (name, True, True, "workflo_schema_owner") for name in RLS_TABLES
        ]
        self.policies = policies if policies is not None else list(RLS_POLICIES)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement):
        sql = str(statement)
        if "FROM pg_roles" in sql:
            return FakeResult([self.role])
        if "FROM pg_class" in sql:
            return FakeResult(self.tables)
        if "FROM pg_policies" in sql:
            return FakeResult(self.policies)
        raise AssertionError(f"Unexpected query in production DB guard: {sql}")


class FakeEngine:
    def __init__(self, dialect="postgresql", **kwargs):
        self.dialect = SimpleNamespace(name=dialect)
        self.connection = FakeConnection(**kwargs)

    def connect(self):
        return self.connection


@pytest.mark.asyncio
async def test_production_database_guard_accepts_fully_protected_schema(monkeypatch):
    monkeypatch.setattr(database, "engine", FakeEngine())
    result = await database.verify_production_database()
    assert result["status"] == "verified"
    assert result["runtime_role"] == "workflo_runtime"
    assert result["rls_policies"] == 8
    assert set(result["rls_tables"]) == set(RLS_TABLES)


@pytest.mark.asyncio
async def test_production_database_guard_rejects_non_postgres(monkeypatch):
    monkeypatch.setattr(database, "engine", FakeEngine(dialect="sqlite"))
    with pytest.raises(RuntimeError, match="requires PostgreSQL"):
        await database.verify_production_database()


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [
    ("workflo_runtime", True, False),
    ("workflo_runtime", False, True),
])
async def test_production_database_guard_rejects_privileged_runtime_role(monkeypatch, role):
    monkeypatch.setattr(database, "engine", FakeEngine(role=role))
    with pytest.raises(RuntimeError, match="SUPERUSER or BYPASSRLS"):
        await database.verify_production_database()


@pytest.mark.asyncio
async def test_production_database_guard_rejects_unenabled_or_unforced_rls(monkeypatch):
    tables = [
        (name, name != "test_runs", name != "artifacts", "workflo_schema_owner")
        for name in RLS_TABLES
    ]
    monkeypatch.setattr(database, "engine", FakeEngine(tables=tables))
    with pytest.raises(RuntimeError, match="RLS/FORCE RLS"):
        await database.verify_production_database()


@pytest.mark.asyncio
async def test_production_database_guard_rejects_runtime_as_table_owner(monkeypatch):
    tables = [
        (name, True, True, "workflo_runtime" if name == "projects" else "workflo_schema_owner")
        for name in RLS_TABLES
    ]
    monkeypatch.setattr(database, "engine", FakeEngine(tables=tables))
    with pytest.raises(RuntimeError, match="separate role"):
        await database.verify_production_database()


@pytest.mark.asyncio
async def test_production_database_guard_rejects_missing_policy(monkeypatch):
    monkeypatch.setattr(
        database,
        "engine",
        FakeEngine(policies=[p for p in RLS_POLICIES if p != ("test_runs", "tenant_isolation_test_runs")]),
    )
    with pytest.raises(RuntimeError, match="lacks required tenant RLS policies"):
        await database.verify_production_database()
