"""Auth command — login, status, logout."""

import click
from rich.console import Console
from rich.table import Table
from workflo_utils.config import load_config, save_config

console = Console()


@click.group()
def auth():
    """Manage your Tenant Shield API key."""
    pass


@auth.command()
@click.option("--key", prompt="API Key", help="Your Tenant Shield API key", hide_input=True)
def login(key: str):
    """Authenticate with your Tenant Shield API key."""
    config = load_config()
    config["auth"] = {"api_key": key}
    save_config(config)
    console.print("[bold green]Authenticated successfully![/bold green]")
    console.print("Key stored in ~/.workflo/config.yaml")


@auth.command()
def status():
    """Show current authentication status."""
    config = load_config()
    api_key = config.get("auth", {}).get("api_key")
    if api_key:
        masked = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "***"
        table = Table(title="Auth Status")
        table.add_column("Field", style="cyan")
        table.add_column("Value")
        table.add_row("API Key", masked)
        table.add_row("Config Path", "~/.workflo/config.yaml")
        console.print(table)
    else:
        console.print("[bold red]Not authenticated.[/bold red]")
        console.print("Run `workflo auth login` to authenticate.")


@auth.command()
def logout():
    """Remove your stored API key."""
    config = load_config()
    config.pop("auth", None)
    save_config(config)
    console.print("[bold yellow]Logged out. API key removed.[/bold yellow]")
