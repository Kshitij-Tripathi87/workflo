#!/usr/bin/env python3
"""Verify a frozen llama.cpp artifact manifest and its local GGUF files."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

HEX64 = re.compile(r"^[0-9a-f]{64}$")
PINNED_IMAGE = re.compile(r"^.+@sha256:[0-9a-f]{64}$")
ADAPTERS = {"test-gen", "reasoning", "reporting"}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def verify_entry(label: str, entry: dict, root: Path) -> Path:
    if not isinstance(entry, dict):
        raise ValueError(f"{label} must be an object")
    source = entry.get("source")
    if not isinstance(source, str) or not source or "REPLACE_" in source:
        raise ValueError(f"{label}.source is not frozen")
    expected = entry.get("sha256")
    if not isinstance(expected, str) or not HEX64.fullmatch(expected):
        raise ValueError(f"{label}.sha256 must be 64 lowercase hex characters")
    relative = Path(str(entry.get("path", "")))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"{label}.path must remain under the serving directory")
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f"{label} artifact is missing: {path}")
    actual = digest(path)
    if actual != expected:
        raise ValueError(f"{label} SHA-256 mismatch: expected {expected}, got {actual}")
    return path


def verify_runtime_env(document: dict, root: Path) -> None:
    """Bind protected-runner configuration to the verified manifest."""

    expected = {
        "WORKFLO_LLAMACPP_IMAGE": document["llama_cpp_image"],
        "WORKFLO_LLAMACPP_MODEL_ID": document["model"]["id"],
        "WORKFLO_LLAMACPP_BASE_GGUF": str((root / document["model"]["path"]).resolve()),
        "WORKFLO_LLAMACPP_BASE_SHA256": document["model"]["sha256"],
    }
    for name, entry in document["adapters"].items():
        prefix = name.upper().replace("-", "_")
        expected[f"WORKFLO_LLAMACPP_{prefix}_GGUF"] = str(
            (root / entry["path"]).resolve()
        )
        expected[f"WORKFLO_LLAMACPP_{prefix}_SHA256"] = entry["sha256"]
    for variable, value in expected.items():
        configured = os.environ.get(variable, "")
        if variable.endswith("_GGUF") and configured:
            configured = str(Path(configured).resolve())
        if configured != value:
            raise ValueError(f"{variable} does not match the frozen manifest")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--check-env",
        action="store_true",
        help="require WORKFLO_LLAMACPP_* runtime values to exactly match the manifest",
    )
    args = parser.parse_args()
    try:
        document = json.loads(args.manifest.read_text(encoding="utf-8"))
        if document.get("version") != 1:
            raise ValueError("manifest version must be 1")
        image = document.get("llama_cpp_image")
        if not isinstance(image, str) or not PINNED_IMAGE.fullmatch(image):
            raise ValueError("llama_cpp_image must be pinned by SHA-256 digest")
        model = document.get("model")
        if not isinstance(model, dict) or not model.get("id") or "REPLACE_" in model["id"]:
            raise ValueError("model.id is not frozen")
        root = args.manifest.resolve().parent
        paths = {verify_entry("model", model, root)}
        adapters = document.get("adapters")
        if not isinstance(adapters, dict) or set(adapters) != ADAPTERS:
            raise ValueError(f"adapters must contain exactly {sorted(ADAPTERS)}")
        for name in sorted(ADAPTERS):
            paths.add(verify_entry(f"adapters.{name}", adapters[name], root))
        if len(paths) != 1 + len(ADAPTERS):
            raise ValueError("model and adapters must reference four distinct files")
        if args.check_env:
            verify_runtime_env(document, root)
    except (KeyError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"artifact manifest verification failed: {exc}", file=sys.stderr)
        return 1
    print("artifact manifest verified: image + base GGUF + three adapters")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
