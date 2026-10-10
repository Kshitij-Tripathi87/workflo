from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

from workflo_ai_integration import AdapterLoadError, ProposeInvariantCall, WriteTestCall
from workflo_worker.executor import _run_llamacpp_model_stage
from workflo_worker.model.llamacpp_runtime import GGUFArtifact, LlamaCppRuntimeConfig


class _Streamer:
    def __init__(self):
        self.lines = []

    def log(self, message):
        self.lines.append(message)


def _artifact(tmp_path: Path, name: str) -> GGUFArtifact:
    path = tmp_path / f"{name}.gguf"
    body = name.encode()
    path.write_bytes(body)
    return GGUFArtifact(name, path, hashlib.sha256(body).hexdigest())


def _config(tmp_path: Path) -> LlamaCppRuntimeConfig:
    return LlamaCppRuntimeConfig(
        executable="llama-server",
        model_id="qwen-test",
        image="image@sha256:" + "a" * 64,
        base_model=_artifact(tmp_path, "base"),
        adapters={
            "test-gen": _artifact(tmp_path, "test-gen"),
            "reasoning": _artifact(tmp_path, "reasoning"),
            "reporting": _artifact(tmp_path, "reporting"),
        },
    )


def _runtime(config):
    runtime = MagicMock()
    runtime.base_url = "http://127.0.0.1:8080"
    runtime.stop.return_value = True
    runtime.provenance.return_value = {
        "backend": "llamacpp",
        "model": config.model_id,
        "server_image": config.image,
        "base_model_sha256": config.base_model.sha256,
        "adapter_sha256": {k: v.sha256 for k, v in config.adapters.items()},
        "endpoint_scope": "loopback",
        "source_code_included": True,
    }
    return runtime


def test_deep_stage_uses_router_and_writes_validated_test(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def add(a, b): return a + b\n")
    config = _config(tmp_path)
    runtime = _runtime(config)
    router = MagicMock()
    router.discover_adapters.return_value = {
        "test-gen": 0,
        "reasoning": 1,
        "reporting": 2,
    }
    router.generate_for_flag.return_value = WriteTestCall(
        path="tests/test_generated_add.py",
        content="def test_generated_add():\n    assert 1 + 1 == 2\n",
        rationale="exercise addition",
    )

    with patch.object(LlamaCppRuntimeConfig, "from_env", return_value=config), patch(
        "workflo_worker.executor.LlamaCppRuntime", return_value=runtime
    ), patch("workflo_worker.executor.ModelRouter", return_value=router):
        teardown, error, findings, generated_dir, provenance = _run_llamacpp_model_stage(
            _Streamer(), str(repo), ["deep"]
        )

    assert teardown is True
    assert error is None
    assert generated_dir == repo / "workflo_generated_tests" / "tests"
    generated = generated_dir / "test_generated_add.py"
    assert generated.read_text() == "def test_generated_add():\n    assert 1 + 1 == 2\n"
    router.generate_for_flag.assert_called_once()
    assert router.generate_for_flag.call_args.args[0] == "--deep-test"
    assert findings[0]["source"] == "llamacpp_test_gen_adapter"
    assert findings[0]["description"] == "validated local-model pytest file generated"
    assert findings[0]["path"] == "workflo_generated_tests/[redacted]"
    assert "test_generated_add.py" not in str(findings)
    assert "exercise addition" not in str(findings)
    assert "def test_generated_add" not in str(findings)
    assert provenance["requests"] == 1
    assert provenance["source_code_included"] is True
    runtime.start.assert_called_once()
    runtime.stop.assert_called_once()


def test_aggressive_stage_routes_reasoning_then_test_generation(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    config = _config(tmp_path)
    runtime = _runtime(config)
    router = MagicMock()
    router.discover_adapters.return_value = {
        "test-gen": 0,
        "reasoning": 1,
        "reporting": 2,
    }
    router.generate_for_flag.side_effect = [
        ProposeInvariantCall(
            description="ids remain positive",
            target="create_item",
            hypothesis_strategy="st.integers(min_value=1)",
            property_check="item.id > 0",
        ),
        WriteTestCall(
            path="test_invariant.py",
            content="def test_invariant():\n    assert 2 > 0\n",
            rationale="check positive ids",
        ),
    ]

    with patch.object(LlamaCppRuntimeConfig, "from_env", return_value=config), patch(
        "workflo_worker.executor.LlamaCppRuntime", return_value=runtime
    ), patch("workflo_worker.executor.ModelRouter", return_value=router):
        teardown, error, findings, _, provenance = _run_llamacpp_model_stage(
            _Streamer(), str(repo), ["aggressive"]
        )

    assert teardown is True and error is None
    assert [call.args[0] for call in router.generate_for_flag.call_args_list] == [
        "--aggressive-test",
        "--deep-test",
    ]
    assert findings[0]["invariant_category"] == "business_logic"
    assert "ids remain positive" not in str(findings)
    assert "create_item" not in str(findings)
    assert provenance["requests"] == 2


def test_router_failure_is_fail_closed_and_tears_down(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    config = _config(tmp_path)
    runtime = _runtime(config)
    router = MagicMock()
    router.discover_adapters.side_effect = AdapterLoadError("reasoning adapter missing")

    with patch.object(LlamaCppRuntimeConfig, "from_env", return_value=config), patch(
        "workflo_worker.executor.LlamaCppRuntime", return_value=runtime
    ), patch("workflo_worker.executor.ModelRouter", return_value=router):
        teardown, error, findings, generated, provenance = _run_llamacpp_model_stage(
            _Streamer(), str(repo), ["deep"]
        )

    assert teardown is True
    assert "reasoning adapter missing" in error
    assert findings == [] and generated is None
    assert provenance["error"] == error
    runtime.stop.assert_called_once()
