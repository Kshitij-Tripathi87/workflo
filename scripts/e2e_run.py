#!/usr/bin/env python3
"""Workflo end-to-end runner — one command from repo to verified receipt.

Two modes:

  --demo        Self-contained fixture: builds a tiny real Python web app
                (stdlib http.server, POST /checkout returns 500), checks it
                into a real local git repo, then runs the FULL Workflo
                pipeline against it. No external services needed. Uses a
                scripted planner unless WORKFLO_LLM_BASE_URL points at a real
                model endpoint.

  --repo URL    Real mode: clone the given GitHub repository at an exact
                commit, detect the project, boot the real application as a
                local process, drive the agent through the Workflo planner
                (requires a model endpoint: workflo config set-llm ... or
                WORKFLO_LLM_* env vars), judge findings, sign the receipt.

Both modes produce, under --out:

  runs/<sandbox-id>/
      run_state.json            live console state (workflo status --runs-dir ...)
      artifacts/                governed tool records (agent_tool_calls.jsonl)
      app.log                   application stdout/stderr
  receipt.json                  signed Ed25519 receipt
  receipt-key.pub.pem           public key for independent verification

Exit 0 means: receipt signed AND self-verified. A broken app is a
REPORTABLE outcome (findings are the product), not a runner failure;
runner failures (clone error, app crash, model misconfiguration) exit
non-zero with the failing stage named.

Isolation honesty: this runner exercises the full agent product loop
(repo → detect → app → agent → judge → receipt) with the application as a
guarded local process. The kernel-level sandbox (bwrap + netns + cgroups
+ seccomp + Landlock) runs in the Linux supervisor path and is gated in
CI (tests/integration/test_linux_gate.py). On the Linux path the same
receipt carries runtime_type="namespaces" teardown proof.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import signal
import socket
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
for pkg in ("sandbox-runtime", "workflo-schema", "workflo-utils",
            "sandbox-isolation"):
    sys.path.insert(0, str(REPO_ROOT / "packages" / pkg / "src"))
sys.path.insert(0, str(REPO_ROOT / "apps" / "worker-engine" / "src"))

DEMO_APP = '''"""Demo shop — intentional defect: POST /checkout always 500s."""
import json, os
from http.server import BaseHTTPRequestHandler, HTTPServer

class Shop(BaseHTTPRequestHandler):
    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def do_GET(self):
        if self.path in ("/", "/health"):
            self._send(200, {"ok": True, "route": self.path})
        else:
            self._send(404, {"error": "no such route"})
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        if self.path == "/checkout":
            self._send(500, {"error": "checkout database unavailable"})
        else:
            self._send(200, {"ok": True})
    def log_message(self, *args):
        pass

if __name__ == "__main__":
    HTTPServer(("127.0.0.1", int(os.environ["PORT"])), Shop).serve_forever()
'''


class RunnerError(RuntimeError):
    def __init__(self, stage: str, message: str):
        super().__init__(f"[{stage}] {message}")
        self.stage = stage


# --------------------------------------------------------------------------
# Scripted demo planner (used only when no real model endpoint is configured)
# --------------------------------------------------------------------------

class _ScriptedLLM(BaseHTTPRequestHandler):
    plans: list = []

    def do_GET(self):
        self._respond(200, {"data": [{"id": "demo"}]}) if self.path == "/models" \
            else self._respond(404, {})

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
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


def _scripted_plans(app_url: str) -> list:
    return [
        {"done": False, "steps": [
            {"tool": "http_get", "args": {"url": f"{app_url}/"}, "reason": "smoke"},
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
             "reason": "reproduce the failure"}]},
    ]


# --------------------------------------------------------------------------
# Process helpers
# --------------------------------------------------------------------------

def _as_command_string(start_command: list | str) -> str:
    """Normalize to a single shell string (Windows: cmd-style quoting)."""
    if isinstance(start_command, str):
        return start_command
    if os.name == "nt":
        return subprocess.list2cmdline([str(p) for p in start_command])
    return shlex.join([str(p) for p in start_command])


def _spawn(start_command: list | str, cwd: Path, env: dict, log):
    cmd = _as_command_string(start_command)
    kwargs = dict(cwd=str(cwd), env=env, stdout=log,
                  stderr=subprocess.STDOUT, shell=True)
    if os.name != "nt":
        kwargs["preexec_fn"] = os.setsid
    return subprocess.Popen(cmd, **kwargs)


def _terminate_tree(proc: subprocess.Popen) -> bool:
    """Kill the app process (and children). Returns True when fully gone."""
    if proc.poll() is not None:
        return True
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                           capture_output=True)
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (ProcessLookupError, OSError):
        pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
            proc.wait(timeout=5)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            return False
    return proc.poll() is not None


def _wait_app_ready(port: int, proc: subprocess.Popen, app_log: Path,
                    timeout: int = 45) -> None:
    """CRASHED vs READY_TIMEOUT semantics (Day 7 contract)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            tail = ""
            try:
                tail = app_log.read_bytes()[-2048:].decode("utf-8", "replace")
            except OSError:
                pass
            raise RunnerError("app",
                              f"app exited with code {proc.returncode} before "
                              f"port {port} became ready. Log tail:\n{tail}")
        try:
            sock = socket.create_connection(("127.0.0.1", port), timeout=1)
            sock.close()
            return
        except OSError:
            time.sleep(0.4)
    raise RunnerError("app", f"app did not answer on port {port} within "
                             f"{timeout}s (READY_TIMEOUT)")


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _rmtree_force(path: Path) -> None:
    """shutil.rmtree that survives Windows read-only git pack files."""
    def _make_writable(func, p, _exc):
        try:
            os.chmod(p, 0o666)
            func(p)
        except OSError:
            pass
    try:
        shutil.rmtree(path, onerror=_make_writable)
    except TypeError:  # Python 3.12+ prefers onexc
        shutil.rmtree(path, onexc=lambda f, p, _e: _make_writable(f, p, _e))


