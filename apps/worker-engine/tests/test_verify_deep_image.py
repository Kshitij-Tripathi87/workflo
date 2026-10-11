from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "release" / "verify_deep_image.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("verify_deep_image", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _manifest(tmp_path: Path) -> tuple[Path, dict]:
    document = {
        "version": 1,
        "llama_cpp_image": "base.example/llama@sha256:" + "a" * 64,
        "model": {"id": "frozen-model", "sha256": "b" * 64},
        "adapters": {
            "test-gen": {"sha256": "c" * 64},
            "reasoning": {"sha256": "d" * 64},
            "reporting": {"sha256": "e" * 64},
        },
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(document))
    return path, document


def test_verifier_binds_labels_binary_artifacts_and_commit(monkeypatch, tmp_path):
    module = _load_module()
    manifest_path, manifest = _manifest(tmp_path)
    deep_image = "registry.example/deep@sha256:" + "f" * 64
    commit = "1" * 40
    report = tmp_path / "report.json"
    labels = module._expected_labels(manifest, commit)
    inspection = [{
        "Id": "sha256:" + "9" * 64,
        "RepoDigests": [deep_image],
        "Config": {"Labels": labels},
    }]
    embedded = {
        "binary_sha256": "8" * 64,
        "artifact_sha256": {
            "base": "b" * 64,
            "test-gen": "c" * 64,
            "reasoning": "d" * 64,
            "reporting": "e" * 64,
        },
        "base_image": manifest["llama_cpp_image"],
        "model_id": manifest["model"]["id"],
    }

    def fake_run(command, *, capture=True):
        if command[:2] == ["docker", "pull"]:
            return SimpleNamespace(stdout="")
        if command[:3] == ["docker", "image", "inspect"]:
            return SimpleNamespace(stdout=json.dumps(inspection))
        assert command[:2] == ["docker", "run"]
        assert "--network" in command and "none" in command
        assert "--read-only" in command
        return SimpleNamespace(stdout=json.dumps(embedded))

    monkeypatch.setattr(module, "_run", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT), "--image", deep_image, "--manifest", str(manifest_path),
            "--commit", commit, "--report", str(report),
        ],
    )

    assert module.main() == 0
    evidence = json.loads(report.read_text())
    assert evidence["passed"] is True
    assert evidence["label_binding_verified"] is True
    assert evidence["embedded_hashes_verified"] is True
    assert evidence["binary_sha256"] == "8" * 64


def test_verifier_fails_closed_on_label_drift(monkeypatch, tmp_path):
    module = _load_module()
    manifest_path, _ = _manifest(tmp_path)
    deep_image = "registry.example/deep@sha256:" + "f" * 64
    report = tmp_path / "report.json"

    monkeypatch.setattr(
        module,
        "_run",
        lambda *args, **kwargs: SimpleNamespace(stdout=json.dumps([{
            "Id": "sha256:" + "9" * 64,
            "RepoDigests": [deep_image],
            "Config": {"Labels": {}},
        }])),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT), "--image", deep_image, "--manifest", str(manifest_path),
            "--commit", "1" * 40, "--report", str(report),
        ],
    )

    assert module.main() == 1
    evidence = json.loads(report.read_text())
    assert evidence["passed"] is False
    assert evidence["failure_class"] == "ValueError"
