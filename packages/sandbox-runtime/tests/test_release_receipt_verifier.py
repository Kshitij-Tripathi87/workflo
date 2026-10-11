from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import sandbox_isolation.verify_receipts as verifier

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "release" / "verify_receipt_bundle.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("verify_receipt_bundle", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _arguments(tmp_path: Path) -> tuple[list[str], Path]:
    receipt = tmp_path / "receipt.json"
    public_key = tmp_path / "receipt-key.pub.pem"
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    receipt.write_text("{}")
    public_key.write_text("public")
    (evidence / "manifest.json").write_text("{}")
    (evidence / "events.jsonl").write_text("{}\n")
    report = tmp_path / "verification.json"
    return [
        str(SCRIPT), "--receipt", str(receipt), "--pubkey", str(public_key),
        "--evidence", str(evidence), "--report", str(report),
    ], report


def test_release_verifier_retains_valid_metadata_only_outcome(monkeypatch, tmp_path):
    module = _load_module()
    args, report = _arguments(tmp_path)
    result = SimpleNamespace(
        status=SimpleNamespace(value="VALID"),
        checks_passed=["one", "two"],
        checks_failed=[],
    )
    monkeypatch.setattr(verifier, "verify_receipt", lambda *args, **kwargs: result)
    monkeypatch.setattr(sys, "argv", args)

    assert module.main() == 0
    evidence = json.loads(report.read_text())
    assert evidence["passed"] is True
    assert evidence["status"] == "VALID"
    assert evidence["staging_secrets_present"] is False
    assert evidence["checks_passed_count"] == 2
    assert len(evidence["receipt_sha256"]) == 64


def test_release_verifier_checks_acceptance_identities_and_tamper_matrix(
    monkeypatch, tmp_path
):
    module = _load_module()
    args, report = _arguments(tmp_path)
    commit = "1" * 40
    base_image = "registry.example/server@sha256:" + "2" * 64
    deep_image = "registry.example/deep@sha256:" + "3" * 64
    adapter_hashes = {
        "test-gen": "4" * 64,
        "reasoning": "5" * 64,
        "reporting": "6" * 64,
    }
    manifest = {
        "llama_cpp_image": base_image,
        "model": {"id": "frozen-model", "sha256": "7" * 64},
        "adapters": {
            name: {"sha256": digest} for name, digest in adapter_hashes.items()
        },
    }
    (tmp_path / "model-artifacts.json").write_text(json.dumps(manifest))
    (tmp_path / "deep-image-digest.txt").write_text(deep_image + "\n")
    (tmp_path / "deep-image-binding.json").write_text(json.dumps({
        "passed": True,
        "deep_image": deep_image,
        "release_commit": commit,
        "base_image": base_image,
        "model_id": "frozen-model",
        "binary_sha256": "8" * 64,
        "artifact_sha256": {"base": "7" * 64, **adapter_hashes},
    }))
    local_provenance = {
        "model": "frozen-model",
        "source_code_included": True,
        "server_image": base_image,
        "base_model_sha256": "7" * 64,
        "adapter_sha256": adapter_hashes,
        "endpoint_scope": "loopback",
        "error": None,
    }
    (tmp_path / "llamacpp-worker-smoke.json").write_text(json.dumps({
        "passed": True,
        "provenance": local_provenance,
    }))
    (tmp_path / "reporting-smoke.json").write_text(json.dumps({
        "passed": True,
        "endpoint_scope": "loopback",
        "source_code_included": False,
        "identity": {
            "model": "frozen-model",
            "server_image": base_image,
            "base_model_sha256": "7" * 64,
            "adapter_sha256": adapter_hashes,
        },
    }))
    (tmp_path / "gateway-smoke.json").write_text(json.dumps({
        "passed": True,
        "valid_request": {"model": "frozen-model"},
    }))
    receipt_document = {
        "teardown_proof": {
            "processes_terminated": True,
            "cgroup_removed": True,
            "network_namespace_removed": True,
            "workspace_removed": True,
        },
        "agent_activity": {"inference_provenance": {
            "model": "frozen-model",
            "mode": "gateway",
            "source_code_included": False,
            "error": None,
            "requests": 1,
        }},
    }
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps(receipt_document))
    bundle = tmp_path / "sandbox-receipt"
    bundle.mkdir()
    (bundle / "receipt.json").write_text(json.dumps(receipt_document))
    (bundle / "receipt-key.pub.pem").write_text("public")
    (bundle / "evidence").mkdir()
    (bundle / "evidence/manifest.json").write_text("{}")
    (bundle / "evidence/events.jsonl").write_text("{}\n")
    for name in ("run-identity.json", "teardown-check.json", "redaction-check.json", "rollback.json"):
        (tmp_path / name).write_text("{}")
    indexed_names = (
        "run-identity.json", "model-artifacts.json", "deep-image-binding.json", "deep-image-digest.txt",
        "llamacpp-worker-smoke.json", "reporting-smoke.json", "gateway-smoke.json",
        "sandbox-receipt/receipt.json", "sandbox-receipt/evidence/manifest.json",
        "sandbox-receipt/evidence/events.jsonl", "teardown-check.json",
        "redaction-check.json", "rollback.json",
    )
    indexed = {
        name: {"sha256": hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()}
        for name in indexed_names
    }
    (tmp_path / "producer-evidence-index.json").write_text(json.dumps({
        "passed": True,
        "release_commit": commit,
        "files_count": len(indexed),
        "files": indexed,
    }))
    valid = SimpleNamespace(
        status=SimpleNamespace(value="VALID"), checks_passed=["valid"], checks_failed=[]
    )
    invalid = SimpleNamespace(
        status=SimpleNamespace(value="INVALID"), checks_passed=[], checks_failed=["tampered"]
    )
    outcomes = iter((valid, invalid))
    monkeypatch.setattr(verifier, "verify_receipt", lambda *args, **kwargs: next(outcomes))
    monkeypatch.setattr(sys, "argv", args + [
        "--acceptance-root", str(tmp_path), "--commit", commit, "--tamper-checks",
    ])

    assert module.main() == 0
    evidence = json.loads(report.read_text())
    assert evidence["acceptance_semantics_verified"] is True
    assert evidence["tamper_checks_passed_count"] == 4
    assert set(evidence["tamper_checks"]) == {
        "model_image_identity", "base_model_sha256", "adapter_sha256", "teardown_status",
    }

    (tmp_path / "gateway-smoke.json").write_text('{"tampered":true}')
    with pytest.raises(module.AcceptanceVerificationError):
        module._verify_producer_index(tmp_path, commit)


def test_release_verifier_rejects_inherited_staging_secret(monkeypatch, tmp_path):
    module = _load_module()
    args, report = _arguments(tmp_path)
    monkeypatch.setenv("WORKFLO_GATEWAY_API_KEY", "must-not-be-inherited")
    monkeypatch.setattr(sys, "argv", args)

    assert module.main() == 1
    evidence = json.loads(report.read_text())
    assert evidence["passed"] is False
    assert evidence["staging_secrets_present"] is True
    assert "must-not-be-inherited" not in report.read_text()
