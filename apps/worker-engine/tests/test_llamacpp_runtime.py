from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from workflo_worker.model.llamacpp_runtime import (
    GGUFArtifact,
    LlamaCppRuntime,
    LlamaCppRuntimeConfig,
    LlamaCppRuntimeError,
)


def _artifact(tmp_path: Path, name: str) -> GGUFArtifact:
    path = tmp_path / f"{name}.gguf"
    content = f"artifact:{name}".encode()
    path.write_bytes(content)
    return GGUFArtifact(name, path, hashlib.sha256(content).hexdigest())


def _config(tmp_path: Path, **overrides) -> LlamaCppRuntimeConfig:
    fields = dict(
        executable="/usr/local/bin/llama-server",
        model_id="qwen-test-q4",
        image="ghcr.io/ggml-org/llama.cpp:server@sha256:" + "a" * 64,
        base_model=_artifact(tmp_path, "base"),
        adapters={
            "test-gen": _artifact(tmp_path, "test-gen"),
            "reasoning": _artifact(tmp_path, "reasoning"),
            "reporting": _artifact(tmp_path, "reporting"),
        },
        startup_timeout_seconds=1.0,
    )
    fields.update(overrides)
    return LlamaCppRuntimeConfig(**fields)


def test_config_verifies_all_artifacts(tmp_path):
    _config(tmp_path).validate()


def test_config_rejects_missing_artifact(tmp_path):
    config = _config(tmp_path)
    config.base_model.path.unlink()
    with pytest.raises(LlamaCppRuntimeError, match="is missing"):
        config.validate()


def test_config_rejects_hash_mismatch(tmp_path):
    config = _config(tmp_path)
    bad = GGUFArtifact("base", config.base_model.path, "0" * 64)
    config = _config(tmp_path, base_model=bad)
    with pytest.raises(LlamaCppRuntimeError, match="mismatch"):
        config.validate()


def test_config_rejects_uppercase_hash_identity(tmp_path):
    config = _config(tmp_path)
    uppercase = GGUFArtifact("base", config.base_model.path, config.base_model.sha256.upper())
    with pytest.raises(LlamaCppRuntimeError, match="invalid SHA-256"):
        _config(tmp_path, base_model=uppercase).validate()


def test_config_rejects_reused_artifact_file(tmp_path):
    config = _config(tmp_path)
    adapters = dict(config.adapters)
    adapters["reporting"] = GGUFArtifact(
        "reporting", adapters["reasoning"].path, adapters["reasoning"].sha256
    )
    with pytest.raises(LlamaCppRuntimeError, match="four distinct files"):
        _config(tmp_path, adapters=adapters).validate()


def test_config_rejects_non_loopback_source_endpoint(tmp_path):
    with pytest.raises(LlamaCppRuntimeError, match="loopback"):
        _config(tmp_path, host="10.0.0.5").validate()


def test_config_requires_pinned_image_digest(tmp_path):
    with pytest.raises(LlamaCppRuntimeError, match="pinned"):
        _config(tmp_path, image="ghcr.io/ggml-org/llama.cpp:server").validate()


def test_command_loads_exact_adapters_without_slot_persistence(tmp_path):
    runtime = LlamaCppRuntime(_config(tmp_path))
    command = runtime.command
    assert command.count("--lora") == 3
    assert "--lora-init-without-apply" in command
    assert "--slot-save-path" not in command
    assert command[command.index("--host") + 1] == "127.0.0.1"
    assert command[command.index("-m") + 1].endswith("base.gguf")


class _FakeProcess:
    def __init__(self):
        self.running = True
        self.returncode = None

    def poll(self):
        return None if self.running else self.returncode

    def terminate(self):
        self.running = False
        self.returncode = 0

    def kill(self):
        self.running = False
        self.returncode = -9

    def wait(self, timeout=None):
        if self.running:
            raise AssertionError("wait called before terminate")
        return self.returncode


def test_runtime_health_then_verified_teardown(tmp_path):
    runtime = LlamaCppRuntime(_config(tmp_path))
    process = _FakeProcess()
    health = httpx.Response(200, json={"status": "ok"})
    with patch.object(runtime, "_port_open", return_value=False), patch(
        "workflo_worker.model.llamacpp_runtime.subprocess.Popen", return_value=process
    ) as popen, patch(
        "workflo_worker.model.llamacpp_runtime.httpx.get", return_value=health
    ):
        runtime.start()
        scratch = runtime._scratch
        assert scratch is not None and scratch.exists()
        assert runtime.stop() is True
        assert not scratch.exists()

    command = popen.call_args.args[0]
    assert command == runtime.command
    environment = popen.call_args.kwargs["env"]
    assert environment["HOME"].startswith(str(scratch))
    assert popen.call_args.kwargs["stdout"] is not None
    assert popen.call_args.kwargs["stderr"] is not None
