"""dbt connector configuration sourced from environment variables."""
import os
from pathlib import Path
from typing import Optional


def dbt_config_from_env() -> dict:
    """Read dbt connector configuration from environment variables.

    Required:
        CORTEX_DBT_MANIFEST_PATH  Path to manifest.json (absolute or
                                  relative to CORTEX_DBT_PROJECT_DIR).

    Optional:
        CORTEX_DBT_CATALOG_PATH   Path to catalog.json. If absent,
                                  column types are unavailable.
        CORTEX_DBT_PROJECT_DIR    Base dir for relative paths. Defaults
                                  to current working directory.
    """
    project_dir = Path(os.environ.get("CORTEX_DBT_PROJECT_DIR", ".")).resolve()
    manifest_path = os.environ.get("CORTEX_DBT_MANIFEST_PATH")
    catalog_path = os.environ.get("CORTEX_DBT_CATALOG_PATH")

    manifest = _resolve(manifest_path, project_dir) if manifest_path else None
    catalog = _resolve(catalog_path, project_dir) if catalog_path else None

    return {
        "manifest_path": manifest,
        "catalog_path": catalog,
        "project_dir": project_dir,
    }


def _resolve(path: str, base: Path) -> Optional[Path]:
    """Resolve a path relative to base, returning None if not found."""
    p = Path(path)
    if not p.is_absolute():
        p = base / p
    p = p.resolve()
    return p if p.exists() else None
