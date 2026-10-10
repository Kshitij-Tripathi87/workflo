"""Regression tests for the deep-tier LLM placeholder safety path.

The demo-critical guarantee: when a user configures a *placeholder* LLM
endpoint, `workflo run --deep-test` must fail FAST with a message naming the
fix — never hand the fake URL to the sandbox and hang/confuse.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner
from workflo_cli.main import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def clean_llm_config(monkeypatch, tmp_path):
    """Isolate the LLM config to a temp dir and clear it after."""
    monkeypatch.setenv("WORKFLO_CONFIG_DIR", str(tmp_path))
    from workflo_cli import llm_config

    yield llm_config
    llm_config.clear_llm_config()


@pytest.fixture
def configured_placeholder(clean_llm_config):
    clean_llm_config.set_llm_config(
        base_url="https://your-model.example.com/v1",
        api_key="wf-placeholder-key",
    )
    return clean_llm_config


class TestConfigLLM:
    def test_set_and_get_redacted(self, runner, clean_llm_config):
        result = runner.invoke(
            cli,
            [
                "config",
                "set-llm",
                "--base-url", "https://inference.acme.com/v1",
                "--api-key", "wf_live_secret123",
            ],
        )
        assert result.exit_code == 0, result.output

        out = runner.invoke(cli, ["config", "get-llm"])
        assert out.exit_code == 0
        data = json.loads(out.output)
        assert data["llm"]["configured"] is True
        assert data["llm"]["base_url"] == "https://inference.acme.com/v1"
        # The full key must never appear in any display surface.
        assert "wf_live_secret123" not in out.output
        assert data["llm"]["api_key"].startswith("wf_l")
        assert "****" in data["llm"]["api_key"]

    def test_placeholder_detection(self, runner, configured_placeholder):
        out = runner.invoke(cli, ["config", "get-llm"])
        data = json.loads(out.output)
        assert data["llm"]["is_placeholder"] is True

    def test_set_rejects_bad_url(self, runner, clean_llm_config):
        result = runner.invoke(
            cli,
            ["config", "set-llm", "--base-url", "ftp://nope", "--api-key", "k"],
        )
        assert result.exit_code != 0

    def test_set_rejects_empty_key(self, runner, clean_llm_config):
        result = runner.invoke(
            cli,
            ["config", "set-llm", "--base-url", "https://x.com/v1", "--api-key", "  "],
        )
        assert result.exit_code != 0


class TestDeepTestPlaceholderFailFast:
    """The reviewer's #1 demo risk: placeholder config must fail FAST."""

    def test_dry_run_fails_fast_with_placeholder(self, runner, configured_placeholder):
        result = runner.invoke(
            cli,
            ["run", "--repo", "https://github.com/pallets/click.git", "--deep-test", "--dry-run"],
        )
        assert result.exit_code != 0
        assert "workflo config set-llm" in result.output
        # No plan JSON must leak — we failed before producing one.
        assert '"mode": "dry-run"' not in result.output

    def test_real_run_fails_fast_with_placeholder(self, runner, configured_placeholder):
        result = runner.invoke(
            cli,
            ["run", "--repo", "https://github.com/pallets/click.git", "--deep-test"],
        )
        assert result.exit_code != 0
        assert "workflo config set-llm" in result.output

    def test_no_config_uses_embedded_llamacpp_path(self, runner, clean_llm_config):
        """No hosted config uses the pinned embedded model; do not hard-fail."""
        result = runner.invoke(
            cli,
            ["run", "--repo", "https://github.com/pallets/click.git", "--deep-test", "--dry-run"],
        )
        assert result.exit_code == 0
        # stdout holds the plan JSON; stderr identifies the embedded model path.
        assert '"mode": "dry-run"' in result.output
        assert '"configured": false' in result.output

    def test_real_config_shows_redacted_in_dry_run(self, runner, clean_llm_config):
        clean_llm_config.set_llm_config(
            base_url="https://inference.acme.com/v1",
            api_key="wf_live_secret123",
        )
        result = runner.invoke(
            cli,
            ["run", "--repo", "https://github.com/pallets/click.git", "--deep-test", "--dry-run"],
        )
        assert result.exit_code == 0
        plan = json.loads(result.output)
        assert plan["llm"]["configured"] is True
        assert plan["llm"]["is_placeholder"] is False
        assert "wf_live_secret123" not in result.output


class TestGatewayModeEndpointValidation:
    def test_gateway_mode_uses_gateway_health_and_api_key_header(
        self, clean_llm_config, monkeypatch
    ):
        """Gateway keys must use X-API-Key and the gateway's health route."""
        import httpx

        seen = {}

        class Response:
            status_code = 200

            @staticmethod
            def json():
                return {"status": "configured", "model": "qa-model"}

        class Client:
            def __init__(self, timeout):
                seen["timeout"] = timeout

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def get(self, url, headers):
                seen["url"] = url
                seen["headers"] = headers
                return Response()

        monkeypatch.setattr(httpx, "Client", Client)
        cfg = clean_llm_config.LLMConfig(
            base_url="https://control.example.test",
            gateway_url="https://gateway.example.test",
            model="qa-model",
            timeout_seconds=10,
            api_key="wf_gateway_key",
            mode="gateway",
        )

        ok, message = clean_llm_config.validate_llm_key(cfg)

        assert ok is True
        assert "200" in message
        assert seen["url"] == "https://gateway.example.test/v1/inference/health"
        assert seen["headers"] == {"X-API-Key": "wf_gateway_key"}
        assert "Authorization" not in seen["headers"]

    def test_gateway_mode_fails_closed_when_key_is_rejected(
        self, clean_llm_config, monkeypatch
    ):
        import httpx

        class Response:
            status_code = 401

        class Client:
            def __init__(self, timeout):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def get(self, url, headers):
                return Response()

        monkeypatch.setattr(httpx, "Client", Client)
        cfg = clean_llm_config.LLMConfig(
            base_url="https://control.example.test",
            gateway_url=None,
            model="qa-model",
            timeout_seconds=10,
            api_key="bad-key",
            mode="gateway",
        )

        ok, message = clean_llm_config.validate_llm_key(cfg)

        assert ok is False
        assert "rejected" in message
        assert "401" in message
