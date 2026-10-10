"""Exercise the release smoke report plumbing without starting llama.cpp.

The protected acceptance workflow still calls the real worker path; this test
only guards the script's argument handling, report shape, log-marker checks,
and source-free artifact output.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "release" / "llamacpp_worker_smoke.py"


def _load_smoke_module():
    spec = importlib.util.spec_from_file_location("llamacpp_worker_smoke", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_smoke_script_writes_source_free_passing_report(monkeypatch, tmp_path):
    module = _load_smoke_module()
    output = tmp_path / "smoke.json"

    def fake_model_stage(streamer, repo_dir, probe_groups):
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
            "loopback_only": True,
            "source_included": True,
            "error": None,
        }
        return True, None, [{"kind": "model-suggested-test"}], generated, provenance

    monkeypatch.setattr(module, "_run_llamacpp_model_stage", fake_model_stage)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--out", str(output)])

    assert module.main() == 0
    report = json.loads(output.read_text())
    assert report["passed"] is True
    assert report["teardown_verified"] is True
    assert all(report["required_log_markers"].values())
    assert report["generated_tests_count"] == 1
    assert "test_calculator.py" not in output.read_text()
    serialized = output.read_text()
    assert "def divide" not in serialized
    assert "def test_divide" not in serialized
