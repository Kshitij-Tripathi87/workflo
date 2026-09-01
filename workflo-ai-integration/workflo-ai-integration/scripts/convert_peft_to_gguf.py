#!/usr/bin/env python3
"""PEFT/Unsloth adapter → GGUF for llama-server (stub).

Run once per adapter after QLoRA training, before mounting under
serving/adapters/. llama-server cannot load raw PEFT directories; vLLM can.

Status: STUB. Prints the conversion plan. Does not invent a .gguf.

  python scripts/convert_peft_to_gguf.py --dry-run \\
      --peft-dir ./train/out/test-gen \\
      --base-gguf ./models/qwen2.5-coder-7b-instruct-q4_K_M.gguf \\
      --out ./serving/adapters/test-gen.gguf
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--peft-dir", required=True, type=Path)
    p.add_argument("--base-gguf", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--i-know-this-is-a-stub",
        action="store_true",
        help="Acknowledge stub mode (still refuses to fake a GGUF).",
    )
    args = p.parse_args()

    plan = f"""# PEFT -> GGUF conversion plan
peft_dir={args.peft_dir}
base_gguf={args.base_gguf}
out={args.out}

# Step 1 - sanity
#   require: {{peft_dir}}/adapter_config.json
#   require: {{base_gguf}} exists

# Step 2 - convert (PIN a llama.cpp commit before un-stubbing)
#   python /path/to/llama.cpp/convert_lora_to_gguf.py \\
#       --base-model-path {{base_gguf}} \\
#       --outfile {{out}} \\
#       {{peft_dir}}

# Step 3 - smoke
#   llama-server -m {{base_gguf}} --lora {{out}} --lora-init-without-apply --port 18080
#   curl -sf http://127.0.0.1:18080/lora-adapters
"""
    print(plan.format(peft_dir=args.peft_dir, base_gguf=args.base_gguf, out=args.out))

    if args.dry_run:
        print("[stub] dry-run only — no conversion executed")
        return 0

    if not args.i_know_this_is_a_stub:
        print(
            "[stub] conversion not implemented yet.\n"
            "Re-run with --dry-run to print the plan, or --i-know-this-is-a-stub to acknowledge.",
            file=sys.stderr,
        )
        return 2

    print(
        "[stub] acknowledged — refusing to fake a .gguf. Wire convert_lora_to_gguf.py first.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
