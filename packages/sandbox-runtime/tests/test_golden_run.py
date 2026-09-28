"""Day 14 — golden run (cross-platform): repo → planner → agent → judge →
signed, verified receipt.

Everything real that can run without Linux namespaces:

  github_connector : real git protocol against a local repo (resolve →
                     pinned SHA → clone)
  planner          : real planner loop against a stub /chat/completions
  agent            : real governed ToolGateway against a real local HTTP
                     app (discovery host rewritten by the test opener —
                     policy/allowlist checks themselves run untouched)
  judge            : deterministic confirmation over governed records
  receipt          : SignedReceipt with mission + provenance + findings,
                     Ed25519-signed and verified

The sandbox/isolation stages are proven by test_supervisor_receipt.py;
this harness proves the AGENT layer that Day 14's demo depends on.
"""

from __future__ import annotations

import json
import subprocess
import threading
import urllib.request
from datetime import datetime, UTC
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from sandbox_runtime.github_connector import (
    build_provenance, clone_pinned, parse_repository_url, resolve_ref,
)
from sandbox_runtime.judge import judge_findings
from sandbox_runtime.planner import run_planner_loop


# ---------------------------------------------------------------------------
# Stub LLM: scripted plans, one per /chat/completions call
# ---------------------------------------------------------------------------

