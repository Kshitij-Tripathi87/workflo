"""Tests for the interactive REPL (workflo repl).

Key property under test: the REPL and the flag-mode CLI share ONE config
source of truth. /configure writes through llm_config.set_llm_config(), and
`load_llm_config()` (what `workflo config get-llm` reads) sees the same data.
"""

import json

import pytest
import click
from click.testing import CliRunner

from workflo_cli import repl as repl_mod
from workflo_cli.llm_config import load_llm_config
from workflo_cli.main import cli


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    """Point the LLM config store at a temp dir so tests never touch the
    user's real ~/.config/workflo."""
    monkeypatch.setenv("WORKFLO_CONFIG_DIR", str(tmp_path))
    return tmp_path


class TestSlashCommands:
    def test_help_lists_commands(self, capsys):
        assert repl_mod.handle_line("/help") is True
        out = capsys.readouterr().out
        for cmd in ("/configure", "/run", "/tools", "/help", "/exit"):
            assert cmd in out

    def test_tools_lists_five_skills(self, capsys):
        repl_mod.handle_line("/tools")
        out = capsys.readouterr().out
        for name in ("run_command", "call_api", "read_logs", "get_metrics", "report_finding"):
            assert name in out

    def test_exit_returns_false(self):
        assert repl_mod.handle_line("/exit") is False

    def test_quit_alias_returns_false(self):
        assert repl_mod.handle_line("/quit") is False

    def test_unknown_command_reports(self, capsys):
        assert repl_mod.handle_line("/nonsense") is True
        assert "Unknown command" in capsys.readouterr().out

    def test_empty_line_is_noop(self):
        assert repl_mod.handle_line("   ") is True

    def test_non_slash_input_rejected(self, capsys):
        assert repl_mod.handle_line("run --repo x") is True
        assert "slash commands only" in capsys.readouterr().out

    def test_run_without_args_shows_usage(self, capsys):
        repl_mod.handle_line("/run")
        assert "Usage: /run" in capsys.readouterr().out


class TestConfigure:
    def _prompt_answerer(self, base_url="", key="", model=""):
        answers = iter([base_url, key, model])

        def fake_prompt(text, **kwargs):
            return next(answers)

        return fake_prompt

    def test_configure_writes_shared_config(
        self, isolated_config, monkeypatch, capsys
    ):
        monkeypatch.setattr(
            "workflo_cli.repl.click.prompt",
            self._prompt_answerer(
                base_url="https://model.test/v1", key="sk-repl-test", model="qwen3"
            ),
        )
        repl_mod.interactive_configure()
        out = capsys.readouterr().out
        assert "Configuration saved" in out

        # Same source of truth as `workflo config get-llm`:
        cfg = load_llm_config()
        assert cfg is not None
        assert cfg.base_url == "https://model.test/v1"
        assert cfg.model == "qwen3"
        assert cfg.api_key == "sk-repl-test"

        # Key must NOT be plaintext in config.json — only the credential store.
        raw = json.loads((isolated_config / "config.json").read_text())
        assert "sk-repl-test" not in json.dumps(raw)

    def test_blank_key_keeps_existing(self, isolated_config, monkeypatch, capsys):
        # First configure with a key.
        monkeypatch.setattr(
            "workflo_cli.repl.click.prompt",
            self._prompt_answerer(
                base_url="https://model.test/v1", key="sk-first", model="qwen3"
            ),
        )
        repl_mod.interactive_configure()

        # Reconfigure with blank key — must keep "sk-first".
        monkeypatch.setattr(
            "workflo_cli.repl.click.prompt",
            self._prompt_answerer(
                base_url="https://model2.test/v1", key="", model="qwen4"
            ),
        )
        repl_mod.interactive_configure()

        cfg = load_llm_config()
        assert cfg.base_url == "https://model2.test/v1"
        assert cfg.api_key == "sk-first"  # kept

    def test_blank_key_without_prior_key_refuses(self, isolated_config, monkeypatch, capsys):
        monkeypatch.setattr(
            "workflo_cli.repl.click.prompt",
            self._prompt_answerer(base_url="https://model.test/v1", key="", model="m"),
        )
        repl_mod.interactive_configure()
        out = capsys.readouterr().out
        assert "No API key on file" in out
        assert load_llm_config() is None

    def test_placeholder_base_url_rejected_by_store(self, isolated_config, monkeypatch, capsys):
        # set_llm_config validates; placeholders should not persist.
        monkeypatch.setattr(
            "workflo_cli.repl.click.prompt",
            self._prompt_answerer(base_url="notaurl", key="k", model="m"),
        )
        repl_mod.interactive_configure()
        captured = capsys.readouterr()
        assert "Not saved" in (captured.out + captured.err)
        assert load_llm_config() is None


class TestRunDispatch:
    def test_run_invokes_main_run_command_same_code_path(
        self, monkeypatch, capsys
    ):
        """The REPL must call the real Click command object — same parsing,
        same auth gate, same executor — not a reimplementation."""
        captured = {}

        class FakeCmd:
            def main(self, args=None, standalone_mode=None):
                captured["args"] = args
                captured["standalone_mode"] = standalone_mode

        monkeypatch.setattr(
            "workflo_cli.main.run", FakeCmd(), raising=True
        )
        # Reimport after patching: handle_line does the import lazily.
        repl_mod.handle_line(
            '/run --repo https://github.com/org/repo.git --test'
        )
        assert captured["standalone_mode"] is False
        assert captured["args"] == [
            "--repo", "https://github.com/org/repo.git", "--test"
        ]

    def test_run_swallows_usage_error_without_killing_repl(self, capsys):
        # --repo is validated before tier exclusivity; pass --repo so the
        # exclusivity check fires. Click writes usage errors to stderr.
        ok = repl_mod.handle_line(
            "/run --repo https://github.com/org/repo.git --test --deep-test"
        )
        assert ok is True  # REPL survives
        err = capsys.readouterr().err
        assert "Only one functional tier" in err

    def test_run_dry_run_plan_reaches_stdout(self, capsys):
        ok = repl_mod.handle_line(
            "/run --repo https://github.com/psf/requests.git --test --dry-run"
        )
        assert ok is True
        out = capsys.readouterr().out
        assert '"dry-run"' in out or "dry-run" in out
        assert '"probe_groups"' in out or "probe_groups" in out


class TestCommandRegistration:
    def test_repl_registered_on_cli(self):
        assert "repl" in cli.commands

    def test_repl_help_runs(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["repl", "--help"])
        assert result.exit_code == 0
        assert "interactive" in result.output.lower()

    def test_repl_requires_tty(self, monkeypatch):
        # When stdin/stdout are not a TTY (CI, piped input), repl must fail
        # with a clean message instead of a prompt_toolkit traceback.
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        from workflo_cli.repl import repl_command

        with pytest.raises(click.ClickException) as excinfo:
            repl_command.callback()
        assert "interactive terminal" in str(excinfo.value)
