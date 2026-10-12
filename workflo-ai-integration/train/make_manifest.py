#!/usr/bin/env python3
"""Generate the frozen artifact manifest from real files on disk.

This script NEVER invents hashes: every sha256 is computed from the actual
bytes of the artifact in the serving directory. It refuses to write a
manifest unless all four artifacts (base + three adapters) exist and all
identity inputs (image digest, model id, canonical sources) are supplied.

Usage:
    python train/make_manifest.py \
        --image "ghcr.io/example/llama.cpp:server@sha256:<64hex>" \
        --model-id "qwen3.8-4b-sft-fable5-glint-q4_k_s" \
        --base-source "release-owner-supply/qwen3_4b_local_final/Qwen3.8-4B-SFT-Fable5-Glint.Q4_K_S.gguf" \
        --adapter-source "workflo-train:<dataset-hash>+<run-id>" \
        --serving-dir ../serving

After writing, it re-verifies with scripts/verify_artifact_manifest.py so a
bad manifest can never be silently produced.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

HEX64 = re.compile(r"^[0-9a-f]{64}$")
PINNED_IMAGE = re.compile(r"^.+@sha256:[0-9a-f]{64}$")
ADAPTERS = ("test-gen", "reasoning", "reporting")


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, help="digest-pinned llama.cpp server image")
    parser.add_argument("--model-id", required=True, help="frozen model identity string")
    parser.add_argument("--base-source", required=True, help="canonical source of the base GGUF")
    parser.add_argument("--adapter-source", required=True, help="canonical source applied to all three adapters")
    parser.add_argument(
        "--serving-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "serving",
    )
    parser.add_argument("--out", type=Path, default=None, help="manifest path (default <serving-dir>/model-artifacts.json)")
    args = parser.parse_args()

    if not PINNED_IMAGE.fullmatch(args.image):
        print("refusing: --image must be pinned as <ref>@sha256:<64 lowercase hex>", file=sys.stderr)
        return 2
    if not args.model_id.strip() or "REPLACE_" in args.model_id:
        print("refusing: --model-id must be a frozen identity string", file=sys.stderr)
        return 2
    for label, source in (("base", args.base_source), ("adapter", args.adapter_source)):
        if not source.strip() or "REPLACE_" in source:
            print(f"refusing: --{label}-source must be a canonical source", file=sys.stderr)
            return 2

    serving = args.serving_dir.resolve()
    base_path = serving / "models" / "base.gguf"
    if not base_path.is_file():
        print(f"refusing: base artifact missing: {base_path}", file=sys.stderr)
        return 2

    adapters = {}
    for name in ADAPTERS:
        adapter_path = serving / "adapters" / f"{name}.gguf"
        if not adapter_path.is_file():
            print(f"refusing: adapter artifact missing: {adapter_path}", file=sys.stderr)
            return 2
        adapters[name] = {
            "source": args.adapter_source,
            "path": f"adapters/{name}.gguf",
            "sha256": digest(adapter_path),
        }

    manifest = {
        "version": 1,
        "llama_cpp_image": args.image,
        "model": {
            "id": args.model_id,
            "source": args.base_source,
            "path": "models/base.gguf",
            "sha256": digest(base_path),
        },
        "adapters": adapters,
    }

    out_path = args.out or (serving / "model-artifacts.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"manifest written -> {out_path}")

    verifier = Path(__file__).resolve().parent.parent / "scripts" / "verify_artifact_manifest.py"
    result = subprocess.run(
        [sys.executable, str(verifier), str(out_path)],
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
