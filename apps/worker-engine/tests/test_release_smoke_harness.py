"""Exercise release smoke plumbing without starting a real llama.cpp process."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from workflo_ai_integration import GenerationValidationError

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "release" / "llamacpp_worker_smoke.py"


def _load_smoke_module():
    spec = importlib.util.spec_from_file_location("llamacpp_worker_smoke", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_model_stage(streamer, repo_dir, probe_groups):
    assert probe_groups == ["aggressive"]
    streamer.log("verifying pinned GGUF artifacts")
    streamer.log("discovered required llama.cpp adapters")
    streamer.log("wrote validated llama.cpp pytest file")
    generated = Path(repo_dir) / ".workflo" / "generated-tests"
    generated.mkdir(parents=True)
    (generated / "test_calculator.py").write_text("def test_divide(): pass\n")
    provenance = {
        "model": "fixture-model",
        "server_image": "image@sha256:" + "a" * 64,
        "base_model_sha256": "b" * 64,
        "adapter_sha256": {
            "test-gen": "c" * 64,
            "reasoning": "d" * 64,
            "reporting": "e" * 64,
        },
        "requests": 2,
        "inference_seconds": 0.1,
        "endpoint_scope": "loopback",
        "source_code_included": True,
        "error": None,
    }
    return True, None, [{"kind": "validated-test"}], generated, provenance


def _passing_reporting_report():
    return {
        "passed": True,
        "adapter": "reporting",
        "schema_valid": True,
        "requests": 1,
        "inference_seconds": 0.1,
        "elapsed_seconds": 0.2,
        "teardown_verified": True,
        "endpoint_scope": "loopback",
        "input_scope": "synthetic-structured-results-only",
        "source_code_included": False,
        "narrative_recorded": False,
        "error": None,
        "identity": {
            "model": "fixture-model",
            "server_image": "image@sha256:" + "a" * 64,
            "base_model_sha256": "b" * 64,
            "adapter_sha256": {
                "test-gen": "c" * 64,
                "reasoning": "d" * 64,
                "reporting": "e" * 64,
            },
        },
    }


def test_smoke_script_writes_source_free_passing_reports(monkeypatch, tmp_path):
    module = _load_smoke_module()
    output = tmp_path / "llamacpp-worker-smoke.json"
    reporting_output = tmp_path / "reporting-smoke.json"

    monkeypatch.setattr(module, "_run_llamacpp_model_stage", _fake_model_stage)
    monkeypatch.setattr(module, "_run_reporting_smoke", _passing_reporting_report)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--out", str(output)])

    assert module.main() == 0
    report = json.loads(output.read_text())
    reporting = json.loads(reporting_output.read_text())
    assert report["passed"] is True
    assert report["worker_passed"] is True
    assert report["reporting_passed"] is True
    assert report["teardown_verified"] is True
    assert all(report["required_log_markers"].values())
    assert report["generated_tests_count"] == 1
    assert reporting["schema_valid"] is True
    assert reporting["narrative_recorded"] is False

    serialized = output.read_text() + reporting_output.read_text()
    assert "test_calculator.py" not in serialized
    assert "def divide" not in serialized
    assert "def test_divide" not in serialized
    assert "summary text from model" not in serialized


def test_malformed_reporting_response_makes_smoke_fail(monkeypatch, tmp_path):
    module = _load_smoke_module()
    output = tmp_path / "llamacpp-worker-smoke.json"
    reporting_output = tmp_path / "reporting-smoke.json"
    config = SimpleNamespace(
        model_id="fixture-model",
        image="image@sha256:" + "a" * 64,
        base_model=SimpleNamespace(sha256="b" * 64),
        adapters={
            "test-gen": SimpleNamespace(sha256="c" * 64),
            "reasoning": SimpleNamespace(sha256="d" * 64),
            "reporting": SimpleNamespace(sha256="e" * 64),
        },
        request_timeout_seconds=1.0,
    )
    runtime = MagicMock()
    runtime.base_url = "http://127.0.0.1:8080"
    runtime.stop.return_value = True
    router = MagicMock()
    router.discover_adapters.return_value = {
        "test-gen": 0,
        "reasoning": 1,
        "reporting": 2,
    }
    router.generate_report.side_effect = GenerationValidationError(
        "schema validation failed (1 errors)"
    )

    monkeypatch.setattr(module, "_run_llamacpp_model_stage", _fake_model_stage)
    monkeypatch.setattr(
        module.LlamaCppRuntimeConfig,
        "from_env",
        classmethod(lambda cls: config),
    )
    monkeypatch.setattr(module, "LlamaCppRuntime", lambda cfg: runtime)
    monkeypatch.setattr(module, "ModelRouter", lambda *args, **kwargs: router)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--out", str(output)])

    assert module.main() == 1
    worker_report = json.loads(output.read_text())
    reporting_report = json.loads(reporting_output.read_text())
    assert worker_report["worker_passed"] is True
    assert worker_report["reporting_passed"] is False
    assert worker_report["passed"] is False
    assert reporting_report["schema_valid"] is False
    assert reporting_report["teardown_verified"] is True
    assert "GenerationValidationError" in reporting_report["error"]
    assert reporting_report["narrative_recorded"] is False
