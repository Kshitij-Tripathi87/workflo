#!/usr/bin/env python3
"""Bind a registry-pinned deep worker image to a frozen artifact manifest.

The verifier inspects immutable image labels and independently hashes the
embedded llama-server executable and all four GGUF files in a networkless,
read-only container. Its report contains identities, hashes, and outcomes only.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

PINNED_IMAGE = re.compile(r"^.+@sha256:[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")


def _run(command: list[str], *, capture: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def _write(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _expected_labels(manifest: dict, commit: str) -> dict[str, str]:
    return {
        "org.opencontainers.image.base.name": manifest["llama_cpp_image"],
        "org.opencontainers.image.revision": commit,
        "dev.workflo.model.id": manifest["model"]["id"],
        "dev.workflo.model.base.sha256": manifest["model"]["sha256"],
        "dev.workflo.adapter.test-gen.sha256": manifest["adapters"]["test-gen"]["sha256"],
        "dev.workflo.adapter.reasoning.sha256": manifest["adapters"]["reasoning"]["sha256"],
        "dev.workflo.adapter.reporting.sha256": manifest["adapters"]["reporting"]["sha256"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    report: dict = {"passed": False, "failure_class": None}
    try:
        if not PINNED_IMAGE.fullmatch(args.image):
            raise ValueError("deep image must be registry-pinned by SHA-256 digest")
        if not COMMIT.fullmatch(args.commit):
            raise ValueError("release commit must be 40 lowercase hex characters")
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        expected = _expected_labels(manifest, args.commit)

        _run(["docker", "pull", args.image], capture=False)
        inspection = json.loads(_run(["docker", "image", "inspect", args.image]).stdout)[0]
        labels = inspection.get("Config", {}).get("Labels") or {}
        for name, value in expected.items():
            if labels.get(name) != value:
                raise ValueError(f"deep image label mismatch: {name}")

        embedded_script = r'''
import hashlib, json, os, pathlib, subprocess
items = {
    "base": ("/models/base.gguf", "WORKFLO_LLAMACPP_BASE_SHA256"),
    "test-gen": ("/adapters/test-gen.gguf", "WORKFLO_LLAMACPP_TEST_GEN_SHA256"),
    "reasoning": ("/adapters/reasoning.gguf", "WORKFLO_LLAMACPP_REASONING_SHA256"),
    "reporting": ("/adapters/reporting.gguf", "WORKFLO_LLAMACPP_REPORTING_SHA256"),
}
def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()
actual = {}
for name, (path, variable) in items.items():
    value = digest(path)
    if value != os.environ.get(variable):
        raise SystemExit(f"embedded artifact mismatch: {name}")
    actual[name] = value
binary = pathlib.Path("/opt/llamacpp/llama-server")
if not binary.is_file() or not os.access(binary, os.X_OK):
    raise SystemExit("embedded llama-server is not executable")
subprocess.run([str(binary), "--version"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print(json.dumps({
    "binary_sha256": digest(binary),
    "artifact_sha256": actual,
    "base_image": os.environ["WORKFLO_LLAMACPP_IMAGE"],
    "model_id": os.environ["WORKFLO_LLAMACPP_MODEL_ID"],
}, sort_keys=True))
'''
        container = _run(
            [
                "docker", "run", "--rm", "--network", "none", "--read-only",
                "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=64m",
                "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
                "--entrypoint", "python", args.image, "-c", embedded_script,
            ]
        )
        embedded = json.loads(container.stdout)
        if embedded["base_image"] != manifest["llama_cpp_image"]:
            raise ValueError("embedded base-image identity does not match manifest")
        if embedded["model_id"] != manifest["model"]["id"]:
            raise ValueError("embedded model identity does not match manifest")

        digest = args.image.rsplit("@sha256:", 1)[1]
        repo_digests = inspection.get("RepoDigests") or []
        if not any(item.endswith(f"@sha256:{digest}") for item in repo_digests):
            raise ValueError("pulled image repository digest does not match requested digest")

        report = {
            "passed": True,
            "deep_image": args.image,
            "deep_image_id": inspection["Id"],
            "release_commit": args.commit,
            "base_image": manifest["llama_cpp_image"],
            "model_id": manifest["model"]["id"],
            "binary_sha256": embedded["binary_sha256"],
            "artifact_sha256": embedded["artifact_sha256"],
            "label_binding_verified": True,
            "embedded_hashes_verified": True,
            "network_mode": "none",
            "read_only": True,
            "capabilities_dropped": True,
        }
    except (KeyError, OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        report["failure_class"] = type(exc).__name__
        _write(args.report, report)
        print(f"deep image verification failed: {exc}", file=sys.stderr)
        return 1

    _write(args.report, report)
    print("deep image verified against manifest and exact release commit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
