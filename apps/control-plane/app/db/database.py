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
