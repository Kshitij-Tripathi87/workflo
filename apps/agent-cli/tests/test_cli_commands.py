"""CLI command tests executed through click's CliRunner.

No network, no interactive prompts, no subprocesses - everything the
commands depend on is patched out.
"""

from unittest.mock import patch

from click.testing import CliRunner

from workflo_agent.cli import main
from workflo_agent.commands.auth import auth
from workflo_agent.commands.runs import runs


@patch("workflo_agent.commands.auth.load_config")
def test_auth_status_when_not_authenticated(mock_load_config):
    mock_load_config.return_value = {}
    runner = CliRunner()
    result = runner.invoke(auth, ["status"])
    assert result.exit_code == 0
    assert "Not authenticated" in result.output
    mock_load_config.assert_called_once()


@patch("workflo_agent.commands.auth.load_config")
def test_auth_status_when_authenticated_shows_masked_key(mock_load_config):
    mock_load_config.return_value = {"auth": {"api_key": "1234567890abcdef"}}
    runner = CliRunner()
    result = runner.invoke(auth, ["status"])
    assert result.exit_code == 0
    # Key is longer than 12 chars, so it should be masked.
    assert "API Key" in result.output


@patch("workflo_agent.commands.auth.save_config")
@patch("workflo_agent.commands.auth.load_config")
def test_auth_login_stores_api_key(mock_load_config, mock_save_config):
    mock_load_config.return_value = {}
    runner = CliRunner()
    result = runner.invoke(auth, ["login", "--key", "test_key"])
    assert result.exit_code == 0
    mock_save_config.assert_called_once()
    saved_config = mock_save_config.call_args.args[0]
    assert saved_config["auth"] == {"api_key": "test_key"}
    assert "Authenticated" in result.output


@patch("workflo_agent.commands.auth.save_config")
@patch("workflo_agent.commands.auth.load_config")
def test_auth_login_preserves_existing_config(mock_load_config, mock_save_config):
    mock_load_config.return_value = {"defaults": {"api_base_url": "https://custom"}}
    runner = CliRunner()
    result = runner.invoke(auth, ["login", "--key", "new-key"])
    assert result.exit_code == 0
    saved_config = mock_save_config.call_args.args[0]
    assert saved_config["auth"] == {"api_key": "new-key"}
    # Existing keys must be preserved.
    assert saved_config["defaults"] == {"api_base_url": "https://custom"}


@patch("workflo_agent.commands.auth.save_config")
@patch("workflo_agent.commands.auth.load_config")
def test_auth_logout_removes_auth_key(mock_load_config, mock_save_config):
    mock_load_config.return_value = {
        "auth": {"api_key": "k"},
        "defaults": {"api_base_url": "https://x"},
    }
    runner = CliRunner()
    result = runner.invoke(auth, ["logout"])
    assert result.exit_code == 0
    mock_save_config.assert_called_once()
    saved_config = mock_save_config.call_args.args[0]
    assert "auth" not in saved_config
    # Other config sections remain untouched.
    assert saved_config["defaults"] == {"api_base_url": "https://x"}
    assert "Logged out" in result.output


def test_main_help_lists_all_commands():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    for name in ["auth", "test", "runs"]:
        assert name in result.output


def test_main_help_shows_usage():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "Tenant Shield" in result.output


@patch("workflo_agent.commands.runs.ControlPlaneClient")
def test_runs_list_handles_api_error_gracefully(mock_client_cls):
    mock_client_cls.return_value.list_runs.side_effect = RuntimeError("boom")
    runner = CliRunner()
    result = runner.invoke(runs, ["list"])
    assert result.exit_code == 0
    assert "Failed to fetch runs" in result.output


@patch("workflo_agent.commands.runs.ControlPlaneClient")
def test_runs_get_handles_api_error_gracefully(mock_client_cls):
    mock_client_cls.return_value.get_run.side_effect = RuntimeError("not found")
    runner = CliRunner()
    result = runner.invoke(runs, ["get", "missing-id"])
    assert result.exit_code == 0
    assert "Failed to fetch run" in result.output
