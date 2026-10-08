"""Database session management.

Provides an async SQLAlchemy engine and session factory. The engine is
created lazily only when DATABASE_URL is configured. When DATABASE_URL is
None (mock/dev mode without a DB), the session functions are no-ops.
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.settings import settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""
    pass


_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def get_engine() -> Optional[AsyncEngine]:
    """Lazily create and return the async engine. None when no DATABASE_URL."""
    global _engine
    if _engine is None and settings.DATABASE_URL:
        url = str(settings.DATABASE_URL)
        # SQLAlchemy async needs asyncpg driver
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)

        _engine = create_async_engine(
            url,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            echo=settings.DB_ECHO,
        )
    return _engine


def get_session_factory() -> Optional[async_sessionmaker[AsyncSession]]:
    """Lazily create and return the session factory. None when no DB."""
    global _session_factory
    if _session_factory is None and settings.DATABASE_URL:
        engine = get_engine()
        if engine is not None:
            _session_factory = async_sessionmaker(
                engine, expire_on_commit=False, class_=AsyncSession
            )
    return _session_factory


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Async context manager that yields a DB session.

    Usage:
        async with get_session() as session:
            ...

    Yields None when no database is configured (mock mode).
    """
    factory = get_session_factory()
    if factory is None:
        # No DB configured - this is only reached by code that explicitly
        # wants a session. Callers should check settings.DATABASE_URL first.
        raise RuntimeError("DATABASE_URL not configured")
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def close_engine() -> None:
    """Dispose of the engine pool. Call on application shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
