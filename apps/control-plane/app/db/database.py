"""SQLAlchemy async database session for the Control Plane.

Supports PostgreSQL (via asyncpg) and SQLite (via aiosqlite) for zero-config dev.
"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
from app.core.config import settings

# Auto-detect: if DATABASE_URL starts with postgresql, use asyncpg; else aiosqlite
db_url = settings.database_url
if db_url.startswith("postgresql"):
    connect_args = {}
    engine = create_async_engine(db_url, echo=False, pool_size=10, max_overflow=20)
else:
    # SQLite (default for dev/test).
    db_url = db_url.replace("postgresql+asyncpg", "sqlite+aiosqlite")
    if ":memory:" in db_url:
        # In-memory SQLite DBs are PER-CONNECTION: with a normal pool each
        # pooled connection would see its own private empty database, so a
        # write committed on one connection would be invisible to reads on
        # another (background run tasks routinely hit this). StaticPool
        # shares ONE connection across all sessions — required for :memory:.
        engine = create_async_engine(
            db_url, echo=False, poolclass=StaticPool
        )
    else:
        engine = create_async_engine(db_url, echo=False)

async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with async_session_factory() as session:
        yield session


async def set_tenant_context(session: AsyncSession, project_id: str | None) -> None:
    """Bind the RLS tenant GUC to this session's transaction (Postgres only).

    Defense in depth (SOC 2 CC6.1): the application scopes every query by
    project_id already; when rls_enabled is set and the SQL in
    db/rls/001_tenant_rls.sql is applied, the DATABASE also refuses
    cross-tenant rows, so an application-layer bug degrades to a denial.

    Transaction-local (set_config third arg = true): the binding resets on
    commit, so pooled connections cannot leak one tenant's context into
    another request. No-op on SQLite and when rls_enabled is False.
    """
    if not settings.rls_enabled:
        return
    bind = session.bind
    if bind is None or bind.dialect.name != "postgresql":
        return
    from sqlalchemy import text

    await session.execute(
        text("SELECT set_config('app.current_project_id', :pid, true)"),
        {"pid": project_id or ""},
    )


# These are the tables covered by apps/control-plane/db/rls/001_tenant_rls.sql.
# The policy names are checked too: ENABLE ROW LEVEL SECURITY alone is not enough
# if a required table has no policy and the effective behavior is not the intended
# tenant contract.
_PRODUCTION_RLS_POLICIES = {
    ("projects", "tenant_isolation_projects"),
    ("api_keys", "tenant_isolation_api_keys"),
    ("test_runs", "tenant_isolation_test_runs"),
    ("test_results", "tenant_isolation_test_results"),
    ("artifacts", "tenant_isolation_artifacts"),
    ("audit_events", "tenant_isolation_audit_select"),
    ("audit_events", "tenant_isolation_audit_insert"),
}


async def set_api_key_lookup_mode(session: AsyncSession, enabled: bool) -> None:
    """Temporarily allow the API-key authenticator to find a key before its
    project ID is known.

    The setting is transaction-local and is used only around the API-key
    SELECT. The authenticator must switch it off immediately after
    materializing the rows, then bind the candidate project before reading
    its DEK or updating last_used. This is the narrow authentication bootstrap
    exception to the normal project-scoped api_keys policy.
    """
    if not settings.rls_enabled:
        return
    bind = session.bind
    if bind is None or bind.dialect.name != "postgresql":
        return
    from sqlalchemy import text

    await session.execute(
        text("SELECT set_config('app.api_key_lookup', :mode, true)"),
        {"mode": "on" if enabled else "off"},
    )


async def verify_production_database() -> dict:
    """Fail closed unless PostgreSQL RLS is enabled, forced, and policy-backed.

    This check intentionally requires a non-superuser, non-BYPASSRLS runtime
    role that does not own the protected tables. The setup/migration role must
    be separate. Production never treats the RLS_ENABLED flag by itself as
    proof that the database was actually provisioned safely.
    """
    from sqlalchemy import text

    if engine.dialect.name != "postgresql":
        raise RuntimeError(
            "production requires PostgreSQL; SQLite and other dialects are development-only"
        )

    async with engine.connect() as conn:
        role_result = await conn.execute(text(
            "SELECT current_user, r.rolsuper, r.rolbypassrls "
            "FROM pg_roles AS r WHERE r.rolname = current_user"
        ))
        role = role_result.first()
        if role is None:
            raise RuntimeError("could not verify the PostgreSQL runtime role")
        runtime_role = str(role[0])
        if bool(role[1]) or bool(role[2]):
            raise RuntimeError(
                "production database role must not be SUPERUSER or BYPASSRLS"
            )

        table_result = await conn.execute(text(
            "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, "
            "pg_get_userbyid(c.relowner) "
            "FROM pg_class AS c "
            "JOIN pg_namespace AS n ON n.oid = c.relnamespace "
            "WHERE n.nspname = current_schema() AND c.relkind = 'r' "
            "AND c.relname IN "
            "('projects', 'api_keys', 'test_runs', 'test_results', 'artifacts', 'audit_events')"
        ))
        table_rows = {
            str(row[0]): (bool(row[1]), bool(row[2]), str(row[3]))
            for row in table_result.all()
        }
        required_tables = {
            "projects", "api_keys", "test_runs", "test_results", "artifacts", "audit_events"
        }
        missing_tables = sorted(required_tables - set(table_rows))
        invalid_tables = sorted(
            name for name, (enabled, forced, owner) in table_rows.items()
            if not enabled or not forced or owner == runtime_role
        )
        if missing_tables or invalid_tables:
            problems = []
            if missing_tables:
                problems.append("missing tables: " + ", ".join(missing_tables))
            if invalid_tables:
                problems.append(
                    "RLS/FORCE RLS must be enabled and tables must be owned by a separate role: "
                    + ", ".join(invalid_tables)
                )
            raise RuntimeError("production database RLS validation failed (" + "; ".join(problems) + ")")

        policy_result = await conn.execute(text(
            "SELECT tablename, policyname FROM pg_policies "
            "WHERE schemaname = current_schema()"
        ))
        present_policies = {(str(row[0]), str(row[1])) for row in policy_result.all()}
        missing_policies = sorted(_PRODUCTION_RLS_POLICIES - present_policies)
        if missing_policies:
            formatted = ", ".join(f"{table}/{policy}" for table, policy in missing_policies)
            raise RuntimeError("production database lacks required tenant RLS policies: " + formatted)

    return {
        "status": "verified",
        "runtime_role": runtime_role,
        "rls_tables": sorted(required_tables),
        "rls_policies": len(_PRODUCTION_RLS_POLICIES),
    }


async def init_db():
    """Create all tables. Used for dev/testing without Alembic."""
    from app.db.base import Base
    from app.db import models  # noqa: F401 - register models
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_db():
    """Drop all tables. Used for test cleanup."""
    from app.db.base import Base
    from app.db import models  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
