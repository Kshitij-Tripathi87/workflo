"""Interactive test command — the goal-based entry point for running tests."""

import click
import questionary
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from workflo_agent.client import ControlPlaneClient
from workflo_agent.ui.prompts import GOAL_CHOICES, prompt_goal, prompt_execution_mode, prompt_overrides

console = Console()


@click.command()
@click.option("--goal", type=click.Choice(["smoke", "security", "integration", "mobile", "regression", "custom"]), default=None, help="Test goal (skip interactive prompt)")
@click.option("--local", is_flag=True, default=False, help="Force local execution")
@click.option("--cloud", is_flag=True, default=False, help="Force cloud execution")
def test(goal, local, cloud):
    """Run tests interactively — pick a goal and let the agent handle the rest."""

    console.print(Panel.fit("[bold cyan]Tenant Shield Test Runner[/bold cyan]", border_style="cyan"))

    selected_goal = goal or prompt_goal()
    execution_mode = "local" if local else ("cloud" if cloud else prompt_execution_mode())
    overrides = prompt_overrides()

    console.print(f"\n[bold]Goal:[/bold] {selected_goal}")
    console.print(f"[bold]Mode:[/bold] {execution_mode}")
    for k, v in overrides.items():
        if v:
            console.print(f"[bold]{k}:[/bold] {v}")

    spec = {
        "goal": selected_goal,
        "markers": GOAL_CHOICES.get(selected_goal, {}).get("markers", []),
        "env": {k: v for k, v in overrides.items() if v},
    }

    if execution_mode == "cloud":
        _run_cloud(spec)
    else:
        _run_local(spec)


def _run_cloud(spec: dict):
    console.print("\n[bold cyan]Submitting to cloud...[/bold cyan]")
    try:
        client = ControlPlaneClient()
        result = client.submit_run(spec)
        run_id = result["run_id"]
        console.print(f"[green]Run submitted![/green] Run ID: {run_id}")
        console.print(f"View results: https://app.tenantshield.dev/runs/{run_id}")
    except Exception as e:
        console.print(f"[bold red]Failed to submit run: {e}[/bold red]")
        console.print("[yellow]Falling back to local execution...[/yellow]")
        _run_local(spec)


def _run_local(spec: dict):
    import subprocess
    import shlex

    console.print("\n[bold cyan]Running tests locally...[/bold cyan]")
    markers = " ".join(spec.get("markers", []))
    pytest_cmd = ["pytest", "-m", markers] if markers else ["pytest"]

    console.print(f"[dim]{' '.join(pytest_cmd)}[/dim]\n")
    try:
        subprocess.run(pytest_cmd, check=True)
        console.print("\n[bold green]Tests completed.[/bold green]")
    except subprocess.CalledProcessError as e:
        console.print(f"\n[bold red]Tests failed with exit code {e.returncode}[/bold red]")
    except FileNotFoundError:
        console.print("[bold red]pytest not found. Activate your venv first.[/bold red]")
