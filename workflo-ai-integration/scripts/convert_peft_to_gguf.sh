#!/usr/bin/env bash
# convert_peft_to_gguf.sh — thin POSIX wrapper around the real Python wrapper.
#
# The Python script owns all validation and fail-closed behavior. This file
# exists only for callers that prefer a shell entry point.
#
#   ./scripts/convert_peft_to_gguf.sh \
#       --peft-dir ./train/out/test_gen/final \
#       --base-gguf ./serving/models/base.gguf \
#       --llamacpp-dir /path/to/llama.cpp \
#       --out ./serving/adapters/test-gen.gguf
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/convert_peft_to_gguf.py" "$@"
