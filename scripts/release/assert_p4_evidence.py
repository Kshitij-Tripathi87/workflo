#!/usr/bin/env python3
"""Fail closed unless a Gate 4 or Gate 5 evidence directory is complete."""
from __future__ import annotations

import argparse
import hashlib
import json
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


def _gate5(root: Path, commit: str, expected_model: str) -> list[str]:
    files = _common(root, commit)
    candidate_binding = _load(root, "deep-image-binding.json")
    gateway = _load(root, "gateway-smoke.json")
    _passed(gateway, "gateway smoke")
    for field in (
        "authorization_rejection", "wrong_key_rejection", "redaction", "source_rejection"
    ):
        if not isinstance(gateway.get(field), dict) or gateway[field].get("passed") is not True:
            raise EvidenceError(f"gateway evidence is incomplete: {field}")
    if gateway["source_rejection"].get("cases", 0) < 4:
        raise EvidenceError("gateway source rejection did not cover four cases")
    if gateway["redaction"].get("redactions_applied", 0) < 1:
        raise EvidenceError("gateway redaction was not observed")
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

    verification = _load(root, "independent-verification.json")
    previous_manifest = _load(root, "previous-manifest-verification.json")
    rollback_binding = _load(root, "rollback-image-binding.json")
    rollback_worker = _load(root, "rollback-smoke/llamacpp-worker-smoke.json")
    rollback_reporting = _load(root, "rollback-smoke/reporting-smoke.json")
    rollback_isolation = _load(root, "rollback-smoke/container-isolation.json")
    rollback = _load(root, "rollback.json")
    final_teardown = _load(root, "final-teardown.json")
    for name, document in (
        ("independent receipt verification", verification),
        ("previous manifest verification", previous_manifest),
        ("rollback image binding", rollback_binding),
        ("rollback worker smoke", rollback_worker),
        ("rollback reporting smoke", rollback_reporting),
        ("rollback container isolation", rollback_isolation),
        ("rollback", rollback),
        ("final teardown", final_teardown),
    ):
        _passed(document, name)
    if verification.get("status") != "VALID":
        raise EvidenceError("independent verifier did not return VALID")
    if verification.get("staging_secrets_present") is not False:
        raise EvidenceError("independent verifier inherited staging credentials")
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
    if final_teardown.get("candidate_container_absent") is not True:
        raise EvidenceError("candidate container remains after acceptance")
    if final_teardown.get("rollback_container_absent") is not True:
        raise EvidenceError("rollback container remains after acceptance")
    files += [
        "independent-verification.json",
        "previous-manifest-verification.json",
        "rollback-image-binding.json",
        "rollback-smoke/llamacpp-worker-smoke.json",
        "rollback-smoke/reporting-smoke.json",
        "rollback-smoke/container-isolation.json",
        "rollback.json",
        "final-teardown.json",
    ]
    return files


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate", required=True, choices=("gate4", "gate5"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--model", default="")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    try:
        if not COMMIT.fullmatch(args.commit):
            raise EvidenceError("release commit is invalid")
        files = (
            _gate4(args.root, args.commit)
            if args.gate == "gate4"
            else _gate5(args.root, args.commit, args.model)
        )
        index = {
            "passed": True,
            "gate": args.gate,
            "release_commit": args.commit,
            "files_count": len(files),
            "files": {
                name: {"sha256": _sha(args.root / name)} for name in sorted(files)
            },
        }
    except (EvidenceError, OSError, KeyError, TypeError) as exc:
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
