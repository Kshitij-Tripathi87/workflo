"""Tests for workflo config commands and LLM settings management."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from workflo_cli.main import cli
from workflo_cli.config_commands import (
    _config_dir,
    _config_path,
    _load_config,
    _save_config,
    _validate_dot_key,
    _coerce_value,
    _redact,
    load_llm_settings,
    _DEFAULT_CONFIG,
)


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def temp_config_dir(tmp_path, monkeypatch):
    """Isolate config directory for each test using WORKFLO_CONFIG_DIR."""
    config_dir = tmp_path / ".workflo"
    monkeypatch.setenv("WORKFLO_CONFIG_DIR", str(config_dir))
    return config_dir


class TestConfigInternal:
    """Unit tests for config helper functions."""

    def test_config_dir_respects_env_var(self, temp_config_dir):
        assert _config_dir() == temp_config_dir

    def test_config_path(self, temp_config_dir):
        assert _config_path() == temp_config_dir / "config.yaml"

    def test_validate_dot_key_valid(self):
        assert _validate_dot_key("llm.base_url") == ("llm", "base_url")
        assert _validate_dot_key("llm.api_key") == ("llm", "api_key")
        assert _validate_dot_key("llm.model") == ("llm", "model")
        assert _validate_dot_key("sandbox.timeout") == ("sandbox", "timeout")
        assert _validate_dot_key("sandbox.memory") == ("sandbox", "memory")
        assert _validate_dot_key("sandbox.cpu") == ("sandbox", "cpu")

    def test_validate_dot_key_empty(self):
        import click
        with pytest.raises(click.BadParameter, match="must not be empty"):
            _validate_dot_key("")
        with pytest.raises(click.BadParameter, match="must not be empty"):
            _validate_dot_key("   ")

    def test_validate_dot_key_no_dot(self):
        import click
        with pytest.raises(click.BadParameter, match="SECTION.FIELD"):
            _validate_dot_key("base_url")

    def test_validate_dot_key_too_many_dots(self):
        import click
        with pytest.raises(click.BadParameter, match="SECTION.FIELD"):
            _validate_dot_key("llm.deep.base_url")

    def test_validate_dot_key_unknown_section(self):
        import click
        with pytest.raises(click.BadParameter, match="Unknown config section"):
            _validate_dot_key("database.url")

    def test_validate_dot_key_unknown_field(self):
        import click
        with pytest.raises(click.BadParameter, match="Unknown config key"):
            _validate_dot_key("llm.unknown_field")

    def test_coerce_value_numeric(self):
        assert _coerce_value("sandbox.timeout", "900") == 900
        assert _coerce_value("sandbox.memory", "4096") == 4096
        assert _coerce_value("sandbox.cpu", "4.0") == 4.0
        assert _coerce_value("sandbox.cpu", "2") == 2.0

    def test_coerce_value_invalid_numeric(self):
        import click
        with pytest.raises(click.BadParameter, match="must be an integer"):
            _coerce_value("sandbox.timeout", "not_a_number")
        with pytest.raises(click.BadParameter, match="must be a number"):
            _coerce_value("sandbox.cpu", "abc")

    def test_coerce_value_strings_unchanged(self):
        assert _coerce_value("llm.base_url", "http://localhost:11434/v1") == "http://localhost:11434/v1"
        assert _coerce_value("llm.api_key", "sk-secret-123") == "sk-secret-123"
        assert _coerce_value("llm.model", "qwen2.5-coder:7b") == "qwen2.5-coder:7b"

    def test_redact_secrets(self):
        assert _redact("llm.api_key", "sk-123456789") == "sk-1****"
        assert _redact("llm.api_key", "short") == "shor****"
        assert _redact("llm.api_key", "abc") == "abc"  # <= 4 chars shown as-is

    def test_redact_non_secrets_unchanged(self):
        assert _redact("llm.base_url", "http://localhost:11434/v1") == "http://localhost:11434/v1"
        assert _redact("llm.model", "qwen2.5-coder:7b") == "qwen2.5-coder:7b"
        assert _redact("sandbox.timeout", 600) == "600"


class TestConfigCommands:
    """CLI integration tests for `workflo config` commands."""

    def test_config_help(self, runner):
        result = runner.invoke(cli, ["config", "--help"])
        assert result.exit_code == 0
        assert "init" in result.output
        assert "set" in result.output
        assert "get" in result.output
        assert "list" in result.output
        assert "path" in result.output

    def test_config_init(self, runner, temp_config_dir):
        result = runner.invoke(cli, ["config", "init"])
        assert result.exit_code == 0
        assert "Config created" in result.output
        assert (temp_config_dir / "config.yaml").exists()

        # Check default values are populated
        settings = load_llm_settings()
        assert settings["base_url"] == "http://localhost:11434/v1"
        assert settings["model"] == "qwen2.5-coder:7b"
        assert settings["api_key"] == "placeholder-key-configure-me"

    def test_config_init_already_exists_fails_without_force(self, runner, temp_config_dir):
        runner.invoke(cli, ["config", "init"])
        result = runner.invoke(cli, ["config", "init"])
        assert result.exit_code == 1
        assert "already exists" in result.output

    def test_config_init_with_force_overwrites(self, runner, temp_config_dir):
        runner.invoke(cli, ["config", "init"])
        runner.invoke(cli, ["config", "set", "llm.model", "custom-model"])
        # Force re-init
        result = runner.invoke(cli, ["config", "init", "--force"])
        assert result.exit_code == 0
        settings = load_llm_settings()
        assert settings["model"] == "qwen2.5-coder:7b"  # Reset to default

    def test_config_set_and_get(self, runner, temp_config_dir):
        runner.invoke(cli, ["config", "init"])
        set_res = runner.invoke(cli, ["config", "set", "llm.base_url", "http://my-ollama:11434/v1"])
        assert set_res.exit_code == 0
        assert "Set llm.base_url = http://my-ollama:11434/v1" in set_res.output

        get_res = runner.invoke(cli, ["config", "get", "llm.base_url"])
        assert get_res.exit_code == 0
        assert "llm.base_url = http://my-ollama:11434/v1" in get_res.output

    def test_config_set_api_key_redacted_in_output(self, runner, temp_config_dir):
        runner.invoke(cli, ["config", "init"])
        set_res = runner.invoke(cli, ["config", "set", "llm.api_key", "sk-super-secret-key-12345"])
        assert set_res.exit_code == 0
        assert "sk-s****" in set_res.output
        assert "super-secret" not in set_res.output

    def test_config_get_api_key_redacted(self, runner, temp_config_dir):
        runner.invoke(cli, ["config", "init"])
        runner.invoke(cli, ["config", "set", "llm.api_key", "sk-super-secret-key-12345"])
        get_res = runner.invoke(cli, ["config", "get", "llm.api_key"])
        assert get_res.exit_code == 0
        assert "sk-s****" in get_res.output
        assert "super-secret" not in get_res.output

    def test_config_get_unset_key(self, runner, temp_config_dir):
        # Empty config
        result = runner.invoke(cli, ["config", "get", "llm.base_url"])
        assert result.exit_code == 1
        assert "not set" in result.output

    def test_config_list(self, runner, temp_config_dir):
        runner.invoke(cli, ["config", "init"])
        result = runner.invoke(cli, ["config", "list"])
        assert result.exit_code == 0
        assert "[llm]" in result.output
        assert "base_url" in result.output
        assert "model" in result.output
        assert "[sandbox]" in result.output
        assert "timeout" in result.output
        # API key must be redacted in list
        assert "****" in result.output

    def test_config_list_empty(self, runner, temp_config_dir):
        result = runner.invoke(cli, ["config", "list"])
        assert result.exit_code == 0
        assert "No config found" in result.output

    def test_config_path_command(self, runner, temp_config_dir):
        result = runner.invoke(cli, ["config", "path"])
        assert result.exit_code == 0
        assert str(temp_config_dir / "config.yaml") in result.output


class TestLoadLLMSettings:
    """Tests for load_llm_settings() helper function."""

    def test_load_llm_settings_no_config(self, temp_config_dir):
        settings = load_llm_settings()
        assert settings == {"base_url": "", "api_key": "", "model": ""}

    def test_load_llm_settings_with_config(self, runner, temp_config_dir):
        runner.invoke(cli, ["config", "init"])
        runner.invoke(cli, ["config", "set", "llm.base_url", "https://api.openai.com/v1"])
        runner.invoke(cli, ["config", "set", "llm.api_key", "sk-custom-api-key-999"])
        runner.invoke(cli, ["config", "set", "llm.model", "gpt-4o"])

        settings = load_llm_settings()
        assert settings["base_url"] == "https://api.openai.com/v1"
        assert settings["api_key"] == "sk-custom-api-key-999"
        assert settings["model"] == "gpt-4o"
