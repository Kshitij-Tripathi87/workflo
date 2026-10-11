#!/usr/bin/env python3
"""Fail closed unless a Gate 4 or Gate 5 evidence directory is complete."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path

HEX64 = re.compile(r"^[0-9a-f]{64}$")
PINNED = re.compile(r"^.+@sha256:[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")


class EvidenceError(ValueError):
    pass


def _load(root: Path, relative: str) -> dict:
    path = root / relative
    if not path.is_file() or not path.stat().st_size:
        raise EvidenceError(f"required evidence is missing: {relative}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EvidenceError(f"required evidence is invalid JSON: {relative}") from exc
    if not isinstance(value, dict):
        raise EvidenceError(f"required evidence is not an object: {relative}")
    return value


def _passed(document: dict, name: str) -> None:
    if document.get("passed") is not True:
        raise EvidenceError(f"required evidence did not pass: {name}")


def _sha(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _common(root: Path, commit: str) -> list[str]:
    configuration = _load(root, "configuration-validation.json")
    manifest = _load(root, "manifest-verification.json")
    binding = _load(root, "deep-image-binding.json")
    worker = _load(root, "llamacpp-worker-smoke.json")
    reporting = _load(root, "reporting-smoke.json")
    isolation = _load(root, "container-isolation.json")
    for name, document in (
        ("configuration", configuration),
        ("manifest", manifest),
        ("deep image binding", binding),
        ("worker smoke", worker),
        ("reporting smoke", reporting),
        ("container isolation", isolation),
    ):
        _passed(document, name)
    if manifest.get("artifact_count") != 4:
        raise EvidenceError("manifest evidence must contain four artifacts")
    if binding.get("release_commit") != commit:
        raise EvidenceError("deep image is not bound to the release commit")
    if not PINNED.fullmatch(str(binding.get("deep_image", ""))):
        raise EvidenceError("deep image evidence is not digest-pinned")
    if worker.get("reporting_passed") is not True:
        raise EvidenceError("worker evidence does not include reporting success")
    if worker.get("teardown_verified") is not True:
        raise EvidenceError("worker model teardown is not verified")
    if reporting.get("teardown_verified") is not True:
        raise EvidenceError("reporting model teardown is not verified")
    required_isolation = (
        "no_published_ports", "network_none", "container_removed", "no_ollama"
    )
    if any(isolation.get(field) is not True for field in required_isolation):
        raise EvidenceError("container isolation or teardown evidence is incomplete")
    return [
        "configuration-validation.json",
        "manifest-verification.json",
        "deep-image-binding.json",
        "llamacpp-worker-smoke.json",
        "reporting-smoke.json",
        "container-isolation.json",
    ]


def _gate4(root: Path, commit: str) -> list[str]:
    files = _common(root, commit)
    negative = _load(root, "negative-builds.json")
    identity = _load(root, "release-identity.json")
    _passed(negative, "negative builds")
    _passed(identity, "release identity")
    cases = negative.get("cases")
    if not isinstance(cases, list) or len(cases) != 6:
        raise EvidenceError("exactly six negative builds are required")
    if any(not isinstance(case, dict) or case.get("rejected") is not True for case in cases):
        raise EvidenceError("every negative image build must fail closed")
    if identity.get("release_commit") != commit:
        raise EvidenceError("release identity commit mismatch")
    if not PINNED.fullmatch(str(identity.get("deep_image", ""))):
        raise EvidenceError("release identity deep image is not immutable")
    return files + ["negative-builds.json", "release-identity.json"]


def _gate5(
    root: Path,
    commit: str,
    expected_model: str,
    *,
    require_independent: bool,
) -> list[str]:
    files = _common(root, commit)
    candidate_binding = _load(root, "deep-image-binding.json")
    run_identity = _load(root, "run-identity.json")
    environment = _load(root, "environment-setup.json")
    cost = _load(root, "cost-report.json")
    failure = _load(root, "failure-evidence.json")
    redaction = _load(root, "redaction-check.json")
    teardown_check = _load(root, "teardown-check.json")
    for name, document in (
        ("run identity", run_identity),
        ("release environment", environment),
        ("cost report", cost),
        ("safe failure", failure),
        ("redaction scan", redaction),
        ("teardown check", teardown_check),
    ):
        _passed(document, name)
    for relative in (
        "run-identity.json",
        "commit.txt",
        "python-version.txt",
        "manifest.sha256",
        "model-artifacts.json",
        "deep-image-digest.txt",
        "previous-model-artifacts.json",
    ):
        path = root / relative
        if not path.is_file() or not path.stat().st_size:
            raise EvidenceError(f"release metadata is missing: {relative}")
        files.append(relative)
    if run_identity.get("release_commit") != commit or run_identity.get("github_sha") != commit:
        raise EvidenceError("run identity does not match the release commit")
    if not str(run_identity.get("github_run_id", "")).isdigit():
        raise EvidenceError("run identity does not contain a GitHub run ID")
    if (root / "commit.txt").read_text(encoding="utf-8").strip() != commit:
        raise EvidenceError("commit metadata does not match the release commit")
    if (root / "deep-image-digest.txt").read_text(encoding="utf-8").strip() != candidate_binding.get("deep_image"):
        raise EvidenceError("deep-image metadata does not match the candidate binding")
    manifest_digest = (root / "manifest.sha256").read_text(encoding="utf-8").strip()
    if not HEX64.fullmatch(manifest_digest) or manifest_digest != _sha(root / "model-artifacts.json"):
        raise EvidenceError("manifest digest metadata is invalid")
    if environment.get("release_commit") != commit:
        raise EvidenceError("release environment commit mismatch")
    if environment.get("deep_image") != candidate_binding.get("deep_image"):
        raise EvidenceError("release environment deep-image mismatch")
    if not HEX64.fullmatch(str(environment.get("binary_sha256", ""))):
        raise EvidenceError("release environment binary identity is invalid")
    try:
        hourly = float(cost["assumption_instance_hourly_usd"])
        cost_per_request = float(cost["estimated_cost_per_request_usd"])
        cost_per_run = float(cost["estimated_cost_per_representative_run_usd"])
    except (KeyError, TypeError, ValueError) as exc:
        raise EvidenceError("cost report is incomplete") from exc
    if (
        not all(math.isfinite(value) and value >= 0 for value in (hourly, cost_per_request, cost_per_run))
        or cost.get("benchmark_repeats") != 3
        or cost.get("requests_completed", 0) < 1
        or cost.get("requests_completed") != cost.get("requests_requested")
        or cost.get("representative_run_requests", 0) < 1
    ):
        raise EvidenceError("cost report values are invalid")
    if failure.get("inference_succeeded") is not False or failure.get("command_exit_nonzero") is not True:
        raise EvidenceError("intentional inference failure did not fail closed")
    failure_privacy_fields = (
        "source_code_included", "prompt_recorded", "generated_code_recorded",
        "narrative_recorded", "credentials_recorded",
    )
    if any(failure.get(field) is not False for field in failure_privacy_fields):
        raise EvidenceError("safe-failure evidence is not source-free")
    if not failure.get("error_classes"):
        raise EvidenceError("safe-failure evidence contains no error identity")
    if (
        redaction.get("staging_secrets_present") is not False
        or redaction.get("rejected_files")
        or redaction.get("missing_files")
        or redaction.get("files_scanned_count", 0) < 1
    ):
        raise EvidenceError("evidence redaction scan is incomplete")
    teardown_fields = (
        "candidate_container_absent", "rollback_container_absent",
        "llama_server_processes_absent", "worker_children_absent", "ollama_absent",
        "listener_inspection_succeeded", "container_inspection_succeeded",
        "model_listeners_absent", "prompt_slot_cache_absent", "known_sandbox_workspace_absent",
    )
    if any(teardown_check.get(field) is not True for field in teardown_fields):
        raise EvidenceError("explicit teardown evidence is incomplete")
    files += [
        "environment-setup.json", "cost-report.json", "failure-evidence.json",
        "redaction-check.json", "teardown-check.json",
    ]

    gateway = _load(root, "gateway-smoke.json")
    _passed(gateway, "gateway smoke")
    for field in (
        "authorization_rejection", "wrong_key_rejection", "valid_request",
        "redaction", "source_rejection",
    ):
        if not isinstance(gateway.get(field), dict) or gateway[field].get("passed") is not True:
            raise EvidenceError(f"gateway evidence is incomplete: {field}")
    if gateway["source_rejection"].get("cases", 0) < 4:
        raise EvidenceError("gateway source rejection did not cover four cases")
    if gateway["redaction"].get("redactions_applied", 0) < 1:
        raise EvidenceError("gateway redaction was not observed")
    if expected_model and gateway["valid_request"].get("model") != expected_model:
        raise EvidenceError("gateway valid-request model identity mismatch")
    if gateway["valid_request"].get("source_code_included") is not False:
        raise EvidenceError("gateway valid request included source code")
    files.append("gateway-smoke.json")

    for repeat in (1, 2, 3):
        name = f"model-benchmark-{repeat}.json"
        benchmark = _load(root, name)
        levels = benchmark.get("levels")
        if not isinstance(levels, list) or [item.get("concurrency") for item in levels] != [1, 2, 4]:
            raise EvidenceError(f"benchmark levels are incomplete: {name}")
        for level in levels:
            if level.get("failed") != 0 or level.get("succeeded") != level.get("requests"):
                raise EvidenceError(f"benchmark requests failed: {name}")
            if level.get("canaries_verified") != level.get("requests"):
                raise EvidenceError(f"benchmark canary coverage is incomplete: {name}")
            if level.get("leakage_failures") != 0:
                raise EvidenceError(f"benchmark leakage detected: {name}")
        if not HEX64.fullmatch(str(benchmark.get("endpoint_sha256", ""))):
            raise EvidenceError(f"benchmark endpoint identity is invalid: {name}")
        markdown_name = f"model-benchmark-{repeat}.md"
        markdown = root / markdown_name
        if not markdown.is_file() or not markdown.stat().st_size:
            raise EvidenceError(f"benchmark Markdown evidence is missing: {markdown_name}")
        files.extend((name, markdown_name))

    receipt_name = "sandbox-receipt/receipt.json"
    receipt = _load(root, receipt_name)
    signed = receipt.get("receipt", receipt)
    if signed.get("receipt_version") != 4 or not signed.get("signature"):
        raise EvidenceError("full signed v4 receipt is missing")
    teardown = signed.get("teardown_proof") or {}
    for field in (
        "processes_terminated", "cgroup_removed", "network_namespace_removed", "workspace_removed"
    ):
        if teardown.get(field) is not True:
            raise EvidenceError(f"sandbox teardown claim is not verified: {field}")
    if (signed.get("canary_check") or {}).get("request_succeeded") is not False:
        raise EvidenceError("sandbox egress canary did not fail")
    provenance = ((signed.get("agent_activity") or {}).get("inference_provenance") or {})
    if provenance.get("mode") != "gateway" or provenance.get("source_code_included") is not False:
        raise EvidenceError("receipt gateway privacy provenance is missing")
    if expected_model and provenance.get("model") != expected_model:
        raise EvidenceError("receipt model identity mismatch")
    if provenance.get("error"):
        raise EvidenceError("receipt contains an inference error")
    if provenance.get("requests", 0) < 1 or not provenance.get("request_ids"):
        raise EvidenceError("receipt contains no real inference request")
    files.append(receipt_name)
    for relative in (
        "sandbox-receipt/receipt-key.pub.pem",
        "sandbox-receipt/evidence/manifest.json",
        "sandbox-receipt/evidence/events.jsonl",
    ):
        path = root / relative
        if not path.is_file() or not path.stat().st_size:
            raise EvidenceError(f"full receipt bundle is incomplete: {relative}")
        files.append(relative)
    evidence_root = root / "sandbox-receipt/evidence"
    for path in sorted(evidence_root.rglob("*")):
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            if relative not in files:
                files.append(relative)

    verification = (
        _load(root, "independent-verification.json") if require_independent else None
    )
    independent_redaction = (
        _load(root, "independent-redaction-check.json") if require_independent else None
    )
    previous_manifest = _load(root, "previous-manifest-verification.json")
    rollback_binding = _load(root, "rollback-image-binding.json")
    rollback_worker = _load(root, "rollback-smoke/llamacpp-worker-smoke.json")
    rollback_reporting = _load(root, "rollback-smoke/reporting-smoke.json")
    rollback_isolation = _load(root, "rollback-smoke/container-isolation.json")
    rollback = _load(root, "rollback.json")
    passing_documents = [
        ("previous manifest verification", previous_manifest),
        ("rollback image binding", rollback_binding),
        ("rollback worker smoke", rollback_worker),
        ("rollback reporting smoke", rollback_reporting),
        ("rollback container isolation", rollback_isolation),
        ("rollback", rollback),
    ]
    if verification is not None and independent_redaction is not None:
        passing_documents.extend((
            ("independent receipt verification", verification),
            ("independent redaction scan", independent_redaction),
        ))
    for name, document in passing_documents:
        _passed(document, name)
    if verification is not None:
        if verification.get("status") != "VALID":
            raise EvidenceError("independent verifier did not return VALID")
        if verification.get("staging_secrets_present") is not False:
            raise EvidenceError("independent verifier inherited staging credentials")
        if verification.get("producer_index_verified") is not True:
            raise EvidenceError("downloaded producer evidence index was not verified")
        if verification.get("acceptance_semantics_verified") is not True:
            raise EvidenceError("independent acceptance semantics were not verified")
        if verification.get("tamper_checks_passed_count") != 4:
            raise EvidenceError("independent tamper matrix is incomplete")
        if (
            independent_redaction.get("staging_secrets_present") is not False
            or independent_redaction.get("missing_files")
            or independent_redaction.get("rejected_files")
        ):
            raise EvidenceError("independent redaction scan is incomplete")
    restored_image = str(rollback.get("restored_image", ""))
    if not PINNED.fullmatch(restored_image):
        raise EvidenceError("rollback image is not immutable")
    if restored_image == candidate_binding.get("deep_image"):
        raise EvidenceError("rollback image must differ from the candidate image")
    restored_commit = rollback.get("restored_commit")
    if not COMMIT.fullmatch(str(restored_commit or "")) or restored_commit == commit:
        raise EvidenceError("rollback commit must be an earlier exact commit")
    if rollback_binding.get("deep_image") != restored_image:
        raise EvidenceError("rollback binding image does not match restored image")
    if rollback_binding.get("release_commit") != restored_commit:
        raise EvidenceError("rollback binding commit does not match restored commit")
    if rollback.get("manifest_verified") is not True or rollback.get("smoke_passed") is not True:
        raise EvidenceError("previous image/manifest pair was not restored and verified")
    files += [
        "previous-manifest-verification.json",
        "rollback-image-binding.json",
        "rollback-smoke/llamacpp-worker-smoke.json",
        "rollback-smoke/reporting-smoke.json",
        "rollback-smoke/container-isolation.json",
        "rollback.json",
    ]
    if verification is not None:
        files.extend(("independent-verification.json", "independent-redaction-check.json"))
    return files


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate", required=True, choices=("gate4", "gate5"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--model", default="")
    parser.add_argument("--phase", choices=("producer", "final"), default="final")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    try:
        if not COMMIT.fullmatch(args.commit):
            raise EvidenceError("release commit is invalid")
        if args.gate == "gate4" and args.phase != "final":
            raise EvidenceError("Gate 4 does not support phased evidence")
        files = (
            _gate4(args.root, args.commit)
            if args.gate == "gate4"
            else _gate5(
                args.root,
                args.commit,
                args.model,
                require_independent=args.phase == "final",
            )
        )
        output = args.out.resolve()
        files = sorted(set(files) | {
            path.relative_to(args.root).as_posix()
            for path in args.root.rglob("*")
            if path.is_file() and path.resolve() != output
        })
        index = {
            "passed": True,
            "gate": args.gate,
            "release_commit": args.commit,
            "files_count": len(files),
            "files": {
                name: {"sha256": _sha(args.root / name)} for name in sorted(files)
            },
        }
    except (EvidenceError, OSError, UnicodeError, KeyError, TypeError) as exc:
        index = {
            "passed": False,
            "gate": args.gate,
            "release_commit": args.commit,
            "failure_class": type(exc).__name__,
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n")
        print(f"P4 evidence assertion failed: {exc}", file=sys.stderr)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n")
    print(f"{args.gate} evidence is complete for {args.commit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
