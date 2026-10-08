#!/usr/bin/env bash
set -euo pipefail

mkdir -p var/transparency secrets
pnpm install
echo "Workflo bootstrap complete."
