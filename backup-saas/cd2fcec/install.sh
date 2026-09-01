#!/bin/sh
# Local-repo installer for the workflo CLI.
# Gives the pip-install experience without publishing to PyPI: the four
# sibling packages exist only in this monorepo, so they are installed from
# the checkout in dependency order, then the CLI.
#
# Usage (demo / Unix):
#   ./install.sh
#   . .workflo-venv/bin/activate
#
# This is not `pip install workflo-cli` from the public internet. That is
# post-demo work. Do not pretend otherwise.

set -e

ROOT=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
cd "$ROOT"

if [ ! -f packages/core-schema/pyproject.toml ] || [ ! -f apps/workflo-cli/pyproject.toml ]; then
    echo "install.sh must be run from a workflo checkout (packages/ and apps/ missing)" >&2
    exit 1
fi

if command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
elif command -v python >/dev/null 2>&1; then
    PYTHON=python
else
    echo "Python 3.11+ is required but was not found on PATH" >&2
    exit 1
fi

if ! "$PYTHON" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"; then
    echo "Python 3.11+ is required (found $("$PYTHON" --version 2>&1))" >&2
    exit 1
fi

echo "Installing workflo..."
echo "  → Setting up environment..."
"$PYTHON" -m venv .workflo-venv

if [ -f .workflo-venv/bin/activate ]; then
    # Unix / macOS
    . .workflo-venv/bin/activate
elif [ -f .workflo-venv/Scripts/activate ]; then
    # Windows Git Bash / MSYS — venv puts scripts in Scripts/, not bin/
    . .workflo-venv/Scripts/activate
else
    echo "Installation failed — venv activate script not found" >&2
    exit 1
fi

# Hide pip's "new release available" nags so the demo narration stays clean.
export PIP_DISABLE_PIP_VERSION_CHECK=1

# One resolver graph for the four local packages so pip does not try to
# fetch tenant-shield-schema / airlock-sandbox-isolation / etc. from PyPI.
# Install them before the CLI: workflo-cli declares those names as deps.
echo "  → Installing core packages..."
pip install --quiet \
    -e packages/core-schema \
    -e packages/sandbox-isolation \
    -e apps/sandbox-executor \
    -e packages/probe-engine

echo "  → Installing workflo CLI..."
pip install --quiet -e apps/workflo-cli

echo "  → Verifying installation..."
if ! command -v workflo >/dev/null 2>&1; then
    echo "Installation failed — workflo not found on PATH" >&2
    exit 1
fi

echo "✓ workflo installed ($(workflo --version))"
echo ""
echo "New shell? Activate first:"
echo "  source .workflo-venv/bin/activate          (bash/zsh/Git Bash)"
echo "  .\\.workflo-venv\\Scripts\\Activate.ps1     (PowerShell)"
echo ""
echo "Then get started:"
echo "  workflo run --repo <repo-url> --test --security --dry-run"
