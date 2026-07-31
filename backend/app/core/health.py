"""Health check module — verifies backend + connectors are alive.

Returns a structured status report:
  - overall status (ok / degraded / down)
  - per-connector status (connected / mock / unreachable / not_configured)
  - uptime, version, env

The Docker healthcheck uses /health (cheap). /health/detailed is for
operators and dashboards.
"""
from __future__ import annotations

import time
from pathlib import Path

from app.core.settings import settings
from app.core.snapshot_cache import get_snapshot_cache


_START_TIME = time.monotonic()


def _uptime_seconds() -> float:
    return time.monotonic() - _START_TIME


def _check_dbt() -> dict:
    """Inspect the configured dbt manifest path."""
    from app.connectors.dbt.config import dbt_config_from_env

    cfg = dbt_config_from_env()
    path = cfg.get("manifest_path")
    if not path:
        return {"status": "not_configured", "message": "CORTEX_DBT_MANIFEST_PATH unset"}
    p = Path(path)
    if not p.exists():
        return {"status": "unreachable", "message": f"manifest not found at {path}"}
    stat = p.stat()
    return {
        "status": "connected",
        "path": str(p),
        "size_bytes": stat.st_size,
        "modified_at": int(stat.st_mtime),
    }


def _check_snowflake() -> dict:
    """Snowflake is mocked or live depending on env."""
    from app.connectors.snowflake.config import snowflake_config_from_env

    cfg = snowflake_config_from_env()
    if cfg.mock_mode:
        return {"status": "mock", "message": "CORTEX_SNOWFLAKE_MOCK=true"}
    if not cfg.account or not cfg.user or not cfg.database:
        return {
            "status": "not_configured",
            "message": "missing CORTEX_SNOWFLAKE_ACCOUNT/USER/DATABASE",
        }
    return {
        "status": "configured",
        "account": cfg.account,
        "database": cfg.database,
        "schema": cfg.schema,
    }


def _check_datahub() -> dict:
    """DataHub is mocked or live."""
    if settings.USE_MOCK_DATAHUB:
        return {"status": "mock", "message": "USE_MOCK_DATAHUB=true"}
    if not settings.DATAHUB_BASE_URL:
        return {"status": "not_configured", "message": "DATAHUB_BASE_URL unset"}
    return {"status": "configured", "base_url": str(settings.DATAHUB_BASE_URL)}


def get_detailed_health() -> dict:
    """Build a structured report describing every subsystem."""
    connectors = {
        "dbt": _check_dbt(),
        "snowflake": _check_snowflake(),
        "datahub": _check_datahub(),
    }

    statuses = {name: info.get("status") for name, info in connectors.items()}
    if any(s == "unreachable" for s in statuses.values()):
        overall = "degraded"
    else:
        overall = "ok"

    return {
        "status": overall,
        "version": "0.3.0",
        "name": "Cortex Autopilot",
        "env": settings.ENV,
        "uptime_seconds": round(_uptime_seconds(), 2),
        "connectors": connectors,
        "cache": get_snapshot_cache().stats(),
    }
