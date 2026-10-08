"""Startup validator — fail fast on misconfiguration.

Checks critical paths, URLs, and connector configs at boot. Logs a
warning rather than aborting when a connector is merely unconfigured
(since users may opt in/out of specific connectors), but raises a
critical error for issues that block the application from starting.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterable

from app.core.logging import logger


def _critical(message: str) -> None:
    logger.critical("startup.check_failed", error=message)


def _warn(message: str) -> None:
    logger.warning("startup.check_warning", message=message)


def _ok(message: str) -> None:
    logger.info("startup.check_ok", message=message)


def check_database_url() -> bool:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        _warn("DATABASE_URL unset — running without persistent storage")
        return True
    if not (db_url.startswith("postgres://") or db_url.startswith("postgresql")):
        _critical("DATABASE_URL must be a Postgres URL (postgres://...)")
        return False
    _ok("DATABASE_URL valid")
    return True


def check_dbt_manifest() -> bool:
    path = os.environ.get("CORTEX_DBT_MANIFEST_PATH")
    if not path:
        _warn("CORTEX_DBT_MANIFEST_PATH unset — dbt connector will be skipped")
        return True
    p = Path(path)
    if not p.exists():
        _critical(
            f"CORTEX_DBT_MANIFEST_PATH points to {path} but the file does not exist"
        )
        return False
    _ok(f"dbt manifest found at {path}")
    return True


def check_frontend_url() -> bool:
    url = os.environ.get("FRONTEND_URL", "http://localhost:3000")
    if not (url.startswith("http://") or url.startswith("https://")):
        _critical(f"FRONTEND_URL must be a URL: {url}")
        return False
    _ok(f"FRONTEND_URL valid: {url}")
    return True


def check_snowflake_config() -> bool:
    mock = os.environ.get("CORTEX_SNOWFLAKE_MOCK", "").lower() in ("1", "true", "yes")
    if mock:
        _ok("Snowflake in mock mode")
        return True
    required = ["CORTEX_SNOWFLAKE_ACCOUNT", "CORTEX_SNOWFLAKE_USER", "CORTEX_SNOWFLAKE_DATABASE"]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        _warn(
            "Snowflake credentials incomplete — connector will fail at query time. "
            f"Missing: {', '.join(missing)}"
        )
    else:
        _ok("Snowflake credentials present")
    return True


def run_startup_checks(raise_on_critical: bool = False) -> bool:
    """Run all startup checks.

    Args:
        raise_on_critical: When True, raise RuntimeError on the first
            critical error. Default False (just log).

    Returns:
        True if all critical checks passed, False otherwise.
    """
    checks: Iterable = [
        check_database_url,
        check_dbt_manifest,
        check_frontend_url,
        check_snowflake_config,
    ]

    critical_failures = 0
    for check in checks:
        ok = check()
        if not ok:
            critical_failures += 1

    if critical_failures:
        if raise_on_critical:
            raise RuntimeError(
                f"{critical_failures} critical startup check(s) failed. See logs."
            )
        return False
    return True


if __name__ == "__main__":
    ok = run_startup_checks(raise_on_critical=True)
    sys.exit(0 if ok else 1)
