"""Configuration management for workflo CLI.

Stores settings in ~/.workflo/config.yaml. Supports dot-notation keys
for nested values (e.g. `llm.base_url`, `sandbox.timeout`).

Usage:
    workflo config init          # Create default config file
    workflo config set KEY VALUE # Set a config value
    workflo config get KEY       # Get a config value
    workflo config list          # List all config values
    workflo config path          # Print the config file path

LLM settings are PLACEHOLDERS — the model integration is post-demo work.
The keys exist so the deep-test / aggressive-test pipeline can read them
from config and inject them into the sandbox environment.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Optional

import click

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]


# Where the config lives — respects WORKFLO_CONFIG_DIR for test isolation.
def _config_dir() -> Path:
    override = os.environ.get("WORKFLO_CONFIG_DIR")
    if override:
        return Path(override)
    return Path.home() / ".workflo"


def _config_path() -> Path:
    return _config_dir() / "config.yaml"


# Default config template — all LLM values are placeholders.
_DEFAULT_CONFIG: dict[str, Any] = {
    "llm": {
        "base_url": "http://localhost:11434/v1",
        "api_key": "placeholder-key-configure-me",
        "model": "qwen2.5-coder:7b",
    },
    "sandbox": {
        "timeout": 600,
        "memory": 2048,
        "cpu": 2.0,
    },
}

# Valid top-level sections and their allowed keys (for validation).
_VALID_KEYS: dict[str, set[str]] = {
    "llm": {"base_url", "api_key", "model"},
    "sandbox": {"timeout", "memory", "cpu"},
}

# Keys that hold secrets — redacted in `config list` output.
_SECRET_KEYS = {"llm.api_key"}

# Size limit for config file reads (defense in depth).
_MAX_CONFIG_BYTES = 1024 * 1024  # 1 MB


def _validate_dot_key(key: str) -> tuple[str, str]:
    """Parse and validate a dot-notation key like 'llm.base_url'.

    Returns (section, field). Raises click.BadParameter on invalid key.
    """
    key = key.strip()
    if not key:
        raise click.BadParameter("Config key must not be empty")

    parts = key.split(".")
    if len(parts) != 2:
        raise click.BadParameter(
            f"Config key must be SECTION.FIELD (e.g. llm.base_url), got {key!r}"
        )

    section, field = parts
    if section not in _VALID_KEYS:
        raise click.BadParameter(
            f"Unknown config section: {section!r}. "
            f"Valid sections: {sorted(_VALID_KEYS.keys())}"
        )
    if field not in _VALID_KEYS[section]:
        raise click.BadParameter(
            f"Unknown config key: {key!r}. "
            f"Valid keys in [{section}]: {sorted(_VALID_KEYS[section])}"
        )
    return section, field


def _coerce_value(key: str, value: str) -> Any:
    """Coerce a string CLI value to the appropriate Python type.

    Numbers stay numbers in the YAML file instead of being quoted strings.
    """
    # Sandbox numeric fields
    if key in ("sandbox.timeout", "sandbox.memory"):
        try:
            return int(value)
        except ValueError:
            raise click.BadParameter(f"{key} must be an integer, got {value!r}")
    if key == "sandbox.cpu":
        try:
            return float(value)
        except ValueError:
            raise click.BadParameter(f"{key} must be a number, got {value!r}")
    return value


def _load_config() -> dict[str, Any]:
    """Load config from disk, or return empty dict if file doesn't exist."""
    path = _config_path()
    if not path.exists():
        return {}

    if yaml is None:
        raise click.ClickException(
            "PyYAML is required for config. Install with: pip install pyyaml"
        )

    size = path.stat().st_size
    if size > _MAX_CONFIG_BYTES:
        raise click.ClickException(
            f"Config file too large: {size} bytes (max {_MAX_CONFIG_BYTES})"
        )

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise click.ClickException(f"Cannot read config: {e}")

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise click.ClickException(f"Invalid YAML in config: {e}")

    if data is None:
        return {}
    if not isinstance(data, dict):
        raise click.ClickException(
            f"Config root must be a mapping, got {type(data).__name__}"
        )
    return data


