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
