"""CLI entry point for validate-phase2.

Usage:
    validate-phase2 --repo <url-or-path> [options]

Options:
    --repo            Repository URL or local path to validate (required)
    --baseline        Manual baseline commit hash (auto-computed if omitted)
    --model-endpoint  vLLM / OpenAI-compatible endpoint URL (env: MODEL_ENDPOINT)
    --model           Model name (env: MODEL_NAME)
    --flags           Comma-separated review flags
    --formats         Comma-separated output formats (md, json, sarif, html)
    --output          Output directory for report files
    --venv-python     Python interpreter for running gates (advanced)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import click
from rich.console import Console

from .orchestrator import run_validation
from .reporters import REPORTERS

# On Windows, ensure stdout/stderr can handle Unicode characters (e.g. in
# gate output or LLM notes).  The default cp1252 code page cannot encode
# characters like the check-mark, causing UnicodeEncodeError mid-run.
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            try:
                _stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

console = Console()

DEFAULT_FLAGS = ["architecture", "patterns"]
DEFAULT_FORMATS = ["md", "json", "sarif", "html"]
DEFAULT_MODEL_ENDPOINT = os.environ.get("MODEL_ENDPOINT", "http://localhost:8000/v1")
DEFAULT_MODEL = os.environ.get("MODEL_NAME", "Qwen/Qwen2.5-Coder-7B-AWQ")

VALID_FLAGS = {
    "architecture",
    "patterns",
    "oauth-correctness",
    "jwt",
    "async-patterns",
    "security",
}

# Map severity -> rich color tag for the summary table.
SEVERITY_COLORS = {
    "critical": "bold red",
    "high": "red",
    "medium": "yellow",
    "low": "dim yellow",
    "info": "blue",
}


def _parse_csv(value: str) -> list[str]:
    """Parse a comma-separated string into a list of trimmed, non-empty values."""
    return [v.strip() for v in value.split(",") if v.strip()]


def _exit_with_summary(result, out_dir: Path, format_list: list[str]) -> None:
    """Write reports, print the summary, and exit with an appropriate code."""
    # --- Write reports -------------------------------------------------------
    for fmt in format_list:
        reporter = REPORTERS[fmt]
        ext = fmt  # "sarif" -> .sarif, "md" -> .md, etc.
        out_path = out_dir / f"validation_report.{ext}"
        reporter(result, out_path)
        console.print(f"  [green]OK[/green] {fmt:5s}  {out_path}")

    # --- Summary -------------------------------------------------------------
    console.print()
    console.print("[bold]Summary[/bold]")
    counts = result.severity_counts
    for sev in ("critical", "high", "medium", "low", "info"):
        count = counts.get(sev, 0)
        if count:
            color = SEVERITY_COLORS.get(sev, "white")
            console.print(f"  [{color}]{sev:<10}[/{color}] {count}")

    gates_passed = sum(1 for g in result.gates if g.passed)
    gates_total = len(result.gates)
    console.print(f"\n  Gates: {gates_passed}/{gates_total} passed")

    if result.notes:
        console.print(f"  Notes: {result.notes}")

    # --- Exit code -----------------------------------------------------------
    has_critical = counts.get("critical", 0) > 0
    has_high = counts.get("high", 0) > 0

    if not result.all_gates_passed:
        console.print(
            "\n[bold red]FAIL: Exiting with code 1: gate failures detected.[/bold red]"
        )
        sys.exit(1)
    if has_critical or has_high:
        console.print(
            f"\n[bold red]FAIL: Exiting with code 1: "
            f"{has_critical} critical, {has_high} high findings.[/bold red]"
        )
        sys.exit(1)

    console.print("\n[bold green]OK: All checks passed.[/bold green]")
    sys.exit(0)


@click.command()
@click.option(
    "--repo",
    required=True,
    help="Repository URL or local path to validate.",
)
@click.option(
    "--baseline",
    default=None,
    help="Manual baseline commit hash (auto-computed from merge-base if omitted).",
)
@click.option(
    "--model-endpoint",
    default=DEFAULT_MODEL_ENDPOINT,
    show_default=True,
    help="vLLM / OpenAI-compatible endpoint URL (env: MODEL_ENDPOINT).",
)
@click.option(
    "--model",
    default=DEFAULT_MODEL,
    show_default=True,
    help="Model name to use for analysis (env: MODEL_NAME).",
)
@click.option(
    "--flags",
    default=",".join(DEFAULT_FLAGS),
    show_default=True,
    help="Comma-separated review flags (e.g. architecture,security,jwt).",
)
@click.option(
    "--formats",
    default=",".join(DEFAULT_FORMATS),
    show_default=True,
    help="Comma-separated output formats (md, json, sarif, html).",
)
@click.option(
    "--output",
    default="./reports",
    show_default=True,
    help="Output directory for report files.",
)
@click.option(
    "--venv-python",
    default=None,
    help="Python interpreter to use for running gates (default: current interpreter).",
)
@click.version_option(package_name="validate-phase2")
def main(
    repo: str,
    baseline: str | None,
    model_endpoint: str,
    model: str,
    flags: str,
    formats: str,
    output: str,
    venv_python: str | None,
):
    """Run the sandboxed architecture-review pipeline.

    Clones the repository, runs automated gates (import-check, pytest),
    feeds the diff + context to a vLLM-hosted LLM for architectural review,
    and emits reports in the requested formats.
    """
    flag_list = _parse_csv(flags)
    format_list = _parse_csv(formats)

    # --- Validate flags ------------------------------------------------------
    unknown = [f for f in flag_list if f not in VALID_FLAGS]
    if unknown:
        console.print(f"[bold red]Unknown flags: {', '.join(unknown)}[/bold red]")
        console.print(
            f"[dim]Valid flags: {', '.join(sorted(VALID_FLAGS))}[/dim]"
        )
        sys.exit(2)

    # --- Validate formats ---------------------------------------------------
    bad_formats = [f for f in format_list if f not in REPORTERS]
    if bad_formats:
        console.print(
            f"[bold red]Unknown formats: {', '.join(bad_formats)}[/bold red]"
        )
        console.print(
            f"[dim]Valid formats: {', '.join(sorted(REPORTERS))}[/dim]"
        )
        sys.exit(2)

    # --- Print config -------------------------------------------------------
    console.print(
        "[bold cyan]validate-phase2[/bold cyan] — architecture review pipeline"
    )
    console.print(f"  [dim]repo:[/dim]          {repo}")
    console.print(f"  [dim]model-endpoint:[/dim] {model_endpoint}")
    console.print(f"  [dim]model:[/dim]         {model}")
    console.print(f"  [dim]flags:[/dim]         {', '.join(flag_list)}")
    console.print(f"  [dim]formats:[/dim]       {', '.join(format_list)}")
    console.print(f"  [dim]output:[/dim]        {output}")
    if baseline:
        console.print(f"  [dim]baseline:[/dim]      {baseline}")
    console.print()

    # --- Progress logger ----------------------------------------------------
    def log(msg: str) -> None:
        console.print(f"  [dim]{msg}[/dim]")

    # --- Run pipeline -------------------------------------------------------
    try:
        result = run_validation(
            repo_url=repo,
            model_endpoint=model_endpoint,
            model=model,
            flags=flag_list,
            venv_python=venv_python,
            baseline=baseline,
            on_log=log,
        )
    except Exception as exc:
        console.print(f"\n[bold red]Pipeline failed:[/bold red] {exc}")
        sys.exit(1)

    # --- Write reports & exit -----------------------------------------------
    out_dir = Path(output)
    _exit_with_summary(result, out_dir, format_list)


if __name__ == "__main__":
    main()
