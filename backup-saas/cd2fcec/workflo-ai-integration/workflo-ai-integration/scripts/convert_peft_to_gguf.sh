#!/usr/bin/env bash
# convert_peft_to_gguf.sh — PEFT/Unsloth adapter → GGUF for llama-server
#
# Run once per adapter after QLoRA training, before mounting under
# serving/adapters/. llama-server cannot load raw PEFT directories; vLLM can.
#
# Status: STUB. The conversion commands below are the intended pipeline;
# they are not executed until convert-lora-to-gguf.py (or equivalent) is
# pinned to a llama.cpp release and a real PEFT checkpoint exists.
#
# Usage (when un-stubbed):
#   ./scripts/convert_peft_to_gguf.sh \
#       --peft-dir ./train/out/test-gen \
#       --base-gguf ./models/qwen2.5-coder-7b-instruct-q4_K_M.gguf \
#       --out ./serving/adapters/test-gen.gguf
#
# Exit codes:
#   0  conversion succeeded (or --dry-run printed the plan)
#   2  missing args / stub mode without --dry-run acknowledging stub
#   3  conversion tool failed

set -euo pipefail

PEFT_DIR=""
BASE_GGUF=""
OUT=""
DRY_RUN=0
FORCE_STUB_ACK=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --peft-dir) PEFT_DIR="$2"; shift 2 ;;
    --base-gguf) BASE_GGUF="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --i-know-this-is-a-stub) FORCE_STUB_ACK=1; shift ;;
    -h|--help)
      sed -n '2,25p' "$0"
      exit 0
      ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$PEFT_DIR" || -z "$BASE_GGUF" || -z "$OUT" ]]; then
  echo "required: --peft-dir --base-gguf --out" >&2
  exit 2
fi

# Intended pipeline (llama.cpp convert-lora-to-gguf.py or equivalent):
#   1. Ensure PEFT dir contains adapter_config.json + adapter_model.safetensors
#   2. python convert-lora-to-gguf.py --base "$BASE_GGUF" --outfile "$OUT" "$PEFT_DIR"
#   3. Verify: llama-server -m "$BASE_GGUF" --lora "$OUT" --lora-init-without-apply -ngl 0 --port 0
PLAN=$(cat <<EOF
# PEFT → GGUF conversion plan
peft_dir=$PEFT_DIR
base_gguf=$BASE_GGUF
out=$OUT

# Step 1 — sanity
test -f "$PEFT_DIR/adapter_config.json"
test -f "$BASE_GGUF"

# Step 2 — convert (PIN a llama.cpp commit before un-stubbing)
# python /path/to/llama.cpp/convert_lora_to_gguf.py \\
#     --base-model-path "$BASE_GGUF" \\
#     --outfile "$OUT" \\
#     "$PEFT_DIR"

# Step 3 — smoke: list adapters after load
# llama-server -m "$BASE_GGUF" --lora "$OUT" --lora-init-without-apply --port 18080 &
# curl -sf http://127.0.0.1:18080/lora-adapters | grep -q "$(basename "$OUT" .gguf || true)"
EOF
)

echo "$PLAN"

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "[stub] dry-run only — no conversion executed"
  exit 0
fi

if [[ "$FORCE_STUB_ACK" -ne 1 ]]; then
  echo "[stub] conversion not implemented yet." >&2
  echo "Re-run with --dry-run to print the plan, or --i-know-this-is-a-stub to acknowledge." >&2
  exit 2
fi

echo "[stub] acknowledged — refusing to fake a .gguf. Wire convert_lora_to_gguf.py first." >&2
exit 2
