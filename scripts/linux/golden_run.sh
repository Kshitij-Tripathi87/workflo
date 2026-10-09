#!/bin/bash
# The Workflo golden run: the complete product loop on REAL Linux
# namespaces — no mocks, no Docker:
#
#   workflo run --path <fixture> --test
#     -> snapshot -> bwrap sandbox -> in-sandbox probes (fail-closed)
#     -> pytest inside the sandbox -> teardown + verification
#     -> evidence binding -> CLI-side Ed25519 signing -> receipt.json
#   workflo verify <receipt>
#     -> signature + teardown claims + canary + evidence binding
#
# Exits 0 only if EVERY step verifies. Run as root on Linux (WSL2 or CI).
set -euo pipefail

REPO_ROOT="${WORKFLO_REPO_ROOT:-$(cd "$(dirname "${0}")/../.." && pwd)}"
FIXTURE="${WORKFLO_FIXTURE:-/root/wf-fixture}"
WORKDIR="${WORKFLO_GOLDEN_DIR:-/root/wf-golden}"

if [ "$(id -u)" -ne 0 ]; then
  echo "ERROR: golden run must execute as root (namespace + cgroup setup)" >&2
  exit 1
fi

# The setup venv carries the workflo CLI
export PATH="/opt/workflo/venv/bin:$PATH"

command -v workflo >/dev/null || {
  echo "ERROR: workflo CLI not installed - run scripts/linux/setup_env.sh" >&2
  exit 1
}
[ -d /opt/workflo/workflo-worker ] || {
  echo "ERROR: runtime image missing - run scripts/linux/setup_env.sh" >&2
  exit 1
}

rm -rf "$WORKDIR"
mkdir -p "$WORKDIR"
cd "$WORKDIR"

echo "==> workflo run (sandboxed, real namespaces)"
set +e
workflo run --path "$FIXTURE" --test --timeout 300 >run.stdout 2>run.stderr
RUN_EXIT=$?
set -e
cat run.stderr
cat run.stdout

# The CLI writes the receipt next to the run evidence
RECEIPT=$(find .workflo/runs -name receipt.json -type f | head -1)
if [ -z "$RECEIPT" ]; then
  echo "GOLDEN RUN FAILED: no receipt produced" >&2
  cat run.stderr >&2
  exit 1
fi

echo
echo "==> workflo verify (independent verification of the receipt)"
set +e
bash "$REPO_ROOT/scripts/linux/package_receipt_key.sh" "$RECEIPT"
PUBKEY="$(dirname "$RECEIPT")/receipt-key.pub.pem"
EVIDENCE="$(dirname "$RECEIPT")/evidence"

workflo verify --receipt "$RECEIPT" --pubkey "$PUBKEY" --evidence "$EVIDENCE" >verify.stdout 2>verify.stderr
VERIFY_EXIT=$?
set -e
cat verify.stderr
cat verify.stdout

echo
echo "==> Golden run summary"
echo "    run exit:      $RUN_EXIT"
echo "    verify exit:   $VERIFY_EXIT"
echo "    receipt:       $RECEIPT"

if [ "$RUN_EXIT" -ne 0 ] || [ "$VERIFY_EXIT" -ne 0 ]; then
  echo "GOLDEN RUN FAILED" >&2
  exit 1
fi
echo "GOLDEN RUN PASSED: run -> sandbox -> evidence -> signed receipt -> verified"
