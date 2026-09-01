"""Shared test fixtures for the Control Plane backend.

Uses synchronous TestClient for HTTP calls, with async DB setup via asyncio.run().
Patches the module-level engine + session_factory between tests for isolation.
"""

import asyncio
import os

# Configure test DB BEFORE importing app modules
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "")

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from fastapi.testclient import TestClient

from app.main import create_app
from app.db import database
from app.db.base import Base
from app.db import models  # noqa: F401 - register ORM models


@pytest.fixture(autouse=True, scope="function")
def setup_db(tmp_path):
    """Create a fresh SQLite DB for each test.

    Uses a per-test FILE, not :memory:. Each TestClient runs the app on its
    own event loop, and aiosqlite/:memory: databases are PER-CONNECTION —
    a write committed by the background run task can land on a connection
    (and loop) that the polling GET handler never sees, making completion
    checks intermittently fail ("never reached terminal state"). A file
    shares committed data across all connections and loops.
    """
    db_path = tmp_path / "test.db"
    new_engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path.as_posix()}",
        echo=False,
    )
    new_factory = async_sessionmaker(
        new_engine, class_=AsyncSession, expire_on_commit=False
    )

    # Patch module-level globals (functions read these at call time via globals())
    database.engine = new_engine
    database.async_session_factory = new_factory

    # Create all tables on the new engine
    def _create_sync(sync_conn):
        Base.metadata.create_all(sync_conn)

    async def _create_async():
        async with new_engine.begin() as conn:
            await conn.run_sync(_create_sync)

    asyncio.set_event_loop(asyncio.new_event_loop())  # Fresh loop
    asyncio.run(_create_async())

    yield

    # Cleanup: drop all tables + dispose engine. Best-effort: a background
    # run task cancelled by TestClient shutdown can leave a checked-out
    # connection holding a lock ("database is locked") — the temp file is
    # deleted with tmp_path regardless, so a failed DROP is harmless.
    def _drop_sync(sync_conn):
        Base.metadata.drop_all(sync_conn)

    async def _drop_async():
        from sqlalchemy.exc import OperationalError

        try:
            async with new_engine.begin() as conn:
                await conn.run_sync(_drop_sync)
        except OperationalError:
            pass
        await new_engine.dispose()

    asyncio.run(_drop_async())


@pytest.fixture
def client():
    """Synchronous HTTP client for testing FastAPI endpoints."""
    app = create_app()
    # Disable lifespan so we control DB setup ourselves (avoid starlette warnings/errors)
    # Note: lifespan is normally only triggered when using TestClient as context manager
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(autouse=True)
def _no_real_executor(monkeypatch):
    """Keep tests hermetic: no test may invoke the real SandboxExecutor.

    The real executor does live `git clone` (network) and `docker` calls —
    any test that POSTs /v1/runs would otherwise spawn a real background
    run whose to_thread work outlives the test (its in-memory DB and event
    loop are torn down underneath it), which makes later tests flaky.

    The fake is deterministic and instant; execution-outcome tests override
    it with their own `patch("workflo_executor.SandboxExecutor")` for
    the duration of their polling loop (inner patches win over this one).
    """
    from unittest.mock import MagicMock

    fake = MagicMock()
    fake.run.return_value.to_json.return_value = (
        '{"receipt": true, "sandbox_id": "sb-fake"}'
    )
    monkeypatch.setattr("workflo_executor.SandboxExecutor", fake)
    yield
