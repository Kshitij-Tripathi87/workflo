"""Tests for the fail-closed artifact registry."""

import hashlib
import json
from pathlib import Path

import pytest
from workflo_ai_integration.artifact_registry import (
    ArtifactRegistry,
    ArtifactRegistryError,
)


def _fake_gguf(path: Path, payload: bytes = b"GGUFfake") -> str:
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


@pytest.fixture()
def serving_dir(tmp_path: Path) -> Path:
    d = tmp_path / "serving"
    (d / "models").mkdir(parents=True)
    (d / "adapters").mkdir()
    return d


def _write_manifest(serving_dir: Path, document: dict) -> Path:
    manifest = serving_dir / "model-artifacts.json"
    manifest.write_text(json.dumps(document), encoding="utf-8")
    return manifest


def _valid_document(serving_dir: Path) -> dict:
    return {
        "version": 1,
        "llama_cpp_image": "ghcr.io/ggml-org/llama.cpp:server@sha256:" + "a" * 64,
        "model": {
            "id": "test-base",
            "source": "hf:test/base",
            "path": "models/base.gguf",
            "sha256": _fake_gguf(serving_dir / "models" / "base.gguf"),
        },
        "adapters": {
            task: {
                "source": "workflo-train:test",
                "path": f"adapters/{task}.gguf",
                "sha256": _fake_gguf(serving_dir / "adapters" / f"{task}.gguf"),
            }
            for task in ("test-gen", "reasoning", "reporting")
        },
    }


def test_valid_manifest_loads_and_verifies(serving_dir: Path):
    manifest = _write_manifest(serving_dir, _valid_document(serving_dir))
    registry = ArtifactRegistry(manifest_path=manifest)
    snap = registry.snapshot
    assert snap.model_id == "test-base"
    assert set(snap.adapters) == {"test-gen", "reasoning", "reporting"}
    telemetry = registry.telemetry()
    assert telemetry["model"]["sha256"] == snap.model_sha256
    assert telemetry["adapters"]["test-gen"]["path"] == "adapters/test-gen.gguf"


def test_missing_manifest_fails_closed(tmp_path: Path):
    with pytest.raises(ArtifactRegistryError, match="not found"):
        ArtifactRegistry(manifest_path=tmp_path / "absent.json")


def test_missing_artifact_file_fails_closed(serving_dir: Path):
    doc = _valid_document(serving_dir)
    (serving_dir / "adapters" / "reasoning.gguf").unlink()
    manifest = _write_manifest(serving_dir, doc)
    with pytest.raises(ArtifactRegistryError, match="missing"):
        ArtifactRegistry(manifest_path=manifest)


def test_tampered_artifact_fails_closed(serving_dir: Path):
    doc = _valid_document(serving_dir)
    (serving_dir / "adapters" / "test-gen.gguf").write_bytes(b"tampered-bytes")
    manifest = _write_manifest(serving_dir, doc)
    with pytest.raises(ArtifactRegistryError, match="digest mismatch"):
        ArtifactRegistry(manifest_path=manifest)


def test_reverify_detects_post_construction_swap(serving_dir: Path):
    manifest = _write_manifest(serving_dir, _valid_document(serving_dir))
    registry = ArtifactRegistry(manifest_path=manifest)
    # Swap bytes after startup; identity metadata stays readable, but
    # reverify must fail closed.
    (serving_dir / "models" / "base.gguf").write_bytes(b"swapped")
    with pytest.raises(ArtifactRegistryError, match="digest mismatch"):
        registry.reverify()
    assert registry.snapshot.model_id == "test-base"


@pytest.mark.parametrize(
    "mutate, match",
    [
        (lambda d: d.update(version=2), "version"),
        (
            lambda d: d.update(
                llama_cpp_image="docker.io/library/llama.cpp:latest"
            ),
            "ghcr.io",
        ),
        (
            lambda d: d.update(
                llama_cpp_image="ghcr.io/ggml-org/llama.cpp:server"
            ),
            "sha256",
        ),
        (lambda d: d.pop("adapters"), "adapters"),
        (lambda d: d["adapters"].pop("reporting"), "exactly"),
        (
            lambda d: d["adapters"].update(
                {"rogue": {"source": "x", "path": "adapters/rogue.gguf", "sha256": "0" * 64}}
            ),
            "exactly",
        ),
        (lambda d: d.pop("model"), "model"),
        (
            lambda d: d["model"].update(sha256="ZZ" * 32),
            "hex digest",
        ),
        (
            lambda d: d["model"].update(path="models/base.bin"),
            ".gguf",
        ),
        (
            lambda d: d["model"].update(path="../outside/base.gguf"),
            "escapes",
        ),
    ],
)
def test_malformed_manifests_fail_closed(serving_dir: Path, mutate, match):
    doc = _valid_document(serving_dir)
    mutate(doc)
    manifest = _write_manifest(serving_dir, doc)
    with pytest.raises(ArtifactRegistryError, match=match):
        ArtifactRegistry(manifest_path=manifest, verify_files=False)


def test_snapshot_to_dict_is_json_serializable_and_identity_only(serving_dir: Path):
    manifest = _write_manifest(serving_dir, _valid_document(serving_dir))
    snap = ArtifactRegistry(manifest_path=manifest).snapshot.to_dict()
    encoded = json.dumps(snap)  # must not raise
    assert "test-base" in encoded
    # identity metadata only: no file contents, no sources leaked into payload
    flat = json.dumps(snap)
    assert "hf:test/base" not in flat  # source strings stay out of telemetry