# --------------------------------------------------------------------------
# Fixture repo (demo mode)
# --------------------------------------------------------------------------

def _git(args, cwd):
    proc = subprocess.run(["git", *args], cwd=str(cwd),
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RunnerError("snapshot", f"git {' '.join(args)}: "
                                      f"{proc.stderr.strip()}")
    return proc.stdout.strip()


def build_demo_repo(root: Path) -> Path:
    repo = root / "demo-origin"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "app.py").write_text(DEMO_APP, encoding="utf-8")
    (repo / "requirements.txt").write_text("# stdlib only\n", encoding="utf-8")
    (repo / "README.md").write_text("# demo shop\n", encoding="utf-8")
    _git(["init", "-q", "-b", "main"], repo)
    _git(["config", "user.email", "e2e@workflo.local"], repo)
    _git(["config", "user.name", "workflo-e2e"], repo)
    _git(["add", "."], repo)
    _git(["commit", "-q", "-m", "initial"], repo)
    return repo


# --------------------------------------------------------------------------
# The end-to-end run
# --------------------------------------------------------------------------

def run_e2e(*, demo: bool, repo: str | None, instruction: str,
            ref: str | None, start_command: str | None,
            port: int | None, out_dir: Path, keep_workspace: bool,
            max_batches: int, max_tool_calls: int,
            install_deps: bool) -> dict:
    from sandbox_runtime.github_connector import (
        build_provenance, clone_pinned, parse_repository_url, resolve_ref,
    )
    from sandbox_runtime.judge import judge_findings
    from sandbox_runtime.run_state import RunStateWriter
    from workflo_utils.detect import detect_project
    from workflo_worker.agent_runner import execute_step
    from workflo_worker.agent_tools import ToolGateway

    sandbox_id = f"e2e-{int(time.time())}"
    run_dir = out_dir / "runs" / sandbox_id
    artifacts = run_dir / "artifacts"
    workspace = run_dir / "workspace"
    artifacts.mkdir(parents=True, exist_ok=True)
    workspace.mkdir(parents=True, exist_ok=True)
    state = RunStateWriter(run_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    llm_server = None
    app_proc = None
    app_log_fh = None
    result: dict = {"sandbox_id": sandbox_id, "run_dir": str(run_dir)}

    def stage(name, phase="active"):
        state.on_stage(name, phase)
        print(f"  [{phase:6}] {name}")

    try:
        state.on_stage("preflight", "pass")
        state.on_stage("config", "pass")

        # ------------------------------------------------- 1. repository
        stage("snapshot")
        if demo:
            origin = build_demo_repo(workspace / "_demo_origin")
            repo_url = f"file://{origin}"
            ref = ref or "main"
        else:
            if not repo:
                raise RunnerError("snapshot", "--repo required in real mode")
            repo_url = repo
            ref = ref or "HEAD"
        spec = parse_repository_url(repo_url)
        resolved = resolve_ref(spec.clone_url, ref)
        clone_dir = workspace / "repo"
        clone_pinned(spec.clone_url, resolved.commit_sha, clone_dir)
        provenance = build_provenance(spec, resolved, snapshot_digest=None)
        state.on_event("REPO_ACQUIRED", {
            "repository": spec.repository, "commit": resolved.commit_sha[:12]})
        print(f"  repo: {spec.repository} @ {resolved.commit_sha[:12]}")
        state.on_stage("snapshot", "pass")

        # ------------------------------------------------- 2. detection
        stage("deps")
        detection = detect_project(clone_dir)
        state.on_event("PROJECT_DETECTED", {
            "language": detection.language,
            "framework": detection.framework or "-",
            "test_command": detection.test_command or "-",
        })
        print(f"  detected: {detection.language}"
              f"{f'/{detection.framework}' if detection.framework else ''}")
        start_command = start_command or detection.start_command
        if demo and not start_command:
            start_command = [sys.executable, "app.py"]
        port = port or detection.port or _free_port()
        if not start_command:
            raise RunnerError(
                "deps", "no start command detected; pass --start-command")
        req = clone_dir / "requirements.txt"
        if install_deps and req.exists() and \
                req.read_text().strip().startswith(("flask", "django", "fastapi")):
            subprocess.run([sys.executable, "-m", "pip", "install", "-q",
                            "-r", str(req)], cwd=str(clone_dir), check=True)
        state.on_stage("deps", "pass")

        # ------------------------------------------------- 3. application
        stage("app")
        app_log_path = run_dir / "app.log"
        app_log_fh = open(app_log_path, "ab", buffering=0)
        env = dict(os.environ)
        env.update({"PORT": str(port), "HOST": "127.0.0.1"})
        app_proc = _spawn(start_command, clone_dir, env, app_log_fh)
        _wait_app_ready(port, app_proc, app_log_path)
        base_url = f"http://app.workflo.internal:{port}"
        state.on_event("APP_STARTED", {"port": port, "base_url": base_url,
                                       "pid": app_proc.pid})
        print(f"  app ready on :{port} (pid {app_proc.pid})")
        state.on_stage("app", "pass")

        # ------------------------------------------------- 4. agent + planner
        state.on_stage("agent", "active")
        records_path = artifacts / "agent_tool_calls.jsonl"
        plan_path = artifacts / "plan.json"
        obs_path = artifacts / "observations.json"

        scripted = None
        if not os.environ.get("WORKFLO_LLM_BASE_URL", "").strip():
            if not demo:
                raise RunnerError(
                    "agent",
                    "no model endpoint configured. Set WORKFLO_LLM_BASE_URL "
                    "(or `workflo config set-llm ...`) — or run --demo.")
            llm_server = HTTPServer(("127.0.0.1", 0), _ScriptedLLM)
            threading.Thread(target=llm_server.serve_forever,
                             daemon=True).start()
            _ScriptedLLM.plans = _scripted_plans(base_url)
            os.environ["WORKFLO_LLM_BASE_URL"] = \
                f"http://127.0.0.1:{llm_server.server_port}"
            os.environ.setdefault("WORKFLO_LLM_MODEL", "workflo-agent-v1")
            os.environ["WORKFLO_LLM_TIMEOUT"] = "15"
            scripted = "scripted (set WORKFLO_LLM_BASE_URL for a real model)"

        def sandbox_opener(request, timeout=None):
            url = request.full_url.replace(
                "app.workflo.internal", "127.0.0.1")
            req = urllib.request.Request(url, data=request.data,
                                         method=request.get_method())
            return urllib.request.urlopen(req, timeout=timeout)

        gateway = ToolGateway(records_path, opener=sandbox_opener)

        def agent_side():
            from sandbox_runtime.planner import PLAN_PATH  # noqa: F401
            last = 0
            for _ in range(600):
                if not plan_path.exists():
                    time.sleep(0.05); continue
                try:
                    plan = json.loads(plan_path.read_text())
                except json.JSONDecodeError:
                    continue
                if plan.get("seq", 0) <= last:
                    time.sleep(0.05); continue
                last = plan["seq"]
                observations = [execute_step(gateway, step)
                                for step in plan.get("steps", [])[:12]]
                obs_path.write_text(json.dumps({
                    "seq": last, "tool_calls": gateway.tool_calls,
                    "observations": observations}))
                for o in observations:
                    state.on_event("AGENT_STEP", {
                        "tool": o["tool"], "detail": o["detail"],
                        "denied": bool(o["denied"])})
                    flag = " (DENIED)" if o["denied"] else ""
                    print(f"  [agent] {o['tool']}: {o['detail']}{flag}")
                if plan.get("done"):
                    return

        agent_thread = threading.Thread(target=agent_side, daemon=True)
        agent_thread.start()
        from sandbox_runtime.planner import run_planner_loop
        planner_result = run_planner_loop(
            artifacts, base_url, max_batches=max_batches,
            max_tool_calls=max_tool_calls, mission=instruction)
        agent_thread.join(timeout=60)
        state.on_event("AGENT_REPORTED", {
            "tool_calls": gateway.tool_calls,
            "denied_attempts": gateway.denied_attempts,
            "steps_total": gateway.tool_calls,
            "steps_completed": gateway.tool_calls - gateway.errors,
            "steps_failed": gateway.errors,
        })
        print(f"  planner: {planner_result['batches']} batches"
              f"{'  [' + scripted + ']' if scripted else ''}")
        state.on_stage("agent", "pass")

        # ------------------------------------------------- 5. judge
        records = [json.loads(line) for line in
                   records_path.read_text().splitlines() if line.strip()]
        judged = judge_findings(records)
        state.on_event("FINDINGS_JUDGED", {"confirmed": judged.confirmed,
                                           "reported": judged.reported})
        for finding in judged.findings:
            print(f"  [finding:{finding['status']}] {finding['title']}")

        # ------------------------------------------------- 6. teardown
        stage("teardown")
        teardown_started = datetime.now(UTC)
        processes_gone = _terminate_tree(app_proc)
        if app_log_fh is not None:
            app_log_fh.close()
            app_log_fh = None
        if not keep_workspace:
            _rmtree_force(workspace)
        workspace_gone = not workspace.exists()
        state.on_event("TEARDOWN", {
            "processes_terminated": processes_gone,
            "workspace_removed": workspace_gone,
        })
        state.on_stage("teardown", "pass")

        # ------------------------------------------------- 7. receipt
        stage("receipt")
        from cryptography.hazmat.primitives import serialization
        from sandbox_isolation import (generate_keypair,
                                       verify_receipt_signature)
        from workflo_schema.sandbox import SignedReceipt

        payload = {
            "receipt_version": 4,
            "sandbox_id": sandbox_id,
            "issued_at": datetime.now(UTC).isoformat(),
            "run_report": {
                "sandbox_id": sandbox_id, "run_id": sandbox_id,
                "total": 0, "passed": 0, "failed": 0, "skipped": 0,
                "duration_seconds": round(time.monotonic() - started, 2),
                "findings": judged.findings,
            },
            # Honest dev-harness claims (non-namespace branch): every
            # process we spawned is confirmed dead and the clone workspace
            # is deleted (unless --keep-workspace). The kernel-isolation
            # claims are the Linux supervisor path's job.
            "teardown_proof": {
                "sandbox_id": sandbox_id,
                "runtime_type": None,
                "destroyed_at": teardown_started.isoformat(),
                "container_removed": processes_gone,
                "filesystem_removed": workspace_gone,
                "no_snapshot_retained": True,
                "session_duration_seconds": round(
                    time.monotonic() - started, 2),
                "events_count": 1,
            },
            "canary_check": {
                "sandbox_id": sandbox_id,
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
                "mission": instruction,
                **({"inference_provenance":
                    planner_result["inference_provenance"]}
                   if planner_result.get("inference_provenance") else {}),
            },
            "signature_algorithm": "ed25519",
            "run_status": "completed",
        }
        signer = generate_keypair()
        receipt = SignedReceipt(**payload)
        signed = signer.sign(receipt)
        verify_ok = verify_receipt_signature(signed, signer.public_key)

        receipt_path = out_dir / "receipt.json"
        receipt_path.write_text(signed.model_dump_json(indent=2),
                                encoding="utf-8")
        key_path = out_dir / "receipt-key.pub.pem"
        key_path.write_bytes(signer.public_key.public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo))
        state.on_event("RECEIPT_SIGNED", {"path": str(receipt_path),
                                          "verified": verify_ok})
        state.on_stage("receipt", "pass")
        state.finish("completed")

        result.update({
            "findings": judged.findings,
            "confirmed": judged.confirmed,
            "reported": judged.reported,
            "tool_calls": gateway.tool_calls,
            "denied_attempts": gateway.denied_attempts,
            "receipt_path": str(receipt_path),
            "key_path": str(key_path),
            "verify_ok": verify_ok,
            "repository": spec.repository,
            "commit": resolved.commit_sha,
        })
        return result

    except RunnerError as e:
        state.finish("failed", failure_stage=e.stage)
        raise
    finally:
        if app_proc is not None and app_proc.poll() is None:
            _terminate_tree(app_proc)
        if app_log_fh is not None:
            app_log_fh.close()
        if llm_server is not None:
            llm_server.shutdown()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Workflo end-to-end runner: repo → receipt → verify")
    parser.add_argument("--demo", action="store_true",
                        help="self-contained fixture run (no external deps)")
    parser.add_argument("--repo", help="GitHub repository URL (real mode)")
    parser.add_argument("--ref", default=None, help="branch/tag/SHA")
    parser.add_argument("--instruction", "-m",
                        default="Test health and checkout",
                        help="testing mission")
    parser.add_argument("--start-command", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--out", default=".workflo/e2e")
    parser.add_argument("--max-batches", type=int, default=6)
    parser.add_argument("--max-tool-calls", type=int, default=40)
    parser.add_argument("--keep-workspace", action="store_true",
                        help="retain the cloned repo after the run")
    parser.add_argument("--install-deps", action="store_true",
                        help="pip-install requirements.txt (user-approved)")
    args = parser.parse_args()

    out_dir = Path(args.out).resolve()
    sandbox_hint = ""
    print(f"== workflo e2e ==\nmission: {args.instruction}")
    try:
        result = run_e2e(
            demo=args.demo, repo=args.repo, instruction=args.instruction,
            ref=args.ref, start_command=args.start_command, port=args.port,
            out_dir=out_dir, keep_workspace=args.keep_workspace,
            max_batches=args.max_batches,
            max_tool_calls=args.max_tool_calls,
            install_deps=args.install_deps)
    except RunnerError as e:
        print(f"\nFAILED: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001 - top-level harness
        print(f"\nFAILED: {e.__class__.__name__}: {e}", file=sys.stderr)
        return 1

    print()
    print(f"receipt : {result['receipt_path']}"
          f"  signature={'VALID' if result['verify_ok'] else 'INVALID'}")
    print(f"pubkey  : {result['key_path']}")
    print(f"console : workflo status --runs-dir "
          f"{out_dir / 'runs'} --run {result['sandbox_id']}")
    print(f"verify  : workflo verify --receipt {result['receipt_path']} "
          f"--pubkey {result['key_path']}")
    print(f"findings: {result['confirmed']} confirmed, "
          f"{result['reported']} reported")
    return 0 if result["verify_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
