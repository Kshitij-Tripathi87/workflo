"""One-off PostgreSQL schema bootstrap for production deployments.

Run this command with a dedicated schema-owner/migration DSN, never with the
runtime API role:

    DATABASE_URL=postgresql+asyncpg://schema_owner:.../workflo \
      python -m app.db.bootstrap_schema

This bootstraps the SQLAlchemy tables and applies the checked-in RLS policy
file. It is safe to re-run: create_all does not delete existing data and the
RLS script replaces its named policies before recreating them. The API runtime
must then use a distinct non-owner role with neither SUPERUSER nor BYPASSRLS.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy import text

from app.db import models  # noqa: F401 — register all mapped tables
from app.db.base import Base
from app.db.database import engine


async def bootstrap_schema() -> None:
    if engine.dialect.name != "postgresql":
        raise RuntimeError("schema bootstrap is PostgreSQL-only")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    sql_path = Path(__file__).resolve().parents[2] / "db" / "rls" / "001_tenant_rls.sql"
    if not sql_path.is_file():
        raise FileNotFoundError(f"required tenant RLS SQL file missing: {sql_path}")

    sql = sql_path.read_text(encoding="utf-8")
    # asyncpg supports executing a multi-statement SQL script when no bind
    # parameters are passed. Keep BEGIN/COMMIT from the reviewed SQL file so
    # the RLS policy changes are applied atomically.
    async with engine.connect() as conn:
        raw = await conn.get_raw_connection()
        driver = raw.driver_connection
        await driver.execute(sql)

    print("Schema bootstrap complete. Apply the runtime DATABASE_URL only after")
    print("the API role is non-owner, non-superuser, non-BYPASSRLS and has the")
    print("required tenant RLS policies. Production startup verifies those facts.")


async def _main_async() -> None:
    try:
        await bootstrap_schema()
    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(_main_async())


if __name__ == "__main__":
    main()
