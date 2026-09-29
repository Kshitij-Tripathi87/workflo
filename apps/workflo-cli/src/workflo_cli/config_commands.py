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
@click.option("--base-url", required=True, help="Model endpoint (direct) or inference gateway (gateway)")
@click.option("--api-key", required=True, help="Bearer key for the model server")
@click.option("--model", default=DEFAULT_MODEL, show_default=True, help="Model identifier")
@click.option("--timeout", "timeout_seconds", default=DEFAULT_TIMEOUT_SECONDS,
              show_default=True, type=int, help="Per-request timeout in seconds")
@click.option("--mode", default="direct", show_default=True, type=click.Choice(["direct", "gateway"]),
              help="direct = call the model endpoint; gateway = route through the "
                   "control-plane privacy gateway (observation-only; the upstream "
                   "model key stays server-side)")
@click.option("--gateway-url", default=None,
              help="Inference gateway base URL (gateway mode; default: --base-url)")
def config_set_llm(base_url: str, api_key: str, model: str, timeout_seconds: int,
                   mode: str, gateway_url: Optional[str]):
    """Configure the LLM endpoint used by --deep-test / --aggressive-test.

    The API key is stored in the OS credential store (never in the config
    file). Values are validated before anything is persisted.

    gateway mode keeps the upstream model key on the control plane: the
    CLI authenticates to the privacy gateway, which forwards ONLY
    bounded runtime observations to the model.
    """
    try:
        backend = set_llm_config(base_url, api_key, model, timeout_seconds,
                                 mode=mode, gateway_url=gateway_url)
    except LLMConfigError as e:
        raise click.BadParameter(str(e))
    click.echo(f"LLM endpoint configured: {base_url} (model: {model}, mode: {mode})", err=True)
    click.echo(f"API key stored in: {backend}", err=True)
    if mode == "gateway":
        click.echo("Privacy: hosted inference is observation-only — source code never leaves the sandbox", err=True)
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