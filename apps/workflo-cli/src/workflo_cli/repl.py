"""Interactive REPL for workflo — a thin front-end over the existing CLI.

Design constraints (hard rules):
- Reuses the existing Click `run` command from main.py verbatim — same flag
  parsing, same auth gate, same executor. No duplicated logic to drift.
- Reuses the SAME config source of truth: llm_config.set_llm_config()
  (config.json + OS credential store). `workflo config get-llm` and the REPL's
  /configure observe each other's writes because they are the same store.
- The API key prompt uses hide_input=True and lands only in the credential
  store path — never echoed, never written to config.json.
"""

from __future__ import annotations

import shlex
import sys

import click

from workflo_cli.llm_config import (
    DEFAULT_MODEL,
    LLMConfigError,
    load_llm_config,
    set_llm_config,
)

# The five skills the deep-tier worker exposes to the model loop. The REPL
# surfaces them read-only; it does not implement or exec them.
TOOLS = (
    ("run_command", "Run an allowlisted shell command inside the sandbox"),
    ("call_api", "Call the running application's own API"),
    ("read_logs", "Read the application's stdout/stderr"),
    ("get_metrics", "Get CPU/memory/response-time metrics"),
    ("report_finding", "Record a finding with severity and reasoning"),
)

# Completion surface. /quit is handled as an alias for /exit in handle_line()
# but kept out of the completion list so the canonical spelling stands alone.
SLASH_COMMANDS = ["/configure", "/run", "/tools", "/help", "/exit"]

_HELP = """Commands:
  /configure        Set the hosted LLM endpoint (base URL, key, model)
  /run <flags>      Run the sandbox pipeline (same flags as `workflo run`)
  /tools            List the skills the deep-tier model can call
  /help             Show this help
  /exit, /quit      Leave the REPL
"""


def interactive_configure() -> None:
    """Prompt for LLM endpoint settings and persist via the shared store.

    A blank API key means "keep the stored one" (same UX as git credential
    helpers). Errors from the store surface as a message, not a traceback.
    """
    current = load_llm_config()
    base_url_default = current.base_url if current else ""
    model_default = current.model if current else DEFAULT_MODEL

    base_url = click.prompt("LLM base URL", default=base_url_default)
    api_key = click.prompt(
        "LLM API key (blank = keep existing)",
        default="",
        hide_input=True,
        show_default=False,
    )
    model = click.prompt("LLM model name", default=model_default)

    key = api_key.strip()
    if not key:
        if current and current.api_key:
            key = current.api_key
        else:
            click.echo("No API key on file — re-run /configure with a key.")
            return

    try:
        backend = set_llm_config(base_url, key, model)
    except LLMConfigError as e:
        click.echo(f"Not saved: {e}", err=True)
        return
    click.echo(f"Configuration saved (key stored via {backend}).")


def list_tools() -> None:
    """List the deep-tier skills (read-only surface, no execution)."""
    for name, desc in TOOLS:
        click.echo(f"  {name:16s} {desc}")


def handle_line(line: str) -> bool:
    """Dispatch one REPL input line.

    Returns True to keep the REPL alive; False exits the loop.
    Side-condition: /run invokes the real Click command object, so flag
    parsing, validation, the auth gate, and the executor are identical to
    `workflo run ...` in a shell.
    """
    line = (line or "").strip()
    if not line:
        return True
    if not line.startswith("/"):
        click.echo("Not a command — slash commands only. /help for the list.")
        return True

    cmd, _, rest = line.partition(" ")

    if cmd in ("/exit", "/quit"):
        return False
    if cmd == "/help":
        click.echo(_HELP)
        return True
    if cmd == "/configure":
        interactive_configure()
        return True
    if cmd == "/tools":
        list_tools()
        return True
    if cmd == "/run":
        args = shlex.split(rest, posix=True)
        if not args:
            click.echo("Usage: /run <same flags as `workflo run`>\n"
                       "       e.g. /run --repo https://github.com/org/repo.git --test")
            return True
        # Imported lazily: this module must not pull main.py in at import
        # time (circular import — main.py registers this command).
        from workflo_cli.main import run as run_command

        try:
            run_command.main(args=args, standalone_mode=False)
        except SystemExit as e:
            # click/sys.exit paths: non-zero exit just means the run refused.
            if e.code not in (0, None):
                click.echo(f"run exited with code {e.code}", err=True)
        except click.exceptions.ClickException as e:
            # UsageError and friends render their own message.
            e.show()
        except click.exceptions.Abort:
            click.echo("Aborted.", err=True)
        return True

    click.echo(f"Unknown command: {cmd}  (/help for the list)")
    return True


@click.command("repl")
def repl_command() -> None:
    """Start the interactive workflo REPL."""
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise click.ClickException(
            "repl requires an interactive terminal (stdin/stdout must be a TTY)."
        )

    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.completion import WordCompleter
    except ImportError:
        # prompt_toolkit is a core dependency; reaching here means the
        # environment is broken (partial uninstall, corrupted site-packages).
        raise click.ClickException(
            "prompt_toolkit is not installed — repair with: "
            "pip install --force-reinstall 'prompt_toolkit>=3.0'"
        )

    session = PromptSession()
    completer = WordCompleter(SLASH_COMMANDS, sentence=True)
    click.echo("workflo — interactive mode. /help for commands, /exit to leave.")

    while True:
        try:
            line = session.prompt("workflo> ", completer=completer)
        except (EOFError, KeyboardInterrupt):
            break
        if not handle_line(line):
            break
