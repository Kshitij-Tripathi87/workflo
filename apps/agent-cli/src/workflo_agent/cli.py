"""Main CLI entry point for the workflo agent."""

import click
from rich.console import Console

from workflo_agent.commands.auth import auth
from workflo_agent.commands.test import test
from workflo_agent.commands.runs import runs

console = Console()


@click.group()
@click.version_option(package_name="workflo-agent")
def main():
    """Workflo — autonomous QA agent from your terminal."""
    pass


main.add_command(auth)
main.add_command(test)
main.add_command(runs)


if __name__ == "__main__":
    main()
