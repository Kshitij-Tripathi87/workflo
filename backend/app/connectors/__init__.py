"""Cortex connector package.

Importing this package auto-registers all available connectors with the
registry (see `app.connectors.registry`). Each connector module handles
its own optional-dependency imports gracefully so that importing this
package never fails if an optional dep (e.g. snowflake-connector-python)
is absent.
"""
from app.connectors.registry import (  # noqa: F401
    register,
    get_connector,
    list_connectors,
    is_registered,
)

# Always available — backed by the in-memory mock store.
from app.connectors.datahub import connector as _datahub_connector  # noqa: F401

# Optional — fails gracefully if deps or config are missing.
try:
    from app.connectors.dbt import connector as _dbt_connector  # noqa: F401
except Exception:  # pragma: no cover - optional dep / no manifest path
    pass

try:
    from app.connectors.snowflake import connector as _snowflake_connector  # noqa: F401
except Exception:  # pragma: no cover - optional dep / no snowflake config
    pass
