"""CLI tests via click's CliRunner with an injected fake router (no GPU, no llama-server)."""

import json

import pytest
from click.testing import CliRunner
from workflo_ai_integration import cli as cli_module
from workflo_ai_integration.model_router import (
    AdapterLoadError,
    GenerationValidationError,
)

from serving_fakes import FakeRouter


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture()
def fake_router(monkeypatch) -> FakeRouter:
    router = FakeRouter()
    monkeypatch.setattr(cli_module, "build_router", lambda *args, **kwargs: router)
    return router


def test_generate_test_gen_happy_path(runner, fake_router):
    result = runner.invoke(
        cli_module.cli,
        ["generate", "--task", "test_gen", "--prompt", "Module: app/x.py\nFunction: f() -> int\nBehavior: returns 1."],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["task"] == "test-gen"
    assert payload["result"]["framework"] == "pytest"
    assert isinstance(payload["latency_ms"], int)
    assert "artifacts" not in payload  # opt-in only
    # default (trained) system prompt was injected
    assert "WriteTestCall schema" in fake_router.calls[0][1]


def test_generate_accepts_hyphen_alias_and_reasoning_task(runner, fake_router):
    result = runner.invoke(
        cli_module.cli,
        ["generate", "--task", "reasoning", "--prompt", "Function: f()\nPropose an invariant."],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["task"] == "reasoning"
    assert payload["result"]["category"] == "business_logic"


def test_generate_custom_system_prompt_overrides_default(runner, fake_router):
    result = runner.invoke(
        cli_module.cli,
        ["generate", "--task", "test_gen", "--system-prompt", "custom system", "--prompt", "p"],
    )
    assert result.exit_code == 0, result.output
    assert fake_router.calls[0][1] == "custom system"


def test_generate_with_artifacts_opt_in(runner, fake_router, monkeypatch, tmp_path):
    from serving_fakes import build_fake_registry

    monkeypatch.setattr(cli_module, "load_registry", lambda: build_fake_registry(tmp_path))
    result = runner.invoke(
        cli_module.cli,
        ["generate", "--task", "test_gen", "--prompt", "p", "--with-artifacts"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["artifacts"]["model"]["id"] == "fake-base"


def test_generate_compact_output(runner, fake_router):
    result = runner.invoke(
        cli_module.cli,
        ["generate", "--task", "test_gen", "--prompt", "p", "--compact"],
    )
    assert result.exit_code == 0
    assert "\n" not in result.output.strip()
    json.loads(result.output)  # still valid JSON


def test_generate_validation_failure_exit_1(runner, monkeypatch):
    class Rejecting(FakeRouter):
        def generate_for_task(self, task, system_prompt, user_prompt):
            raise GenerationValidationError("compile-check failed: disallowed call: eval")

    monkeypatch.setattr(cli_module, "build_router", lambda *args, **kwargs: Rejecting())
    result = runner.invoke(cli_module.cli, ["generate", "--task", "test_gen", "--prompt", "p"])
    assert result.exit_code == 1
    err = json.loads(result.output)
    assert err["error"] == "generation_validation_failed"


def test_generate_server_down_exit_2(runner, monkeypatch):
    class Down(FakeRouter):
        def generate_for_task(self, task, system_prompt, user_prompt):
            raise AdapterLoadError("failed to list llama.cpp adapters")

    monkeypatch.setattr(cli_module, "build_router", lambda *args, **kwargs: Down())
    result = runner.invoke(cli_module.cli, ["generate", "--task", "test_gen", "--prompt", "p"])
    assert result.exit_code == 2
    assert json.loads(result.output)["error"] == "adapter_load_failed"


def test_generate_invalid_base_url_exit_2(runner, monkeypatch):
    """RouterConfig's loopback guard rejects non-loopback URLs before any I/O.
    Captures the real builder before the fake fixture patches it."""
    import importlib

    fresh = importlib.reload(cli_module)
    real_builder = fresh.build_router
    monkeypatch.setattr(cli_module, "build_router", real_builder)
    result = runner.invoke(
        cli_module.cli,
        ["generate", "--task", "test_gen", "--prompt", "p", "--base-url", "http://evil.example.com:8080"],
    )
    assert result.exit_code == 2
    assert json.loads(result.output)["error"] == "invalid_configuration"


def test_report_inline_results(runner, fake_router):
    result = runner.invoke(
        cli_module.cli,
        ["report", "--results", '{"passed": 97, "failed": 3}'],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["task"] == "reporting"
    assert "summary" in payload["result"]


def test_report_from_file(runner, fake_router, tmp_path):
    f = tmp_path / "results.json"
    f.write_text(json.dumps({"passed": 1, "failed": 0}), encoding="utf-8")
    result = runner.invoke(cli_module.cli, ["report", "--file", str(f)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["result"]["summary"]


def test_report_rejects_missing_and_duplicate_input(runner, fake_router, tmp_path):
    missing = runner.invoke(cli_module.cli, ["report"])
    assert missing.exit_code == 2
    assert json.loads(missing.output)["error"] == "invalid_usage"
    f = tmp_path / "results.json"
    f.write_text("{}", encoding="utf-8")
    dup = runner.invoke(cli_module.cli, ["report", "--results", "{}", "--file", str(f)])
    assert dup.exit_code == 2
    assert json.loads(dup.output)["error"] == "invalid_usage"
    nonexistent = runner.invoke(cli_module.cli, ["report", "--file", "nope.json"])
    assert nonexistent.exit_code == 2  # click path validation


def test_report_rejects_non_object_and_malformed_json(runner, fake_router):
    arr = runner.invoke(cli_module.cli, ["report", "--results", "[1,2]"])
    assert arr.exit_code == 2
    assert json.loads(arr.output)["error"] == "invalid_results_json"
    bad = runner.invoke(cli_module.cli, ["report", "--results", "not json"])
    assert bad.exit_code == 2


def test_report_rejects_oversized_results(runner, fake_router):
    blob = json.dumps({"blob": "x" * 300_000})
    result = runner.invoke(cli_module.cli, ["report", "--results", blob])
    assert result.exit_code == 2
    assert json.loads(result.output)["error"] == "results_too_large"


def test_health_ok(runner, fake_router):
    result = runner.invoke(cli_module.cli, ["health"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload == {
        "status": "ok",
        "adapter_ids": {"reporting": 2, "reasoning": 1, "test-gen": 0},
    }


def test_health_degraded_exit_2(runner, monkeypatch):
    class Down(FakeRouter):
        def discover_adapters(self, force=False):
            raise AdapterLoadError("failed to list llama.cpp adapters")

    monkeypatch.setattr(cli_module, "build_router", lambda *args, **kwargs: Down())
    result = runner.invoke(cli_module.cli, ["health"])
    assert result.exit_code == 2
    assert json.loads(result.output)["status"] == "degraded"


def test_unknown_task_rejected_by_click(runner, fake_router):
    result = runner.invoke(cli_module.cli, ["generate", "--task", "web", "--prompt", "p"])
    assert result.exit_code == 2  # click usage error
