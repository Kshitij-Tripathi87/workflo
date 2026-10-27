#!/usr/bin/env bash
# One definition of green (re-baselined roadmap, section 8).
#
# Runs, in order, failing closed on the first red signal:
#   1. JS workspace: pnpm install --frozen-lockfile, lint, typecheck, test
#   2. Python: per-package pytest suites (packages run separately)
#   3. CLI smoke: --help, plan dry-run (exit 0), no-backend run (exit 6)
#
# Nothing is "done" until this is green and, for CI, the fresh-install
# gate is green with the run URL recorded in docs/progress.md.
#
# Usage:
#   ./scripts/verify.sh                 # full run (JS + Python + smoke)
#   ./scripts/verify.sh --skip-js       # Python + smoke only
#   ./scripts/verify.sh --skip-python   # JS only
#   ./scripts/verify.sh --smoke-only    # CLI smoke only

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SKIP_JS=0
SKIP_PYTHON=0
SMOKE_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --skip-js) SKIP_JS=1 ;;
    --skip-python) SKIP_PYTHON=1 ;;
    --smoke-only) SMOKE_ONLY=1; SKIP_JS=1; SKIP_PYTHON=1 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

echo "[verify] root: $ROOT"

if [ "$SKIP_JS" != "1" ]; then
  echo "[verify] JS: pnpm install --frozen-lockfile"
  pnpm install --frozen-lockfile > /dev/null
  echo "[verify] JS: pnpm lint"
  pnpm lint
  echo "[verify] JS: pnpm typecheck"
  pnpm typecheck
  echo "[verify] JS: pnpm test"
  pnpm test
fi

if [ "$SKIP_PYTHON" != "1" ]; then
  if [ ! -x .workflo-venv/bin/python ] && [ ! -x .workflo-venv/Scripts/python.exe ]; then
    echo "[verify] creating .workflo-venv (python3 -m venv)"
    python3 -m venv .workflo-venv
    VPIP=".workflo-venv/bin/pip"
    "$VPIP" install --quiet --upgrade pip
    echo "[verify] installing local packages (dependency order)"
    "$VPIP" install --quiet \
      -e packages/workflo-schema \
      -e packages/workflo-utils \
      -e packages/sandbox-isolation \
      -e packages/sandbox-runtime \
      -e packages/cortex-auth \
      -e apps/sandbox-executor \
      -e packages/probe-engine \
      -e workflo-ai-integration \
      -e apps/worker-engine \
      -e apps/control-plane \
      -e apps/agent-cli \
      -e apps/validation-cli \
      -e packages/workflo-datahub \
      -e "apps/workflo-cli[dev]"
  fi
  if [ -x .workflo-venv/bin/python ]; then
    VPY=".workflo-venv/bin/python"
  else
    VPY=".workflo-venv/Scripts/python.exe"
  fi
  # Hosts with a locked default pytest temp root can override the basetemp:
  #   WORKFLO_PYTEST_BASETEMP=/some/writable/dir ./scripts/verify.sh
  PYTEST_BASETEMP_ARGS=()
  if [ -n "${WORKFLO_PYTEST_BASETEMP:-}" ]; then
    PYTEST_BASETEMP_ARGS=(--basetemp "$WORKFLO_PYTEST_BASETEMP")
  fi
  for suite in \
    apps/agent-cli \
    apps/control-plane \
    apps/sandbox-executor \
    apps/validation-cli \
    apps/worker-engine \
    apps/workflo-cli \
    packages/cortex-auth \
    packages/probe-engine \
    packages/sandbox-isolation \
    packages/sandbox-runtime \
    packages/workflo-datahub \
    packages/workflo-schema \
    packages/workflo-utils \
    workflo-ai-integration
  do
    echo "[verify] pytest $suite"
    (cd "$suite" && "$ROOT/$VPY" -m pytest tests -q --timeout=180 "${PYTEST_BASETEMP_ARGS[@]}")
  done
fi

echo "[verify] CLI smoke"
WF=".workflo-venv/bin/workflo"
[ -x "$WF" ] || WF=".workflo-venv/Scripts/workflo.exe"
"$WF" --help > /dev/null
echo "[verify] CLI smoke: --help OK"

SMOKE_DIR="$(mktemp -d)"
trap 'rm -rf "$SMOKE_DIR"' EXIT
printf 'def test_pass():\n    assert True\n' > "$SMOKE_DIR/test_sample.py"

"$WF" run --path "$SMOKE_DIR" --test --dry-run > /dev/null
echo "[verify] CLI smoke: dry-run exit 0 OK"

# A host without a sandbox backend must fail closed with the documented
# infrastructure exit code (6) and a one-line reason on stderr.
set +e
"$WF" run --path "$SMOKE_DIR" --test --backend namespaces 2> "$SMOKE_DIR/err.txt"
rc=$?
set -e
if [ "$rc" -ne 6 ]; then
  echo "[verify] CLI smoke: expected exit 6 without a namespaces backend, got $rc" >&2
  cat "$SMOKE_DIR/err.txt" >&2
  exit 1
fi
if ! grep -q . "$SMOKE_DIR/err.txt"; then
  echo "[verify] CLI smoke: expected a stderr reason with exit 6, got silence" >&2
  exit 1
fi
echo "[verify] CLI smoke: no-backend preflight exit 6 with stderr reason OK"

echo "[verify] GREEN"
