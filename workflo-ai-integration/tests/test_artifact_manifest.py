from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_artifact_manifest.py"
spec = importlib.util.spec_from_file_location("verify_artifact_manifest", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def _entry(root: Path, name: str) -> dict:
    path = root / f"{name}.gguf"
    body = name.encode()
    path.write_bytes(body)
    return {
        "source": f"https://artifacts.example.invalid/{name}.gguf",
        "path": path.name,
        "sha256": hashlib.sha256(body).hexdigest(),
    }


def _manifest(tmp_path: Path) -> Path:
    doc = {
        "version": 1,
        "llama_cpp_image": "image@sha256:" + "a" * 64,
        "model": {"id": "qwen-test", **_entry(tmp_path, "base")},
        "adapters": {
            name: _entry(tmp_path, name)
            for name in ("test-gen", "reasoning", "reporting")
        },
    }
    path = tmp_path / "model-artifacts.json"
    path.write_text(json.dumps(doc))
    return path


def test_manifest_accepts_exact_artifacts(tmp_path, monkeypatch):
    manifest = _manifest(tmp_path)
    report = tmp_path / "report.json"
    monkeypatch.setattr(
        "sys.argv", [str(SCRIPT), str(manifest), "--report", str(report)]
    )
    assert module.main() == 0
    evidence = json.loads(report.read_text())
    assert evidence["passed"] is True
    assert evidence["artifact_count"] == 4
    assert evidence["environment_binding_verified"] is False
    assert "path" not in report.read_text()


def _set_runtime_env(manifest: Path, monkeypatch) -> None:
    doc = json.loads(manifest.read_text())
    root = manifest.parent
    values = {
        "WORKFLO_LLAMACPP_IMAGE": doc["llama_cpp_image"],
        "WORKFLO_LLAMACPP_MODEL_ID": doc["model"]["id"],
        "WORKFLO_LLAMACPP_BASE_GGUF": str(root / doc["model"]["path"]),
        "WORKFLO_LLAMACPP_BASE_SHA256": doc["model"]["sha256"],
    }
    for name, entry in doc["adapters"].items():
        prefix = name.upper().replace("-", "_")
        values[f"WORKFLO_LLAMACPP_{prefix}_GGUF"] = str(root / entry["path"])
        values[f"WORKFLO_LLAMACPP_{prefix}_SHA256"] = entry["sha256"]
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def test_manifest_accepts_matching_runtime_environment(tmp_path, monkeypatch):
    manifest = _manifest(tmp_path)
    _set_runtime_env(manifest, monkeypatch)
    monkeypatch.setattr("sys.argv", [str(SCRIPT), str(manifest), "--check-env"])
    assert module.main() == 0


def test_manifest_rejects_runtime_environment_drift(tmp_path, monkeypatch):
    manifest = _manifest(tmp_path)
    _set_runtime_env(manifest, monkeypatch)
    monkeypatch.setenv("WORKFLO_LLAMACPP_REASONING_SHA256", "f" * 64)
    monkeypatch.setattr("sys.argv", [str(SCRIPT), str(manifest), "--check-env"])
    assert module.main() == 1


def test_manifest_rejects_tampered_artifact(tmp_path, monkeypatch):
    manifest = _manifest(tmp_path)
    (tmp_path / "reasoning.gguf").write_bytes(b"tampered")
    monkeypatch.setattr("sys.argv", [str(SCRIPT), str(manifest)])
    assert module.main() == 1


def test_manifest_rejects_duplicate_artifact_path(tmp_path, monkeypatch):
    manifest = _manifest(tmp_path)
    doc = json.loads(manifest.read_text())
    doc["adapters"]["reporting"] = dict(doc["adapters"]["reasoning"])
    manifest.write_text(json.dumps(doc))
    monkeypatch.setattr("sys.argv", [str(SCRIPT), str(manifest)])
    assert module.main() == 1


def test_manifest_rejects_unpinned_image(tmp_path, monkeypatch):
    manifest = _manifest(tmp_path)
    doc = json.loads(manifest.read_text())
    doc["llama_cpp_image"] = "image:latest"
    manifest.write_text(json.dumps(doc))
    monkeypatch.setattr("sys.argv", [str(SCRIPT), str(manifest)])
    assert module.main() == 1