class _StubLLM(BaseHTTPRequestHandler):
    plans: list[dict] = []

    def do_GET(self):
        if self.path == "/models":
            self._respond(200, {"data": [{"id": "workflo-agent-v1"}]})
        else:
            self._respond(404, {})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        plan = self.plans.pop(0) if self.plans else {"done": True, "steps": []}
        content = json.dumps(plan)
        self._respond(200, {"choices": [{"message": {
            "role": "assistant", "content": content}}]})

    def _respond(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


# ---------------------------------------------------------------------------
# Stub target app: everything healthy except POST /checkout (500)
# ---------------------------------------------------------------------------

class _StubApp(BaseHTTPRequestHandler):
    def do_GET(self):
        self._respond(200 if self.path in ("/", "/health") else 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        self._respond(500 if self.path == "/checkout" else 200)

    def _respond(self, code):
        body = b"{}"
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def _server(handler_cls):
    httpd = HTTPServer(("127.0.0.1", 0), handler_cls)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def _git(args, cwd):
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


@pytest.fixture
def fixture_repo(tmp_path):
    """A real git repo standing in for github.com/customer/app."""
    repo = tmp_path / "origin"
    repo.mkdir()
    (repo / "README.md").write_text("# demo shop\n")
    (repo / "app.py").write_text("# flask-ish app; /checkout is broken\n")
    _git(["init", "-q", "-b", "main"], repo)
    _git(["config", "user.email", "t@example.com"], repo)
    _git(["config", "user.name", "t"], repo)
    _git(["add", "."], repo)
    _git(["commit", "-q", "-m", "initial"], repo)
    sha = _git(["rev-parse", "HEAD"], repo)
    return {"path": repo, "sha": sha}


# ---------------------------------------------------------------------------

def test_golden_run_agent_layer(fixture_repo, tmp_path, monkeypatch):
    app = _server(_StubApp)
    llm = _server(_StubLLM)
    try:
        app_port = app.server_port
        app_url = f"http://app.workflo.internal:{app_port}"

        # The app dies twice on /checkout (reproducible failure), then done.
        _StubLLM.plans = [
            {"done": False, "steps": [
                {"tool": "http_get", "args": {"url": f"{app_url}/"},
                 "reason": "smoke"},
                {"tool": "http_get", "args": {"url": f"{app_url}/health"},
                 "reason": "liveness"},
            ]},
            {"done": False, "steps": [
                {"tool": "http_post",
                 "args": {"url": f"{app_url}/checkout", "body": {"items": 2}},
                 "reason": "exercise checkout"},
            ]},
            {"done": False, "steps": [
                {"tool": "http_post",
                 "args": {"url": f"{app_url}/checkout", "body": {"items": 3}},
                 "reason": "reproduce"},
            ]},
        ]

        monkeypatch.setenv("WORKFLO_LLM_BASE_URL",
                           f"http://127.0.0.1:{llm.server_port}")
        monkeypatch.setenv("WORKFLO_LLM_API_KEY", "test-key")
        monkeypatch.setenv("WORKFLO_LLM_MODEL", "workflo-agent-v1")
        monkeypatch.setenv("WORKFLO_LLM_TIMEOUT", "10")

        # ---- 1. Git connector: ref -> exact commit -> pinned clone -----
        spec = parse_repository_url(f"file://{fixture_repo['path']}")
        resolved = resolve_ref(spec.clone_url, "main")
        assert resolved.commit_sha == fixture_repo["sha"]
        clone_dir = tmp_path / "clone" / "repo"
        clone_pinned(spec.clone_url, resolved.commit_sha, clone_dir)
        assert (clone_dir / "app.py").exists()

        # ---- 2. Planner drives the agent through the file protocol -----
        artifacts = tmp_path / "artifacts"
        artifacts.mkdir()

        from workflo_worker.agent_runner import execute_step
        from workflo_worker.agent_tools import ToolGateway

        records_path = artifacts / "agent_tool_calls.jsonl"
        plan_path = artifacts / "plan.json"
        obs_path = artifacts / "observations.json"

        def sandbox_opener(request, timeout=None):
            # Test transport: internal hosts route to the stub app. The
            # ToolGateway allowlist ran on the ORIGINAL url before this —
            # policy is exercised, only DNS is simulated.
            url = request.full_url.replace(
                "app.workflo.internal", "127.0.0.1"
            )
            req = urllib.request.Request(url, data=request.data,
                                         method=request.get_method())
            return urllib.request.urlopen(req, timeout=timeout)

        gateway = ToolGateway(records_path, opener=sandbox_opener)

        def agent_side():
            """The sandboxed half of the golden run (in-process)."""
            last_seq = 0
            for _ in range(50):
                if not plan_path.exists():
                    import time; time.sleep(0.05); continue
                try:
                    plan = json.loads(plan_path.read_text())
                except json.JSONDecodeError:
                    continue
                if plan.get("seq", 0) <= last_seq:
                    import time; time.sleep(0.05); continue
                last_seq = plan["seq"]
                observations = []
                for step in plan.get("steps", [])[:12]:
                    observations.append(execute_step(gateway, step))
                obs_path.write_text(json.dumps({
                    "seq": last_seq,
                    "tool_calls": gateway.tool_calls,
                    "observations": observations,
                }))
                if plan.get("done"):
                    return

        agent_thread = threading.Thread(target=agent_side, daemon=True)
        agent_thread.start()

        mission = "Test authentication and checkout"
        planner_result = run_planner_loop(
            artifacts, app_url, max_batches=6, max_tool_calls=40,
            mission=mission,
        )
        agent_thread.join(timeout=15)
        assert planner_result["planner"] == "llm"
        assert planner_result["mission"] == mission

        # ---- 3. Judge the governed records ------------------------------
        records = [
            json.loads(line)
            for line in records_path.read_text().splitlines() if line.strip()
        ]
        assert len(records) >= 4
        report = judge_findings(records)
        assert report.confirmed == 1
        assert report.findings[0]["title"].startswith("POST /checkout")

        # ---- 4. Receipt: mission + provenance + findings, signed+verified
        from sandbox_isolation import generate_keypair, verify_receipt_signature
        from workflo_schema.sandbox import SignedReceipt

        provenance = build_provenance(spec, resolved, snapshot_digest="ab" * 32)
        payload = {
            "receipt_version": 4,
            "sandbox_id": "golden-01",
            "issued_at": datetime.now(UTC).isoformat(),
            "run_report": {
                "sandbox_id": "golden-01",
                "run_id": "golden-01",
                "total": 0, "passed": 0, "failed": 0, "skipped": 0,
                "duration_seconds": 1.0,
                "findings": report.findings,
            },
            "teardown_proof": {
                "sandbox_id": "golden-01",
                "runtime_type": "namespaces",
                "destroyed_at": datetime.now(UTC).isoformat(),
                "container_removed": True,
                "filesystem_removed": True,
                "processes_terminated": True,
                "cgroup_removed": True,
                "network_namespace_removed": True,
                "workspace_removed": True,
                "no_snapshot_retained": True,
                "session_duration_seconds": 1.0,
                "events_count": 1,
            },
            "canary_check": {
                "sandbox_id": "golden-01",
                "attempted_at": datetime.now(UTC).isoformat(),
                "target_host": "example.com",
                "request_succeeded": False,
            },
            "repository": provenance,
            "agent_activity": {
                "tool_calls": gateway.tool_calls,
                "tools_used": gateway.tools_used,
                "steps_total": len(records),
                "steps_completed": sum(1 for r in records if r.get("ok")),
                "steps_failed": sum(1 for r in records if not r.get("ok")),
                "denied_attempts": gateway.denied_attempts,
                "errors": gateway.errors,
                "planner": "llm",
                "mission": mission,
            },
            "signature_algorithm": "ed25519",
        }
        signer = generate_keypair()
        receipt = SignedReceipt(**payload)
        signed = signer.sign(receipt)

        assert verify_receipt_signature(signed, signer.public_key)
        assert signed.repository.commit == fixture_repo["sha"]
        assert signed.agent_activity.mission == mission
        assert signed.run_report.findings[0]["status"] == "confirmed"

        # A tampered finding must NOT verify.
        forged = signed.model_copy(deep=True)
        forged.run_report.findings[0]["severity"] = "info"
        assert not verify_receipt_signature(forged, signer.public_key)
    finally:
        app.shutdown()
        llm.shutdown()
