#!/usr/bin/env bash
# One-command Workflo agent execution demo.
#
# Modes:
#   quick          deterministic ToolGateway run + scripted planner run (no model API key)
#   task-spec      deterministic, model-free agent run
#   scripted       local scripted LLM drives the real sandboxed agent (no external API)
#   model          configured real OpenAI-compatible / Workflo gateway planner
#   all            quick + configured real model run
#
# Development/CI only: current execution path is Linux namespaces + bubblewrap.
# This script does NOT claim Firecracker/KVM Gate B or production isolation.
set -Eeuo pipefail

usage() {
  cat <<'USAGE'
Usage:
  sudo -E bash scripts/linux/demo_agent_execution.sh [options]

Options:
  --mode MODE          quick|task-spec|scripted|model|all (default: quick)
  --fixture PATH       fixture Git repository (default: /root/wf-fixture)
  --output-dir PATH    new output directory (default: /root/workflo-agentic-demo-<UTC>)
  --mission TEXT       objective for the configured model planner
  --help               show this help

Examples:
  sudo -E bash scripts/linux/demo_agent_execution.sh
  sudo -E bash scripts/linux/demo_agent_execution.sh --mode scripted
  sudo -E bash scripts/linux/demo_agent_execution.sh --mode model \
    --mission "Explore checkout, test authentication errors, and report reproducible failures."

One-time Linux/WSL2 Ubuntu setup:
  sudo bash scripts/linux/setup_env.sh

For --mode model, configure and validate the model first:
  workflo config set-llm --base-url <endpoint> --api-key <key> --model <model>
  workflo config test-llm

The API key is stored by the existing Workflo credential-store path; it is not written
into this script or copied into the guest. Gateway mode is preferred where available.
USAGE
}

MODE="quick"
FIXTURE="${WORKFLO_DEMO_FIXTURE:-/root/wf-fixture}"
OUTPUT_DIR=""
MISSION="Explore the application, probe its health and key flows, inspect runtime evidence, and report reproducible failures."

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode) MODE="${2:?missing value for --mode}"; shift 2 ;;
    --fixture) FIXTURE="${2:?missing value for --fixture}"; shift 2 ;;
    --output-dir) OUTPUT_DIR="${2:?missing value for --output-dir}"; shift 2 ;;
    --mission) MISSION="${2:?missing value for --mission}"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$MODE" in
  quick|task-spec|scripted|model|all) ;;
  *) echo "Unsupported mode: $MODE" >&2; usage >&2; exit 2 ;;
esac

if [[ "$(id -u)" -ne 0 ]]; then
  command -v sudo >/dev/null 2>&1 || { echo "sudo is required; run this demo as root." >&2; exit 2; }
  sudo_args=(--mode "$MODE" --fixture "$FIXTURE" --mission "$MISSION")
  if [[ -n "$OUTPUT_DIR" ]]; then
    sudo_args+=(--output-dir "$OUTPUT_DIR")
  fi
  exec sudo -E bash "$0" "${sudo_args[@]}"
fi

REPO_ROOT="${WORKFLO_REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
WORKFLO_BIN="/opt/workflo/venv/bin/workflo"
export PATH="/opt/workflo/venv/bin:$PATH"

for cmd in bwrap ip nft dnsmasq git python3; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "Missing prerequisite: $cmd. Run: sudo bash $REPO_ROOT/scripts/linux/setup_env.sh" >&2
    exit 2
  }
done
[[ -x "$WORKFLO_BIN" ]] || {
  echo "Workflo CLI not installed at $WORKFLO_BIN. Run: sudo bash $REPO_ROOT/scripts/linux/setup_env.sh" >&2
  exit 2
}
[[ -f /opt/workflo/workflo-worker/opt/workflo/runtime/workflo_worker/agent_runner.py ]] || {
  echo "Agent runtime image missing. Run: sudo bash $REPO_ROOT/scripts/linux/setup_env.sh" >&2
  exit 2
}
[[ -d "$FIXTURE" && -f "$FIXTURE/app.py" ]] || {
  echo "Fixture app missing at $FIXTURE. Run setup_env.sh or pass --fixture <git-repo-with-app.py>." >&2
  exit 2
}
git -C "$FIXTURE" rev-parse --is-inside-work-tree >/dev/null 2>&1 || {
  echo "Fixture must be a Git repository so Workflo can snapshot an exact revision: $FIXTURE" >&2
  exit 2
}
FIXTURE="$(cd "$FIXTURE" && pwd)"

if [[ -z "$OUTPUT_DIR" ]]; then
  OUTPUT_DIR="/root/workflo-agentic-demo-$(date -u +%Y%m%dT%H%M%SZ)"
fi
OUTPUT_DIR="$(mkdir -p "$(dirname "$OUTPUT_DIR")" && cd "$(dirname "$OUTPUT_DIR")" && pwd)/$(basename "$OUTPUT_DIR")"
if [[ -e "$OUTPUT_DIR" || -L "$OUTPUT_DIR" ]]; then
  echo "Refusing to overwrite existing demo output: $OUTPUT_DIR" >&2
  exit 2
fi
mkdir -m 0700 "$OUTPUT_DIR"

echo "Workflo agent execution demo"
echo "  mode:       $MODE"
echo "  fixture:    $FIXTURE"
echo "  output:     $OUTPUT_DIR"
echo "  runtime:    Linux namespaces + bubblewrap (DEVELOPMENT/CI ONLY)"
echo "  production: Firecracker/KVM Gate B is a separate, unproven boundary"
echo

