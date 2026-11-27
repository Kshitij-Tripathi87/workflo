#!/usr/bin/env bash
# Reproducible Python environment + per-project test runner for this monorepo.
#
# Why this exists: the repository contains ~20 independent Python projects
# (packages/, apps/, supervisor/, worker/, backend/, workflo-ai-integration/).
# They are NOT a single installable workspace — they are separate setuptools
# projects that resolve each other by distribution name (workflo-schema,
# sandbox-isolation, ...). A fresh clone therefore cannot run any suite until
# several of them are installed editable, in dependency order, and there was no
# script that did that: every suite failed with ModuleNotFoundError and looked
# like a code defect.
#
# Usage:
#   scripts/python-env.sh install        # editable install of every project + dev tools
#   scripts/python-env.sh test           # run every project's suite separately
#   scripts/python-env.sh test worker apps/control-plane
#   scripts/python-env.sh list           # show the projects and their reported state
#
# Suites MUST run in separate pytest processes: several projects use the same
# top-level `tests` package name and collide if collected together (surfacing as
# "import file mismatch"), which is why this loops rather than collecting once.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || exit 1

PYTHON="${PYTHON:-python}"

# Dependency order: libraries first, then the apps that import them, then the
# standalone services. Keep this list in sync with the known-good state.
PACKAGES=(
  packages/workflo-schema
  packages/workflo-utils
  packages/sandbox-isolation
  packages/sandbox-runtime
  packages/probe-engine
  packages/cortex-auth
  packages/workflo-datahub
  workflo-ai-integration
  supervisor
  apps/sandbox-executor
  apps/validation-cli
  apps/workflo-cli
  apps/agent-cli
  apps/worker-engine
  apps/control-plane
  worker
)

# Projects that still ship their own requirements.txt instead of (or in addition
# to) a pyproject dependency set.
REQUIREMENTS=(
  backend
)

DEV_TOOLS=(
  pytest pytest-asyncio pytest-cov pytest-timeout pytest-mock
  pytest-json-report respx ruff mypy
)

# Suites to execute. `worker` and `backend` are listed explicitly because their
# test layout is not under an apps/ or packages/ parent.
SUITES=(
  "${PACKAGES[@]}"
  backend
)

cmd_install() {
  echo "==> installing dev tools"
  "$PYTHON" -m pip install --quiet "${DEV_TOOLS[@]}" || return 1

  echo "==> installing ${#PACKAGES[@]} Python projects (editable, dependency order)"
  local args=()
  local p
  for p in "${PACKAGES[@]}"; do
    args+=(-e "$p")
  done
  "$PYTHON" -m pip install --quiet "${args[@]}" || return 1

  for p in "${REQUIREMENTS[@]}"; do
    [ -f "$p/requirements.txt" ] || continue
    echo "==> installing $p/requirements.txt"
    "$PYTHON" -m pip install --quiet -r "$p/requirements.txt" || return 1
  done

  echo "install complete"
}

cmd_test() {
  local targets=("$@")
  if [ ${#targets[@]} -eq 0 ]; then
    targets=("${SUITES[@]}")
  fi
  local p summary="" failures=0
  for p in "${targets[@]}"; do
    if [ ! -d "$p/tests" ]; then
      printf '%-32s %s\n' "$p" "(no tests/ directory — skipped)"
      continue
    fi
    local out
    out="$(cd "$p" && timeout 600 "$PYTHON" -m pytest tests -q -p no:cacheprovider 2>&1 | tail -1)"
    printf '%-32s %s\n' "$p" "$out"
    case "$out" in
      *failed*|*error*) failures=$((failures + 1)) ;;
    esac
  done
  echo
  if [ "$failures" -gt 0 ]; then
    echo "$failures suite(s) reported failures"
    return 1
  fi
  echo "all suites reported success"
}

cmd_list() {
  local p
  for p in "${SUITES[@]}"; do
    [ -d "$p/tests" ] && printf '%-32s %s tests files\n' "$p" "$(find "$p/tests" -name 'test_*.py' | wc -l | tr -d ' ')"
  done
}

case "${1:-}" in
  install) shift; cmd_install "$@" ;;
  test)    shift; cmd_test "$@" ;;
  list)    cmd_list ;;
  *)
    echo "usage: $0 {install|test [project...]|list}" >&2
    exit 2
    ;;
esac
