"""Workflo command-line interface.

Thin client over the same fail-closed ModelRouter that powers the HTTP
service and the worker. Every subcommand prints a single JSON document to
stdout (machine-readable); diagnostics go to stderr.

Exit codes:
  0  success
  1  generation rejected (schema/safety-gate failure or bad model output)
  2  environment or server error: llama-server unreachable, adapter
     discovery failed, invalid --base-url — or CLI usage error (click default)
  4  unexpected internal error

Artifact metadata is opt-in via --with-artifacts: unlike the long-lived
HTTP service (which hashes once at startup), a CLI invocation would pay the
full 2.5 GB base-model re-hash on every call, so identity metadata is only
loaded when explicitly requested.
"""

from __future__ import annotations

import json
import sys
import time

import click

from workflo_ai_integration.model_router import (
    AdapterLoadError,
    GenerationValidationError,
    ModelRouter,
    RouterConfig,
    TaskType,
)
from workflo_ai_integration.service_defaults import SYSTEM_PROMPTS

TASK_ALIASES: dict[str, TaskType] = {
    "test_gen": "test-gen",
    "test-gen": "test-gen",
    "reasoning": "reasoning",
    "reporting": "reporting",
}

MAX_REPORT_RESULTS_BYTES = 262_144


def build_router(
    base_url: str | None = None, timeout_sec: float | None = None
) -> ModelRouter:
    if base_url is None and timeout_sec is None:
        return ModelRouter()
    config_kwargs: dict = {}
    if base_url:
        config_kwargs["base_url"] = base_url
    if timeout_sec:
        config_kwargs["timeout_sec"] = timeout_sec
    return ModelRouter(RouterConfig(**config_kwargs))


def load_registry():
    """Return a verified ArtifactRegistry, or None when unavailable."""
    try:
        from workflo_ai_integration.artifact_registry import ArtifactRegistry

        return ArtifactRegistry()
    except Exception:
        return None


def _emit(payload: dict, pretty: bool) -> None:
    click.echo(json.dumps(payload, indent=2 if pretty else None))


def _fail(error: str, detail: str, code: int) -> None:
    click.echo(json.dumps({"error": error, "detail": detail}), err=True)
    sys.exit(code)


@click.group()
@click.version_option(package_name="workflo-ai-integration", prog_name="workflo-ai")
def cli() -> None:
    """Workflo AI — fail-closed adapter routing over manifest-pinned GGUFs.

    This is the model-serving CLI (workflo-ai). The product CLI is the
    separately installed `workflo` command (@cortexstudio/workflo); the two
    are deliberately independent so the npm product CLI never depends on the
    Python model runtime being importable.
    """


@cli.command()
@click.option(
    "--task",
    "task_alias",
    type=click.Choice(sorted(TASK_ALIASES)),
    required=True,
    help="Adapter task to run (reporting uses the dedicated `report` command).",
)
@click.option("--prompt", required=True, help="User prompt (module/behavior description).")
@click.option("--system-prompt", default=None, help="Override the trained system prompt.")
@click.option("--base-url", default=None, help="llama-server loopback URL (default 127.0.0.1:8080).")
@click.option("--timeout", "timeout_sec", type=float, default=600.0, show_default=True, help="Completion timeout in seconds (CPU-only servers need large values).")
@click.option("--with-artifacts", is_flag=True, help="Include verified artifact identities in the output.")
@click.option("--compact/--pretty", "compact", default=False, help="Compact JSON output.")
def generate(
    task_alias: str,
    prompt: str,
    system_prompt: str | None,
    base_url: str | None,
    timeout_sec: float,
    with_artifacts: bool,
    compact: bool,
) -> None:
    """Generate a validated schema payload for a task adapter."""
    task = TASK_ALIASES[task_alias]
    router = None
    try:
        router = build_router(base_url, timeout_sec)
        effective_system = system_prompt or SYSTEM_PROMPTS[task]
        start = time.perf_counter()
        result = router.generate_for_task(task, effective_system, prompt)
        latency_ms = round((time.perf_counter() - start) * 1000)
    except AdapterLoadError as exc:
        _fail("adapter_load_failed", str(exc), 2)
    except GenerationValidationError as exc:
        _fail("generation_validation_failed", str(exc), 1)
    except ValueError as exc:
        _fail("invalid_configuration", str(exc), 2)

    payload: dict = {
        "task": task,
        "result": result.model_dump(),
        "latency_ms": latency_ms,
    }
    if with_artifacts:
        registry = load_registry()
        payload["artifacts"] = registry.telemetry() if registry else None
    _emit(payload, not compact)


@cli.command()
@click.option("--results", default=None, help="Structured results as inline JSON.")
@click.option(
    "--file",
    "results_file",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Path to a JSON file with structured results ('-' for stdin).",
)
@click.option("--base-url", default=None, help="llama-server loopback URL (default 127.0.0.1:8080).")
@click.option("--timeout", "timeout_sec", type=float, default=600.0, show_default=True, help="Completion timeout in seconds (CPU-only servers need large values).")
@click.option("--with-artifacts", is_flag=True, help="Include verified artifact identities in the output.")
@click.option("--compact/--pretty", "compact", default=False, help="Compact JSON output.")
def report(
    results: str | None,
    results_file: str | None,
    base_url: str | None,
    timeout_sec: float,
    with_artifacts: bool,
    compact: bool,
) -> None:
    """Summarize structured test outcomes via the reporting adapter.

    Input is structured outcomes only — never source code.
    """
    if bool(results) == bool(results_file):
        _fail("invalid_usage", "provide exactly one of --results or --file", 2)
    if results_file == "-":
        results = click.get_text_stream("stdin").read()
    elif results_file:
        with open(results_file, encoding="utf-8") as handle:
            results = handle.read()
    if len(results) > MAX_REPORT_RESULTS_BYTES:
        _fail("results_too_large", f"results must be <= {MAX_REPORT_RESULTS_BYTES} bytes", 2)
    try:
        results_json = json.loads(results)
    except json.JSONDecodeError as exc:
        _fail("invalid_results_json", str(exc), 2)
    if not isinstance(results_json, dict):
        _fail("invalid_results_json", "results must be a JSON object", 2)

    try:
        router = build_router(base_url, timeout_sec)
        start = time.perf_counter()
        result = router.generate_report(results_json)
        latency_ms = round((time.perf_counter() - start) * 1000)
    except AdapterLoadError as exc:
        _fail("adapter_load_failed", str(exc), 2)
    except GenerationValidationError as exc:
        _fail("generation_validation_failed", str(exc), 1)
    except ValueError as exc:
        _fail("invalid_configuration", str(exc), 2)

    payload: dict = {
        "task": "reporting",
        "result": result.model_dump(),
        "latency_ms": latency_ms,
    }
    if with_artifacts:
        registry = load_registry()
        payload["artifacts"] = registry.telemetry() if registry else None
    _emit(payload, not compact)


@cli.command()
@click.option("--base-url", default=None, help="llama-server loopback URL (default 127.0.0.1:8080).")
def health(base_url: str | None) -> None:
    """Probe llama-server adapter discovery; exit 2 when degraded."""
    try:
        router = build_router(base_url)
        ids = router.discover_adapters()
    except AdapterLoadError as exc:
        click.echo(
            json.dumps({"status": "degraded", "reason": str(exc)}),
            err=True,
        )
        sys.exit(2)
    except ValueError as exc:
        _fail("invalid_configuration", str(exc), 2)
    _emit({"status": "ok", "adapter_ids": {t: ids[t] for t in sorted(ids)}}, True)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
