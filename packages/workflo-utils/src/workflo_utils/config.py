"""Config file loading and saving for the workflo platform."""

import os
import yaml
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_DIR = Path.home() / ".workflo"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.yaml"


def load_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or DEFAULT_CONFIG_FILE
    if not config_path.exists():
        return {}
    with open(config_path) as f:
        return yaml.safe_load(f) or {}


def save_config(config: dict[str, Any], path: Path | None = None) -> None:
    config_path = path or DEFAULT_CONFIG_FILE
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w") as f:
        yaml.safe_dump(config, f, default_flow_style=False)


def get_config_value(key: str, default: Any = None, path: Path | None = None) -> Any:
    config = load_config(path)
    parts = key.split(".")
    value = config
    for part in parts:
        if not isinstance(value, dict):
            return default
        value = value.get(part)
        if value is None:
            return default
    return value if value is not None else default
