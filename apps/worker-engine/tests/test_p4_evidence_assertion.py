from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "release" / "assert_p4_evidence.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("assert_p4_evidence", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(root: Path, name: str, value: dict) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def _gate4_bundle(root: Path, commit: str) -> None:
    image = "registry.example/deep@sha256:" + "a" * 64
    _write(root, "configuration-validation.json", {"passed": True})
    _write(root, "manifest-verification.json", {"passed": True, "artifact_count": 4})
    _write(root, "deep-image-binding.json", {
        "passed": True, "release_commit": commit, "deep_image": image,
    })
    _write(root, "llamacpp-worker-smoke.json", {
        "passed": True, "reporting_passed": True, "teardown_verified": True,
    })
    _write(root, "reporting-smoke.json", {"passed": True, "teardown_verified": True})
    _write(root, "container-isolation.json", {
        "passed": True,
        "no_published_ports": True,
        "network_none": True,
        "container_removed": True,
        "no_ollama": True,
    })
    _write(root, "negative-builds.json", {
        "passed": True,
        "cases": [{"name": f"case-{i}", "rejected": True} for i in range(6)],
    })
    _write(root, "release-identity.json", {
        "passed": True, "release_commit": commit, "deep_image": image,
    })


def test_gate4_evidence_assertion_indexes_complete_bundle(monkeypatch, tmp_path):
    module = _load_module()
    commit = "1" * 40
    _gate4_bundle(tmp_path, commit)
    output = tmp_path / "evidence-index.json"
    monkeypatch.setattr(sys, "argv", [
        str(SCRIPT), "--gate", "gate4", "--root", str(tmp_path),
        "--commit", commit, "--out", str(output),
    ])

    assert module.main() == 0
    index = json.loads(output.read_text())
    assert index["passed"] is True
    assert index["files_count"] == 8
    assert all(len(item["sha256"]) == 64 for item in index["files"].values())


def test_gate4_evidence_assertion_rejects_missing_negative_build(monkeypatch, tmp_path):
    module = _load_module()
    commit = "1" * 40
    _gate4_bundle(tmp_path, commit)
    document = json.loads((tmp_path / "negative-builds.json").read_text())
    document["cases"].pop()
    _write(tmp_path, "negative-builds.json", document)
    output = tmp_path / "evidence-index.json"
    monkeypatch.setattr(sys, "argv", [
        str(SCRIPT), "--gate", "gate4", "--root", str(tmp_path),
        "--commit", commit, "--out", str(output),
    ])

    assert module.main() == 1
    assert json.loads(output.read_text())["passed"] is False


def test_gate5_evidence_assertion_requires_full_receipt_benchmarks_and_rollback(
    monkeypatch, tmp_path
):
    module = _load_module()
    commit = "1" * 40
    model = "frozen-model"
    image = "registry.example/deep@sha256:" + "c" * 64
    _gate4_bundle(tmp_path, commit)
    _write(tmp_path, "gateway-smoke.json", {
        "passed": True,
        "authorization_rejection": {"passed": True},
        "wrong_key_rejection": {"passed": True},
        "redaction": {"passed": True, "redactions_applied": 1},
        "source_rejection": {"passed": True, "cases": 4},
    })
    for repeat in (1, 2, 3):
        _write(tmp_path, f"model-benchmark-{repeat}.json", {
            "endpoint_sha256": "b" * 64,
            "levels": [
                {
                    "concurrency": concurrency,
                    "requests": 4,
                    "succeeded": 4,
                    "failed": 0,
                    "canaries_verified": 4,
                    "leakage_failures": 0,
                }
                for concurrency in (1, 2, 4)
            ],
        })
        (tmp_path / f"model-benchmark-{repeat}.md").write_text("metadata report\n")
    _write(tmp_path, "sandbox-receipt/receipt.json", {
        "receipt_version": 4,
        "signature": "signed",
        "teardown_proof": {
            "processes_terminated": True,
            "cgroup_removed": True,
            "network_namespace_removed": True,
            "workspace_removed": True,
        },
        "canary_check": {"request_succeeded": False},
        "agent_activity": {"inference_provenance": {
            "mode": "gateway",
            "source_code_included": False,
            "model": model,
            "error": None,
            "requests": 1,
            "request_ids": ["request-id"],
        }},
    })
    for relative, content in (
        ("sandbox-receipt/receipt-key.pub.pem", "public-key"),
        ("sandbox-receipt/evidence/manifest.json", "{}"),
        ("sandbox-receipt/evidence/events.jsonl", "{}\n"),
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    _write(tmp_path, "independent-verification.json", {
        "passed": True, "status": "VALID", "staging_secrets_present": False,
    })
    _write(tmp_path, "previous-manifest-verification.json", {"passed": True})
    _write(tmp_path, "rollback-image-binding.json", {
        "passed": True,
        "deep_image": image,
        "release_commit": "2" * 40,
    })
    for relative in (
        "rollback-smoke/llamacpp-worker-smoke.json",
        "rollback-smoke/reporting-smoke.json",
        "rollback-smoke/container-isolation.json",
    ):
        _write(tmp_path, relative, {"passed": True})
    _write(tmp_path, "rollback.json", {
        "passed": True,
        "restored_image": image,
        "restored_commit": "2" * 40,
        "manifest_verified": True,
        "smoke_passed": True,
    })
    _write(tmp_path, "final-teardown.json", {
        "passed": True,
        "candidate_container_absent": True,
        "rollback_container_absent": True,
    })
    output = tmp_path / "evidence-index.json"
    monkeypatch.setattr(sys, "argv", [
        str(SCRIPT), "--gate", "gate5", "--root", str(tmp_path),
        "--commit", commit, "--model", model, "--out", str(output),
    ])

    assert module.main() == 0
    index = json.loads(output.read_text())
    assert index["passed"] is True
    assert index["files_count"] == 25
