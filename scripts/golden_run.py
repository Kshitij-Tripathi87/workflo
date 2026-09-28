#!/usr/bin/env python3
"""Workflo golden run — the Day-14 demo, executable standalone.

Runs the full agent-layer path with real components:

    git repo --(connector)--> pinned commit
    planner --(stub LLM)--> batches of governed actions
    ToolGateway --(stub app)--> bounded observations
    judge --> confirmed findings
    receipt --> signed -> verified -> receipt JSON on disk

    python scripts/golden_run.py [--out .workflo/golden]

No Linux required: this proves the agent product loop. The full sandboxed
(bwrap/netns) run is proven by the supervisor test suite and the Linux
integration harness.

Standard library + the repo's own installed packages.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from datetime import datetime, UTC
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for pkg in ("sandbox-runtime", "workflo-schema", "sandbox-isolation"):
    sys.path.insert(0, str(REPO_ROOT / "packages" / pkg / "src"))
sys.path.insert(0, str(REPO_ROOT / "apps" / "worker-engine" / "src"))
sys.path.insert(0, str(REPO_ROOT / "apps" / "sandbox-executor" / "src"))

MISSION = "Test authentication, health, and checkout"


class StubLLM(BaseHTTPRequestHandler):
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
        self._respond(200, {"choices": [{"message": {
            "role": "assistant", "content": json.dumps(plan)}}]})

    def _respond(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class StubApp(BaseHTTPRequestHandler):
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


def _serve(handler):
    httpd = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def _git(args, cwd):
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip())
    return proc.stdout.strip()


def make_fixture_repo(root: Path) -> dict:
    repo = root / "origin"
    repo.mkdir(parents=True)
    (repo / "README.md").write_text("# demo shop\n")
    (repo / "app.py").write_text("# demo app; POST /checkout is broken\n")
    _git(["init", "-q", "-b", "main"], repo)
    _git(["config", "user.email", "golden@workflo.local"], repo)
    _git(["config", "user.name", "golden"], repo)
    _git(["add", "."], repo)
    _git(["commit", "-q", "-m", "initial"], repo)
    return {"path": repo, "sha": _git(["rev-parse", "HEAD"], repo)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Workflo golden run")
    parser.add_argument("--out", default=".workflo/golden")
    args = parser.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    from sandbox_runtime.github_connector import (
        build_provenance, clone_pinned, parse_repository_url, resolve_ref,
    )
    from sandbox_runtime.judge import judge_findings
    from sandbox_runtime.planner import run_planner_loop

    app = _serve(StubApp)
    llm = _serve(StubLLM)
    try:
        app_port = app.server_port
        app_url = f"http://app.workflo.internal:{app_port}"

        StubLLM.plans = [
            {"done": False, "steps": [
                {"tool": "http_get", "args": {"url": f"{app_url}/"},
                 "reason": "smoke"},
                {"tool": "http_get", "args": {"url": f"{app_url}/health"},
                 "reason": "liveness"},
            ]},
            {"done": False, "steps": [
                {"tool": "http_post",
                 "args": {"url": f"{app_url}/checkout", "body": {"items": 2}},
                 "reason": "exercise checkout"}]},
            {"done": False, "steps": [
                {"tool": "http_post",
                 "args": {"url": f"{app_url}/checkout", "body": {"items": 3}},
                 "reason": "reproduce"}]},
        ]

        import os
        os.environ["WORKFLO_LLM_BASE_URL"] = f"http://127.0.0.1:{llm.server_port}"
        os.environ["WORKFLO_LLM_API_KEY"] = "golden"
        os.environ["WORKFLO_LLM_MODEL"] = "workflo-agent-v1"
        os.environ["WORKFLO_LLM_TIMEOUT"] = "10"

        print("== golden run ==")
        print(f"mission: {MISSION}")

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)

            # 1. Repo -----------------------------------------------------
            fixture = make_fixture_repo(tmp)
            spec = parse_repository_url(f"file://{fixture['path']}")
            resolved = resolve_ref(spec.clone_url, "main")
            clone_dir = tmp / "clone" / "repo"
            clone_pinned(spec.clone_url, resolved.commit_sha, clone_dir)
            print(f"[git] {spec.repository} main -> {resolved.commit_sha[:12]}")

            # 2. Planner <-> agent ---------------------------------------
            from workflo_worker.agent_runner import execute_step
            from workflo_worker.agent_tools import ToolGateway

            artifacts = out_dir / "artifacts"
            artifacts.mkdir(exist_ok=True)
            records_path = artifacts / "agent_tool_calls.jsonl"
            plan_path = artifacts / "plan.json"
            obs_path = artifacts / "observations.json"

            def sandbox_opener(request, timeout=None):
                url = request.full_url.replace("app.workflo.internal", "127.0.0.1")
                req = urllib.request.Request(url, data=request.data,
                                             method=request.get_method())
                return urllib.request.urlopen(req, timeout=timeout)

            gateway = ToolGateway(records_path, opener=sandbox_opener)

            def agent_side():
                last = 0
                for _ in range(60):
                    if not plan_path.exists():
                        time.sleep(0.05); continue
                    try:
                        plan = json.loads(plan_path.read_text())
                    except json.JSONDecodeError:
                        continue
                    if plan.get("seq", 0) <= last:
                        time.sleep(0.05); continue
                    last = plan["seq"]
                    observations = [
                        execute_step(gateway, step)
                        for step in plan.get("steps", [])[:12]
                    ]
                    obs_path.write_text(json.dumps({
                        "seq": last, "tool_calls": gateway.tool_calls,
                        "observations": observations,
                    }))
                    for o in observations:
                        print(f"  [agent] {o['tool']} {o['description']} "
                              f"-> {o['detail']}{' (DENIED)' if o['denied'] else ''}")
                    if plan.get("done"):
                        return

            agent_thread = threading.Thread(target=agent_side, daemon=True)
            agent_thread.start()
            planner_result = run_planner_loop(
                artifacts, app_url, max_batches=6, max_tool_calls=40,
                mission=MISSION,
            )
            agent_thread.join(timeout=30)
            print(f"[planner] {planner_result['batches']} batches")

            # 3. Judge ----------------------------------------------------
            records = [json.loads(line)
                       for line in records_path.read_text().splitlines()
                       if line.strip()]
            judged = judge_findings(records)
            for finding in judged.findings:
                print(f"[finding:{finding['status']}] {finding['title']}")

            # 4. Receipt --------------------------------------------------
            from sandbox_isolation import generate_keypair, verify_receipt_signature
            from workflo_schema.sandbox import SignedReceipt

            provenance = build_provenance(spec, resolved, snapshot_digest=None)
            payload = {
                "receipt_version": 4,
                "sandbox_id": "golden-run",
                "issued_at": datetime.now(UTC).isoformat(),
                "run_report": {
                    "sandbox_id": "golden-run",
                    "run_id": "golden-run",
                    "total": 0, "passed": 0, "failed": 0, "skipped": 0,
                    "duration_seconds": 1.0,
                    "findings": judged.findings,
                },
                "teardown_proof": {
                    "sandbox_id": "golden-run",
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
                    "sandbox_id": "golden-run",
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
                    "mission": MISSION,
                },
                "signature_algorithm": "ed25519",
            }
            signer = generate_keypair()
            receipt = SignedReceipt(**payload)
            signed = signer.sign(receipt)
            ok = verify_receipt_signature(signed, signer.public_key)

            receipt_path = out_dir / "receipt.json"
            receipt_path.write_text(signed.model_dump_json(indent=2),
                                    encoding="utf-8")
            key_path = out_dir / "golden.pub.pem"
            from cryptography.hazmat.primitives import serialization
            key_path.write_bytes(signer.public_key.public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            ))
            print(f"[receipt] {receipt_path}  signature={'VALID' if ok else 'INVALID'}")
            print(f"[pubkey ] {key_path}")
            print(f"[verify ] workflo verify --receipt {receipt_path} "
                  f"--pubkey {key_path}")
            return 0 if ok else 1
    finally:
        app.shutdown()
        llm.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
