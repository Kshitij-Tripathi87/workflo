#!/usr/bin/env python3
"""PEFT/Unsloth adapter â†’ GGUF for llama-server (real wrapper).

Run once per adapter after QLoRA training, before mounting under
serving/adapters/. llama-server cannot load raw PEFT directories; vLLM can.

This script is a thin, honest wrapper around llama.cpp's
``convert_lora_to_gguf.py``. It performs NO serialization itself: if the
llama.cpp checkout or its converter is missing, it fails closed. It never
writes a .gguf by any other means.

Prerequisites:
  - A llama.cpp checkout at --llamacpp-dir containing convert_lora_to_gguf.py
    (PIN the commit used for a release; record it in the release evidence).
  - --peft-dir produced by train/train_qlora.py containing
    adapter_config.json and adapter_model.safetensors.
  - The FROZEN serving base GGUF (the same file recorded in the manifest).

Usage:
    python scripts/convert_peft_to_gguf.py \
        --peft-dir train/out/test_gen/final \
        --base-gguf serving/models/base.gguf \
        --llamacpp-dir /path/to/llama.cpp \
        --out serving/adapters/test-gen.gguf

    # plan only:
    python scripts/convert_peft_to_gguf.py ... --dry-run
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

CONVERTER_NAME = "convert_lora_to_gguf.py"
REQUIRED_PEFT_FILES = ("adapter_config.json",)


def find_converter(llamacpp_dir: Path) -> Path:
    direct = llamacpp_dir / CONVERTER_NAME
    if direct.is_file():
        return direct
    for candidate in sorted(llamacpp_dir.rglob(CONVERTER_NAME)):
        return candidate
    raise FileNotFoundError(
        f"{CONVERTER_NAME} not found under {llamacpp_dir}. "
        "Clone llama.cpp (pin the commit) and pass --llamacpp-dir."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--peft-dir", required=True, type=Path)
    parser.add_argument(
        "--hf-config-dir",
        required=True,
        type=Path,
        help="directory with the base model's ORIGINAL HF config/tokenizer "
        "(config.json, tokenizer.json); the converter reads tensor names and "
        "shapes from here",
    )
    parser.add_argument(
        "--base-gguf",
        type=Path,
        default=None,
        help="frozen serving GGUF; checked for existence only (conversion "
        "itself reads the HF config), but proves the release artifact is "
        "present before converting",
    )
    parser.add_argument("--llamacpp-dir", required=True, type=Path)
    parser.add_argument("--out", "--outfile", dest="outfile", required=True, type=Path)
    parser.add_argument(
        "--outtype",
        default="f16",
        choices=["f32", "f16", "bf16", "q8_0", "auto"],
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the exact command that would run, then exit",
    )
    parser.add_argument(
        "--converter-arg",
        action="append",
        default=[],
        help="extra argument forwarded verbatim to the converter (repeatable)",
    )
    args = parser.parse_args()

    if not args.peft_dir.is_dir():
        print(f"refusing: PEFT directory missing: {args.peft_dir}", file=sys.stderr)
        return 2
    for required in REQUIRED_PEFT_FILES:
        if not (args.peft_dir / required).is_file():
            print(
                f"refusing: {required} missing in {args.peft_dir} â€” "
                "is this a trained adapter directory?",
                file=sys.stderr,
            )
            return 2
    weights = args.peft_dir / "adapter_model.safetensors"
    if not weights.is_file():
        alt = args.peft_dir / "adapter_model.bin"
        if not alt.is_file():
            print(
                "refusing: no adapter_model.safetensors (or .bin) in "
                f"{args.peft_dir}",
                file=sys.stderr,
            )
            return 2
    if args.base_gguf is not None and not args.base_gguf.is_file():
        print(f"refusing: base GGUF missing: {args.base_gguf}", file=sys.stderr)
        return 2
    if not args.hf_config_dir.is_dir():
        print(f"refusing: HF config directory missing: {args.hf_config_dir}", file=sys.stderr)
        return 2
    if not (args.hf_config_dir / "config.json").is_file():
        print(
            f"refusing: config.json missing in {args.hf_config_dir} â€” "
            "pass the ORIGINAL HF weights directory",
            file=sys.stderr,
        )
        return 2
    if not args.llamacpp_dir.is_dir():
        print(f"refusing: llama.cpp directory missing: {args.llamacpp_dir}", file=sys.stderr)
        return 2

    try:
        converter = find_converter(args.llamacpp_dir)
    except FileNotFoundError as exc:
        print(f"refusing: {exc}", file=sys.stderr)
        return 2

    command = [
        sys.executable,
        str(converter),
        "--outfile",
        str(args.outfile.resolve()),
        "--outtype",
        args.outtype,
        "--base",
        str(args.hf_config_dir.resolve()),
        *args.converter_arg,
        str(args.peft_dir.resolve()),
    ]

    if args.dry_run:
        print("conversion plan (dry-run):")
        print("  " + " ".join(command))
        print(
            "post-conversion smoke (run before trusting the adapter): "
            "llama-server -m <base> --lora <out> --lora-init-without-apply "
            "--port 18080, then GET /lora-adapters"
        )
        return 0

    args.outfile.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(command)
    if completed.returncode != 0:
        print(
            f"converter exited with {completed.returncode}; no adapter GGUF "
            "was produced by this script",
            file=sys.stderr,
        )
        return completed.returncode
    if not args.outfile.is_file():
        print(
            f"converter succeeded but output missing: {args.outfile}",
            file=sys.stderr,
        )
        return 2
    print(f"adapter written -> {args.outfile}")
    print(
        "record its sha256 into the release manifest via "
        "train/make_manifest.py; never hand-edit hashes."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