def _save_config(data: dict[str, Any]) -> None:
    """Write config to disk. Creates the directory if needed."""
    if yaml is None:
        raise click.ClickException(
            "PyYAML is required for config. Install with: pip install pyyaml"
        )

    config_dir = _config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)

    path = _config_path()
    try:
        text = yaml.dump(data, default_flow_style=False, sort_keys=True)
        path.write_text(text, encoding="utf-8")
    except OSError as e:
        raise click.ClickException(f"Cannot write config: {e}")


def _redact(key: str, value: Any) -> str:
    """Redact secret values for display."""
    if key in _SECRET_KEYS and isinstance(value, str) and len(value) > 4:
        return value[:4] + "****"
    return str(value)


def load_llm_settings() -> dict[str, Optional[str]]:
    """Load LLM settings from config. Returns dict with base_url, api_key, model.

    Used by the run command to inject LLM env vars into deep-test sandbox specs.
    Returns empty strings for missing keys — never raises.
    """
    try:
        cfg = _load_config()
    except click.ClickException:
        return {"base_url": "", "api_key": "", "model": ""}

    llm = cfg.get("llm", {})
    if not isinstance(llm, dict):
        return {"base_url": "", "api_key": "", "model": ""}

    return {
        "base_url": str(llm.get("base_url", "")),
        "api_key": str(llm.get("api_key", "")),
        "model": str(llm.get("model", "")),
    }


# ---------------------------------------------------------------------------
# Click command group
# ---------------------------------------------------------------------------

@click.group(name="config")
def config_group():
    """Manage workflo configuration.

    Settings are stored in ~/.workflo/config.yaml. Use dot-notation keys:

      workflo config set llm.base_url http://localhost:11434/v1
      workflo config set llm.api_key sk-xxxxx
      workflo config set sandbox.timeout 900

    LLM settings are placeholders for the deep-test pipeline integration
    (post-demo). The keys exist so the sandbox environment can be configured.
    """


@config_group.command(name="init")
@click.option("--force", is_flag=True, help="Overwrite existing config file")
def config_init(force):
    """Create a default config file at ~/.workflo/config.yaml."""
    path = _config_path()
    if path.exists() and not force:
        click.echo(f"Config already exists at {path}", err=True)
        click.echo("Use --force to overwrite.", err=True)
        raise SystemExit(1)

    _save_config(_DEFAULT_CONFIG)
    click.echo(f"Config created at {path}")
    click.echo("Edit it or use `workflo config set` to update values.")


@config_group.command(name="set")
@click.argument("key")
@click.argument("value")
def config_set(key, value):
    """Set a config value. KEY uses dot-notation: SECTION.FIELD.

    Examples:
      workflo config set llm.base_url http://localhost:11434/v1
      workflo config set llm.api_key sk-xxxxx
      workflo config set sandbox.timeout 900
    """
    section, field = _validate_dot_key(key)
    typed_value = _coerce_value(key, value)

    data = _load_config()
    if section not in data:
        data[section] = {}
    data[section][field] = typed_value
    _save_config(data)

    display = _redact(key, typed_value)
    click.echo(f"Set {key} = {display}")


@config_group.command(name="get")
@click.argument("key")
def config_get(key):
    """Get a config value. KEY uses dot-notation: SECTION.FIELD.

    Example:
      workflo config get llm.base_url
    """
    section, field = _validate_dot_key(key)
    data = _load_config()

    section_data = data.get(section, {})
    if not isinstance(section_data, dict) or field not in section_data:
        click.echo(f"{key}: (not set)")
        raise SystemExit(1)

    value = section_data[field]
    display = _redact(key, value)
    click.echo(f"{key} = {display}")


@config_group.command(name="list")
def config_list():
    """List all config values (secrets are redacted)."""
    data = _load_config()
    if not data:
        click.echo("No config found. Run `workflo config init` to create one.")
        return

    for section in sorted(data.keys()):
        section_data = data[section]
        if not isinstance(section_data, dict):
            click.echo(f"{section} = {section_data}")
            continue
        click.echo(f"[{section}]")
        for field in sorted(section_data.keys()):
            dot_key = f"{section}.{field}"
            display = _redact(dot_key, section_data[field])
            click.echo(f"  {field} = {display}")


@config_group.command(name="path")
def config_path_cmd():
    """Print the config file path."""
    path = _config_path()
    click.echo(str(path))
    if path.exists():
        click.echo("(exists)", err=True)
    else:
        click.echo("(not created yet — run `workflo config init`)", err=True)
