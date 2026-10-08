#!/bin/bash
# The AGENT golden run: full deep tier (app boot + governed agent) via the
# real CLI surface, then independent verification.
set -euo pipefail
REPO_ROOT="${WORKFLO_REPO_ROOT:-$(cd "$(dirname "${0}")/../.." && pwd)}"
export PATH="/opt/workflo/venv/bin:$PATH"

if [ "$(id -u)" -ne 0 ]; then echo "must run as root" >&2; exit 1; fi

WORK=/root/wf-agent-golden
rm -rf "$WORK"; mkdir -p "$WORK"; cd "$WORK"

echo "==> workflo run --path fixture --deep-test (app + governed agent)"
set +e
workflo run --path /root/wf-fixture --deep-test --start-command "python3 app.py" --port 3457 --timeout 300 \
  >run.stdout 2>run.stderr
RUN_EXIT=$?
set -e
grep -E 'Tests:|Agent:|Canary|removed|terminated|gone|Signed receipt|Duration' run.stderr || true
cat run.stdout | tail -5

RECEIPT=$(find .workflo/runs -name receipt.json -type f | head -1)
if [ -z "$RECEIPT" ]; then
  echo "AGENT GOLDEN FAILED: no receipt" >&2
  grep -E 'error|Supervisor' run.stderr >&2 | head -5
  exit 1
fi

echo
echo "==> workflo verify (independent)"
set +e
workflo verify --receipt "$RECEIPT" >verify.stdout 2>verify.stderr
VERIFY_EXIT=$?
set -e
cat verify.stderr

echo
echo "    run exit:    $RUN_EXIT"
echo "    verify exit: $VERIFY_EXIT"
[ "$RUN_EXIT" -ne 0 ] && { echo "AGENT GOLDEN FAILED (run)"; exit 1; }
[ "$VERIFY_EXIT" -ne 0 ] && { echo "AGENT GOLDEN FAILED (verify)"; exit 1; }
echo "AGENT GOLDEN PASSED: app boot -> governed agent -> evidence -> signed receipt -> verified"
