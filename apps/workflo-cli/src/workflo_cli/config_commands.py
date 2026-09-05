"""`workflo config` command group — settings that live outside any sandbox run.

Currently scoped to the LLM endpoint used by --deep-test / --aggressive-test:

    workflo config set-llm --base-url <url> --api-key <key> [--model qwen3-4b-4bit]
    workflo config get-llm          # key always redacted
    workflo config test-llm         # validates the key against the endpoint
    workflo config list             # redacted summary of every section

Design rules:
  - The API key is never printed and never written to the config file. It
    goes to the OS credential store (Keychain / Windows Credential Manager /
    Secret Service), with a permission-restricted (0600) file as the last
    resort.
  - Every display surface (this module's output, the dry-run plan) routes
    through llm_config.redact_key(). The redaction habit is locked in now,
    while the endpoint is still a placeholder, so a real key can never
    leak via cargo-culted output later.
"""

from __future__ import annotations

from typing import Optional

import click

from workflo_cli.llm_config import (
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT_SECONDS,
    LLMConfigError,
    clear_llm_config,
    describe_llm_config,
    set_llm_config,
    validate_llm_key,
)

LLM_NOT_CONFIGURED_HINT = (
    "LLM not configured — run: "
    "workflo config set-llm --base-url <url> --api-key <key>"
)


@click.group("config")
def config_group():
    """View and edit workflo settings (LLM endpoint, defaults)."""


@config_group.command("set-llm")
@click.option("--base-url", required=True, help="Model server base URL (https://...)")
@click.option("--api-key", required=True, help="Bearer key for the model server")
@click.option("--model", default=DEFAULT_MODEL, show_default=True, help="Model identifier")
@click.option("--timeout", "timeout_seconds", default=DEFAULT_TIMEOUT_SECONDS,
              show_default=True, type=int, help="Per-request timeout in seconds")
def config_set_llm(base_url: str, api_key: str, model: str, timeout_seconds: int):
    """Configure the LLM endpoint used by --deep-test / --aggressive-test.

    The API key is stored in the OS credential store (never in the config
    file). Values are validated before anything is persisted.
    """
    try:
        backend = set_llm_config(base_url, api_key, model, timeout_seconds)
    except LLMConfigError as e:
        raise click.BadParameter(str(e))
    click.echo(f"LLM endpoint configured: {base_url} (model: {model})", err=True)
    click.echo(f"API key stored in: {backend}", err=True)
    click.echo("Validate with: workflo config test-llm", err=True)


@config_group.command("get-llm")
def config_get_llm():
    """Show the current LLM config. The API key is always redacted."""
    import json as _json

    click.echo(_json.dumps({"llm": describe_llm_config()}, indent=2))


@config_group.command("test-llm")
def config_test_llm():
    """Contact the configured endpoint with the stored key and report status."""
    ok, msg = validate_llm_key()
    if ok:
        click.echo(f"ok: {msg}", err=True)
        raise SystemExit(0)
    click.echo(f"failed: {msg}", err=True)
    raise SystemExit(1)


@config_group.command("clear-llm")
def config_clear_llm():
    """Remove the stored LLM endpoint and key."""
    clear_llm_config()
    click.echo("LLM config cleared", err=True)


@config_group.command("list")
def config_list():
    """Show a redacted summary of every config section."""
    import json as _json

    click.echo(_json.dumps({"llm": describe_llm_config()}, indent=2))