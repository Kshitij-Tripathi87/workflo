"""Runs command — list and get historical test runs."""

import click
from rich.console import Console
from rich.table import Table
from workflo_agent.client import ControlPlaneClient

console = Console()


@click.group()
def runs():
    """View and manage test runs."""
    pass


@runs.command()
@click.option("--limit", default=20, help="Number of runs to show")
@click.option("--status", default=None, type=click.Choice(["queued", "running", "completed", "failed", "cancelled"]), help="Filter by status")
def list(limit, status):
    """List recent test runs."""
    try:
        client = ControlPlaneClient()
        run_list = client.list_runs(limit=limit)
    except Exception as e:
        console.print(f"[bold red]Failed to fetch runs: {e}[/bold red]")
        return

    table = Table(title="Recent Runs")
    table.add_column("Run ID", style="cyan")
    table.add_column("Goal")
    table.add_column("Status")
    table.add_column("Started")

    for run in run_list if isinstance(run_list, list) else []:
        table.add_row(str(run.get("run_id", "")), str(run.get("goal", "")), str(run.get("status", "")), str(run.get("started_at", "")))

    console.print(table)


@runs.command()
@click.argument("run_id")
def get(run_id):
    """Get details and download artifacts for a specific run."""
    try:
        client = ControlPlaneClient()
        result = client.get_run(run_id)
        console.print(result)
    except Exception as e:
        console.print(f"[bold red]Failed to fetch run: {e}[/bold red]")
