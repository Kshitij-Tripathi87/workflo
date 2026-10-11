from __future__ import annotations

import hashlib
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
    candidate_image = "registry.example/deep@sha256:" + "a" * 64
    _gate4_bundle(tmp_path, commit)
    manifest = {
        "llama_cpp_image": "registry.example/server@sha256:" + "d" * 64,
        "model": {"id": model, "sha256": "e" * 64},
        "adapters": {
            name: {"sha256": digest * 64}
            for name, digest in (("test-gen", "f"), ("reasoning", "a"), ("reporting", "b"))
        },
    }
    manifest_text = json.dumps(manifest)
    (tmp_path / "model-artifacts.json").write_text(manifest_text)
    (tmp_path / "previous-model-artifacts.json").write_text(manifest_text)
    _write(tmp_path, "run-identity.json", {
        "passed": True,
        "release_commit": commit,
        "github_sha": commit,
        "github_run_id": "12345",
        "github_ref_name": "arena/bd73d1dd-workflo",
    })
    (tmp_path / "commit.txt").write_text(commit + "\n")
    (tmp_path / "python-version.txt").write_text("Python 3.11\n")
    (tmp_path / "manifest.sha256").write_text(
        hashlib.sha256(manifest_text.encode()).hexdigest() + "\n"
    )
    (tmp_path / "deep-image-digest.txt").write_text(candidate_image + "\n")
    _write(tmp_path, "environment-setup.json", {
        "passed": True,
        "release_commit": commit,
        "deep_image": candidate_image,
        "binary_sha256": "9" * 64,
    })
    _write(tmp_path, "cost-report.json", {
        "passed": True,
        "assumption_instance_hourly_usd": 1.0,
        "estimated_cost_per_request_usd": 0.01,
        "estimated_cost_per_representative_run_usd": 0.03,
        "benchmark_repeats": 3,
        "requests_completed": 12,
        "requests_requested": 12,
        "representative_run_requests": 3,
    })
    _write(tmp_path, "failure-evidence.json", {
        "passed": True,
        "inference_succeeded": False,
        "command_exit_nonzero": True,
        "source_code_included": False,
        "prompt_recorded": False,
        "generated_code_recorded": False,
        "narrative_recorded": False,
        "credentials_recorded": False,
        "error_classes": ["transport_URLError"],
    })
    _write(tmp_path, "redaction-check.json", {
        "passed": True,
        "staging_secrets_present": False,
        "rejected_files": [],
        "missing_files": [],
        "files_scanned_count": 30,
    })
    _write(tmp_path, "teardown-check.json", {
        "passed": True,
        "candidate_container_absent": True,
        "rollback_container_absent": True,
        "llama_server_processes_absent": True,
        "worker_children_absent": True,
        "ollama_absent": True,
        "listener_inspection_succeeded": True,
        "container_inspection_succeeded": True,
        "model_listeners_absent": True,
        "prompt_slot_cache_absent": True,
        "known_sandbox_workspace_absent": True,
    })
    _write(tmp_path, "gateway-smoke.json", {
        "passed": True,
        "authorization_rejection": {"passed": True},
        "wrong_key_rejection": {"passed": True},
        "valid_request": {"passed": True, "model": model, "source_code_included": False},
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
    _write(tmp_path, "independent-redaction-check.json", {
        "passed": True,
        "staging_secrets_present": False,
        "missing_files": [],
        "rejected_files": [],
    })
    _write(tmp_path, "independent-verification.json", {
        "passed": True,
        "status": "VALID",
        "staging_secrets_present": False,
        "producer_index_verified": True,
        "acceptance_semantics_verified": True,
        "tamper_checks_passed_count": 4,
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
    output = tmp_path / "evidence-index.json"
    monkeypatch.setattr(sys, "argv", [
        str(SCRIPT), "--gate", "gate5", "--root", str(tmp_path),
        "--commit", commit, "--model", model, "--out", str(output),
    ])

    assert module.main() == 0
    index = json.loads(output.read_text())
    assert index["passed"] is True
    assert index["files_count"] >= 35
    assert "independent-verification.json" in index["files"]
    assert "independent-redaction-check.json" in index["files"]
    assert "redaction-check.json" in index["files"]

    (tmp_path / "independent-verification.json").unlink()
    (tmp_path / "independent-redaction-check.json").unlink()
    producer_output = tmp_path / "producer-evidence-index.json"
    monkeypatch.setattr(sys, "argv", [
        str(SCRIPT), "--gate", "gate5", "--phase", "producer",
        "--root", str(tmp_path), "--commit", commit, "--model", model,
        "--out", str(producer_output),
    ])
    assert module.main() == 0
    assert json.loads(producer_output.read_text())["passed"] is True
