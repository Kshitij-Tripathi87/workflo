#!/usr/bin/env python3
"""Independently verify a receipt and the Gate 5 acceptance identity bundle."""
from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import io
import json
import os
import re
import sys
import tempfile
from pathlib import Path

HEX64 = re.compile(r"^[0-9a-f]{64}$")
PINNED = re.compile(r"^.+@sha256:[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
ADAPTERS = {"test-gen", "reasoning", "reporting"}


class AcceptanceVerificationError(ValueError):
    """An independently checked release identity or semantic claim failed."""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AcceptanceVerificationError("acceptance document is not an object")
    return value


def _signed(receipt_document: dict) -> dict:
    value = receipt_document.get("receipt", receipt_document)
    if not isinstance(value, dict):
        raise AcceptanceVerificationError("signed receipt payload is not an object")
    return value


def _validate_acceptance(
    root: Path,
    commit: str,
    *,
    receipt_document: dict | None = None,
    binding_document: dict | None = None,
) -> None:
    if not COMMIT.fullmatch(commit):
        raise AcceptanceVerificationError("release commit is invalid")
    manifest = _json(root / "model-artifacts.json")
    binding = binding_document or _json(root / "deep-image-binding.json")
    worker = _json(root / "llamacpp-worker-smoke.json")
    reporting = _json(root / "reporting-smoke.json")
    gateway = _json(root / "gateway-smoke.json")
    receipt_doc = receipt_document or _json(root / "sandbox-receipt/receipt.json")
    receipt = _signed(receipt_doc)
    if any(
        document.get("passed") is not True
        for document in (binding, worker, reporting, gateway)
    ):
        raise AcceptanceVerificationError("candidate acceptance document did not pass")

    expected_deep = (root / "deep-image-digest.txt").read_text(encoding="utf-8").strip()
    if not PINNED.fullmatch(expected_deep) or binding.get("deep_image") != expected_deep:
        raise AcceptanceVerificationError("candidate deep-image identity mismatch")
    if binding.get("release_commit") != commit:
        raise AcceptanceVerificationError("candidate release commit mismatch")
    if binding.get("base_image") != manifest.get("llama_cpp_image"):
        raise AcceptanceVerificationError("candidate base-image identity mismatch")
    if binding.get("model_id") != (manifest.get("model") or {}).get("id"):
        raise AcceptanceVerificationError("candidate model identity mismatch")

    expected_artifacts = {"base": (manifest.get("model") or {}).get("sha256")}
    adapters = manifest.get("adapters") or {}
    if set(adapters) != ADAPTERS:
        raise AcceptanceVerificationError("manifest adapter set mismatch")
    expected_artifacts.update({name: adapters[name].get("sha256") for name in ADAPTERS})
    if any(not isinstance(value, str) or not HEX64.fullmatch(value) for value in expected_artifacts.values()):
        raise AcceptanceVerificationError("manifest artifact identity is invalid")
    if binding.get("artifact_sha256") != expected_artifacts:
        raise AcceptanceVerificationError("embedded artifact identity mismatch")
    if not HEX64.fullmatch(str(binding.get("binary_sha256", ""))):
        raise AcceptanceVerificationError("embedded binary identity is invalid")

    local = worker.get("provenance") or {}
    report_identity = reporting.get("identity") or {}
    expected_adapter_hashes = {name: expected_artifacts[name] for name in ADAPTERS}
    if local.get("model") != (manifest.get("model") or {}).get("id"):
        raise AcceptanceVerificationError("worker model identity mismatch")
    if local.get("source_code_included") is not True:
        raise AcceptanceVerificationError("worker source scope is invalid")
    if local.get("server_image") != manifest.get("llama_cpp_image"):
        raise AcceptanceVerificationError("worker serving-image identity mismatch")
    if local.get("base_model_sha256") != expected_artifacts["base"]:
        raise AcceptanceVerificationError("worker base-model identity mismatch")
    if local.get("adapter_sha256") != expected_adapter_hashes:
        raise AcceptanceVerificationError("worker adapter identity mismatch")
    if local.get("endpoint_scope") != "loopback" or local.get("error"):
        raise AcceptanceVerificationError("worker provenance is not a passing loopback run")
    if reporting.get("endpoint_scope") != "loopback":
        raise AcceptanceVerificationError("reporting endpoint scope is invalid")
    if reporting.get("source_code_included") is not False:
        raise AcceptanceVerificationError("reporting source scope is invalid")
    if report_identity.get("model") != (manifest.get("model") or {}).get("id"):
        raise AcceptanceVerificationError("reporting model identity mismatch")
    if report_identity.get("server_image") != manifest.get("llama_cpp_image"):
        raise AcceptanceVerificationError("reporting serving-image identity mismatch")
    if report_identity.get("base_model_sha256") != expected_artifacts["base"]:
        raise AcceptanceVerificationError("reporting base-model identity mismatch")
    if report_identity.get("adapter_sha256") != expected_adapter_hashes:
        raise AcceptanceVerificationError("reporting adapter identity mismatch")

    model_id = (manifest.get("model") or {}).get("id")
    valid_gateway = gateway.get("valid_request") or {}
    provenance = ((receipt.get("agent_activity") or {}).get("inference_provenance") or {})
    if valid_gateway.get("model") != model_id or provenance.get("model") != model_id:
        raise AcceptanceVerificationError("gateway or receipt model identity mismatch")
    if provenance.get("mode") != "gateway" or provenance.get("source_code_included") is not False:
        raise AcceptanceVerificationError("receipt gateway privacy provenance is invalid")
    if provenance.get("error") or provenance.get("requests", 0) < 1:
        raise AcceptanceVerificationError("receipt inference provenance is not successful")

    teardown = receipt.get("teardown_proof") or {}
    for name in (
        "processes_terminated", "cgroup_removed", "network_namespace_removed", "workspace_removed"
    ):
        if teardown.get(name) is not True:
            raise AcceptanceVerificationError("receipt teardown claim is false")


def _verify_producer_index(root: Path, commit: str) -> None:
    index = _json(root / "producer-evidence-index.json")
    if index.get("passed") is not True or index.get("release_commit") != commit:
        raise AcceptanceVerificationError("producer evidence index is not valid")
    indexed = index.get("files")
    if not isinstance(indexed, dict) or index.get("files_count") != len(indexed):
        raise AcceptanceVerificationError("producer evidence index is incomplete")
    required = {
        "run-identity.json", "model-artifacts.json", "deep-image-binding.json",
        "deep-image-digest.txt",
        "llamacpp-worker-smoke.json", "reporting-smoke.json", "gateway-smoke.json",
        "sandbox-receipt/receipt.json", "sandbox-receipt/evidence/manifest.json",
        "sandbox-receipt/evidence/events.jsonl", "teardown-check.json",
        "redaction-check.json", "rollback.json",
    }
    if not required.issubset(indexed):
        raise AcceptanceVerificationError("producer evidence identities are not fully indexed")
    root_resolved = root.resolve()
    for relative, identity in indexed.items():
        if not isinstance(relative, str) or not isinstance(identity, dict):
            raise AcceptanceVerificationError("producer evidence identity is malformed")
        candidate = root / relative
        path = candidate.resolve()
        if candidate.is_symlink() or not path.is_relative_to(root_resolved) or not path.is_file():
            raise AcceptanceVerificationError("producer evidence path is unsafe")
        if identity.get("sha256") != _sha(path):
            raise AcceptanceVerificationError("producer evidence digest mismatch")


def _expect_semantic_rejection(root: Path, commit: str, **overrides: dict) -> bool:
    try:
        _validate_acceptance(root, commit, **overrides)
    except (AcceptanceVerificationError, KeyError, TypeError, OSError, json.JSONDecodeError):
        return True
    return False


def _tamper_checks(root: Path, commit: str, verify_receipt) -> dict[str, dict[str, object]]:
    binding = _json(root / "deep-image-binding.json")
    receipt_document = _json(root / "sandbox-receipt/receipt.json")
    checks: dict[str, dict[str, object]] = {}

    image_tamper = copy.deepcopy(binding)
    image_tamper["deep_image"] = "registry.invalid/deep@sha256:" + "0" * 64
    checks["model_image_identity"] = {
        "passed": _expect_semantic_rejection(
            root, commit, binding_document=image_tamper
        ),
        "outcome": "rejected",
    }

    base_tamper = copy.deepcopy(binding)
    base_tamper.setdefault("artifact_sha256", {})["base"] = "0" * 64
    checks["base_model_sha256"] = {
        "passed": _expect_semantic_rejection(
            root, commit, binding_document=base_tamper
        ),
        "outcome": "rejected",
    }

    adapter_tamper = copy.deepcopy(binding)
    adapter_tamper.setdefault("artifact_sha256", {})["test-gen"] = "0" * 64
    checks["adapter_sha256"] = {
        "passed": _expect_semantic_rejection(
            root, commit, binding_document=adapter_tamper
        ),
        "outcome": "rejected",
    }

    teardown_tamper = copy.deepcopy(receipt_document)
    _signed(teardown_tamper).setdefault("teardown_proof", {})["processes_terminated"] = False
    semantic_rejected = _expect_semantic_rejection(
        root, commit, receipt_document=teardown_tamper
    )
    with tempfile.TemporaryDirectory(prefix="workflo-receipt-tamper-") as temporary:
        path = Path(temporary) / "receipt.json"
        path.write_text(json.dumps(teardown_tamper), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = verify_receipt(
                str(path),
                pubkey_path=str(root / "sandbox-receipt/receipt-key.pub.pem"),
                evidence_dir=str(root / "sandbox-receipt/evidence"),
            )
    checks["teardown_status"] = {
        "passed": semantic_rejected and result.status.value != "VALID",
        "outcome": "rejected",
    }
    return checks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--pubkey", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--acceptance-root", type=Path)
    parser.add_argument("--commit")
    parser.add_argument("--tamper-checks", action="store_true")
    args = parser.parse_args()

    sensitive_names = (
        "WORKFLO_MODEL_API_KEY",
        "WORKFLO_GATEWAY_API_KEY",
        "WORKFLO_LLM_API_KEY",
    )
    inherited_secrets = [name for name in sensitive_names if os.environ.get(name)]

    try:
        if inherited_secrets:
            raise RuntimeError("independent verifier inherited staging credentials")
        from sandbox_isolation.verify_receipts import verify_receipt

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = verify_receipt(
                str(args.receipt),
                pubkey_path=str(args.pubkey),
                evidence_dir=str(args.evidence),
            )
        if result.status.value != "VALID":
            raise AcceptanceVerificationError("receipt verification was not valid")

        semantic_verified = False
        tamper: dict[str, dict[str, object]] = {}
        if args.acceptance_root is not None:
            if not args.commit:
                raise AcceptanceVerificationError("acceptance commit is required")
            _verify_producer_index(args.acceptance_root, args.commit)
            _validate_acceptance(args.acceptance_root, args.commit)
            semantic_verified = True
            if args.tamper_checks:
                tamper = _tamper_checks(args.acceptance_root, args.commit, verify_receipt)
                if len(tamper) != 4 or any(item.get("passed") is not True for item in tamper.values()):
                    raise AcceptanceVerificationError("acceptance tamper matrix was not rejected")

        report = {
            "passed": True,
            "status": "VALID",
            "checks_passed_count": len(result.checks_passed),
            "checks_failed_count": len(result.checks_failed),
            "staging_secrets_present": False,
            "receipt_sha256": _sha(args.receipt),
            "public_key_sha256": _sha(args.pubkey),
            "evidence_manifest_sha256": _sha(args.evidence / "manifest.json"),
            "evidence_events_sha256": _sha(args.evidence / "events.jsonl"),
            "producer_index_verified": semantic_verified,
            "acceptance_semantics_verified": semantic_verified,
            "tamper_checks_passed_count": sum(
                item.get("passed") is True for item in tamper.values()
            ),
            "tamper_checks": tamper,
        }
    except Exception as exc:  # noqa: BLE001 - classify verifier failure
        report = {
            "passed": False,
            "status": "VERIFICATION_FAILED",
            "checks_passed_count": 0,
            "checks_failed_count": 1,
            "staging_secrets_present": bool(inherited_secrets),
            "failure_class": type(exc).__name__,
        }

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if not report["passed"]:
        print(f"independent receipt verification failed: {report['status']}", file=sys.stderr)
        return 1
    print("independent receipt and acceptance verification returned VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