run_task_spec() {
  local case_dir="$OUTPUT_DIR/task-spec"
  local run_dir="${WORKFLO_AGENT_GOLDEN_DIR:-$case_dir/run}"
  mkdir -p "$case_dir"
  echo "==> task-spec: real sandboxed agent + governed tools, no model dependency"
  if env WORKFLO_REPO_ROOT="$REPO_ROOT" \
      WORKFLO_AGENT_FIXTURE="$FIXTURE" \
      WORKFLO_AGENT_GOLDEN_DIR="$run_dir" \
      WORKFLO_CONFIG_DIR="$case_dir/empty-config" \
      bash "$REPO_ROOT/scripts/linux/agent_golden_run.sh" >"$case_dir/driver.log" 2>&1; then
    tail -n 12 "$case_dir/driver.log" || true
    echo "PASS: task-spec"
  else
    local status=$?
    tail -n 60 "$case_dir/driver.log" >&2 || true
    echo "FAIL: task-spec (exit $status); diagnostics: $case_dir" >&2
    return "$status"
  fi
}

run_scripted_planner() {
  local case_dir="$OUTPUT_DIR/scripted-planner"
  local run_dir="${WORKFLO_PLANNER_GOLDEN_DIR:-$case_dir/run}"
  mkdir -p "$case_dir"
  echo "==> scripted-planner: local scripted model -> real sandboxed agent -> ToolGateway"
  if env WORKFLO_REPO_ROOT="$REPO_ROOT" \
      WORKFLO_PLANNER_FIXTURE="$FIXTURE" \
      WORKFLO_PLANNER_GOLDEN_DIR="$run_dir" \
      bash "$REPO_ROOT/scripts/linux/planner_golden_run.sh" >"$case_dir/driver.log" 2>&1; then
    tail -n 16 "$case_dir/driver.log" || true
    echo "PASS: scripted-planner"
  else
    local status=$?
    tail -n 60 "$case_dir/driver.log" >&2 || true
    echo "FAIL: scripted-planner (exit $status); diagnostics: $case_dir" >&2
    return "$status"
  fi
}

run_real_model_planner() {
  local case_dir="$OUTPUT_DIR/model-planner"
  local run_dir="$case_dir/run"
  local run_exit=0
  mkdir -p "$run_dir"

  # Preserve an explicitly selected config directory, otherwise use the
  # current root user's standard Workflo config location.
  local config_dir="${WORKFLO_CONFIG_DIR:-$HOME/.config/workflo}"
  mkdir -p "$config_dir"
  export WORKFLO_CONFIG_DIR="$(cd "$config_dir" && pwd)"
  echo "==> model-planner: configured model receives bounded observations and mission"
  "$WORKFLO_BIN" config test-llm >"$case_dir/model-check.log" 2>&1 || {
    cat "$case_dir/model-check.log" >&2
    echo "Configure a real model with 'workflo config set-llm' or run --mode scripted." >&2
    return 2
  }

  (
    cd "$run_dir"
    set +e
    "$WORKFLO_BIN" run --path "$FIXTURE" --deep-test \
      --start-command "python3 app.py" --port 3457 --timeout 300 \
      --instruction "$MISSION" >run.stdout 2>run.stderr
    run_exit=$?
    set -e
    echo "$run_exit" >run.exit
    # 0 = clean, 1 = QA findings; both produce a completed, verifiable run.
    if [[ "$run_exit" -gt 1 ]]; then
      echo "CLI infrastructure failure (exit $run_exit)" >&2
      tail -n 50 run.stderr >&2 || true
      exit "$run_exit"
    fi

    mapfile -t receipts < <(find .workflo/runs -type f -name receipt.json -print | sort)
    [[ "${#receipts[@]}" -eq 1 ]] || {
      echo "Expected exactly one receipt; found ${#receipts[@]}" >&2
      exit 3
    }
    receipt="${receipts[0]}"

    fingerprint="$(python3 - "$receipt" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
receipt = data.get("receipt", data)
activity = receipt.get("agent_activity") or {}
if activity.get("planner") != "llm":
    raise SystemExit("Run did not use the LLM planner; refusing a false model-demo claim")
if int(activity.get("tool_calls", 0)) < 1:
    raise SystemExit("LLM planner completed without any governed tool calls")
print(receipt.get("public_key_fingerprint") or "")
PY
)"
    [[ -n "$fingerprint" ]] || { echo "Receipt missing public_key_fingerprint" >&2; exit 3; }
    pubkey="$HOME/.config/workflo/keys/$fingerprint.pub.pem"
    [[ -s "$pubkey" ]] || { echo "Public key missing: $pubkey" >&2; exit 3; }
    evidence="$(dirname "$receipt")/evidence"
    "$WORKFLO_BIN" verify --receipt "$receipt" --pubkey "$pubkey" --evidence "$evidence" \
      >verify.stdout 2>verify.stderr
    echo "Verified real-model receipt: $receipt"
    cat verify.stderr
    echo "CLI exit: $run_exit (1 may indicate QA findings; receipt/trust verification passed)"
  ) >"$case_dir/driver.log" 2>&1 || {
    local status=$?
    tail -n 80 "$case_dir/driver.log" >&2 || true
    echo "FAIL: model-planner (exit $status); diagnostics: $case_dir" >&2
    return "$status"
  }

  tail -n 24 "$case_dir/driver.log" || true
  echo "PASS: model-planner"
}

case "$MODE" in
  task-spec)
    run_task_spec
    ;;
  scripted)
    run_scripted_planner
    ;;
  model)
    run_real_model_planner
    ;;
  quick)
    run_task_spec
    run_scripted_planner
    ;;
  all)
    run_task_spec
    run_scripted_planner
    run_real_model_planner
    ;;
esac

echo
echo "DEMO COMPLETE"
echo "Artifacts and verified receipts: $OUTPUT_DIR"
echo "Inspect per-run files under task-spec/run, scripted-planner/run, and/or model-planner/run."
