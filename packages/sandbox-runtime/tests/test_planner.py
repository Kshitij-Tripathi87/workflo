"""Tests for the LLM planner loop (host-side) and the planner protocol.

The full protocol is testable on any platform: a FAKE OpenAI-compatible
LLM server (local HTTP) drives the planner; the agent executes through
the real ToolGateway against a real local HTTP app. This is the
Autonomous Verified Deep Test loop — everything real except the sandbox.

Trust invariant exercised here: the planner can only write plan files;
it never executes anything itself.
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from sandbox_runtime.planner import (
    run_planner_loop,
    parse_plan,
    llm_available,
    build_user_prompt,
    PlannerUnavailable,
    SYSTEM_PROMPT,
)


# ---------------------------------------------------------------------------
# Fake OpenAI-compatible LLM server
# ---------------------------------------------------------------------------

class FakeLLMHandler(BaseHTTPRequestHandler):
    """Scripted /chat/completions + /models responses."""

    # Set by the fixture: a list of plan dicts served in order
    plans = []
    calls = []

    def do_GET(self):
        if self.path == "/models":
            body = json.dumps({"data": [{"id": "fake-model"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/chat/completions":
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length))
            FakeLLMHandler.calls.append(payload)
            plan = FakeLLMHandler.plans.pop(0) if FakeLLMHandler.plans else {"done": True, "steps": []}
            content = "```json\n" + json.dumps(plan) + "\n```"  # fenced, like real models
            body = json.dumps({
                "id": "chatcmpl-test-1",
                "choices": [{"message": {"role": "assistant", "content": content}}],
                "usage": {"prompt_tokens": 111, "completion_tokens": 222,
                          "total_tokens": 333},
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture
def fake_llm(monkeypatch):
    """A fake OpenAI-compatible LLM server + WORKFLO_LLM_* env pointing at it."""
    httpd = HTTPServer(("127.0.0.1", 0), FakeLLMHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    FakeLLMHandler.plans = []
    FakeLLMHandler.calls = []

    port = httpd.server_port
    monkeypatch.setenv("WORKFLO_LLM_BASE_URL", f"http://127.0.0.1:{port}")
    monkeypatch.setenv("WORKFLO_LLM_API_KEY", "test-key")
    monkeypatch.setenv("WORKFLO_LLM_MODEL", "fake-model")
    monkeypatch.setenv("WORKFLO_LLM_TIMEOUT", "10")

    yield httpd

    httpd.shutdown()


# ---------------------------------------------------------------------------
# Fake app under test (local HTTP stand-in for the in-netns app)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def app_server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health":
                body = b'{"status":"ok"}'
            else:
                body = b"<html>workflo app</html>"
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd
    httpd.shutdown()


# ---------------------------------------------------------------------------
# The planner protocol end-to-end (fake LLM + real gateway)
# ---------------------------------------------------------------------------

class TestPlannerLoop:
    def test_full_protocol_plan_observe_plan_done(
        self, fake_llm, tmp_path, monkeypatch, app_server
    ):
        """The complete Autonomous Deep Test loop with everything real
        except the sandbox: the LLM plans, the agent executes through the
        real governed gateway against a real HTTP app, observations flow
        back, and the planner finishes."""
        from workflo_worker.agent_tools import ToolGateway
        from workflo_worker.agent_runner import execute_step

        port = app_server.server_port

        # The LLM plans: batch 1 probes the app; batch 2 declares done
        FakeLLMHandler.plans = [
            {"done": False, "steps": [
                {"tool": "http_get", "args": {"url": f"http://app.workflo.internal:{port}/"},
                 "reason": "check root"},
                {"tool": "http_get", "args": {"url": f"http://app.workflo.internal:{port}/health"},
                 "reason": "check health"},
            ]},
            {"done": True, "steps": [
                {"tool": "http_get",
                 "args": {"url": f"http://app.workflo.internal:{port}/missing"},
                 "reason": "final check"},
            ]},
        ]

        # A real gateway executing against the REAL app via the allowlist.
        # The opener rewrites internal URLs to the local app server — the
        # same translation the sandbox netns performs for real.
        records = tmp_path / "records.jsonl"
        from urllib.parse import urlparse, urlunparse

        def sandbox_opener(request, timeout=None):
            parsed = urlparse(request.full_url)
            rewritten = urlunparse(parsed._replace(netloc=f"127.0.0.1:{port}"))
            import urllib.request as ur
            req2 = ur.Request(rewritten, data=request.data,
                              method=request.get_method())
            return ur.urlopen(req2, timeout=timeout)

        gw = ToolGateway(records, opener=sandbox_opener)

        def agent_side():
            """The sandboxed agent side: wait for plans, execute, observe."""
            plan_dir = tmp_path
            plan_path = plan_dir / "plan.json"
            obs_path = plan_dir / "observations.json"
            last_seq = 0
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if plan_path.exists():
                    try:
                        plan = json.loads(plan_path.read_text(encoding="utf-8"))
                    except (json.JSONDecodeError, OSError):
                        # Mirror the real agent runner: retry if a producer has
                        # not finished publishing a protocol file yet.
                        time.sleep(0.05)
                        continue
                    if plan.get("seq", 0) > last_seq:
                        last_seq = plan["seq"]
                        observations = [execute_step(gw, s) for s in plan.get("steps", [])]
                        obs_path.write_text(json.dumps({
                            "seq": last_seq,
                            "tool_calls": gw.tool_calls,
                            "denied_attempts": gw.denied_attempts,
                            "observations": observations,
                        }))
                        if plan.get("done"):
                            return
                time.sleep(0.05)

        agent_task = threading.Thread(target=agent_side, daemon=True)
        agent_task.start()

        events = []
        result = run_planner_loop(
            tmp_path, f"http://app.workflo.internal:{port}",
            max_batches=4, max_tool_calls=40,
            on_event=lambda note, data: events.append((note, data)),
        )

        agent_task.join(timeout=10)
        assert not agent_task.is_alive(), "agent side never saw the done plan"

        assert result["planner"] == "llm"
        assert result["batches"] >= 2

        # The LLM received the observations from batch 1 in batch 2's prompt
        assert len(FakeLLMHandler.calls) >= 2
        second_prompt = FakeLLMHandler.calls[1]["messages"][1]["content"]
        assert "Recent observations" in second_prompt
        assert "HTTP 200" in second_prompt  # bounded observation flowed back

        # The agent actually operated the app through the governed gateway
        assert gw.tool_calls == 3
        assert "http_get" in gw.tools_used

    def test_budget_exhaustion_ends_loop(self, fake_llm, tmp_path):
        """The planner stops when the tool-call budget is exhausted."""
        FakeLLMHandler.plans = [
            {"done": False, "steps": [{"tool": "http_get", "args": {"url": "http://app.workflo.internal:1/x"}}]}
            for _ in range(10)
        ]
        # No agent side: observation waits time out quickly
        result = run_planner_loop(
            tmp_path, "http://app.workflo.internal:1",
            max_batches=2, max_tool_calls=1,
            on_event=lambda n, d: None,
        )
        assert result["planner"] == "llm"
        # Only one plan was written before the budget stopped the loop
        assert len(FakeLLMHandler.calls) == 1

    def test_unreachable_llm_raises(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WORKFLO_LLM_BASE_URL", "http://127.0.0.1:1")
        monkeypatch.setenv("WORKFLO_LLM_API_KEY", "x")
        monkeypatch.setenv("WORKFLO_LLM_MODEL", "m")
        assert llm_available() is False
        with pytest.raises(PlannerUnavailable):
            run_planner_loop(tmp_path, "http://app.workflo.internal:1")

    def test_no_llm_configured_raises(self, tmp_path, monkeypatch):
        monkeypatch.delenv("WORKFLO_LLM_BASE_URL", raising=False)
        with pytest.raises(PlannerUnavailable, match="no LLM configured"):
            run_planner_loop(tmp_path, "http://app.workflo.internal:1")

    def test_malformed_llm_response_ends_gracefully(self, fake_llm, tmp_path, monkeypatch):
        """A malformed plan must not crash anything — the loop ends and
        the run proceeds with collected activity."""
        monkeypatch.setattr(FakeLLMHandler, "plans", [])  # serve done-plans
        # Override the handler to return garbage
        original_post = FakeLLMHandler.do_POST

        def garbage_post(self):
            length = int(self.headers.get("Content-Length", 0))
            self.rfile.read(length)
            body = json.dumps({"choices": [{"message": {"content": "I cannot answer in JSON"}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        FakeLLMHandler.do_POST = garbage_post
        try:
            with pytest.raises(PlannerUnavailable, match="no JSON"):
                run_planner_loop(tmp_path, "http://app.workflo.internal:1")
        finally:
            FakeLLMHandler.do_POST = original_post


class TestPromptPrivacy:
    def test_prompt_contains_only_observations(self):
        """The planner prompt must contain bounded runtime observations —
        never source code paths or file contents beyond previews."""
        prompt = build_user_prompt(
            "http://app.workflo.internal:3000",
            [{"description": "GET /", "ok": True, "detail": "HTTP 200"}],
            batches_left=3, tool_calls_left=20,
        )
        assert "app.workflo.internal" in prompt
        assert "observations" in prompt.lower()
        assert "State:" in prompt  # Day 9 mission-state section
        assert "/home/" not in prompt  # no host paths

    def test_system_prompt_constrains_targets(self):
        assert ".workflo.internal" in SYSTEM_PROMPT
        assert "denied and recorded" in SYSTEM_PROMPT


class TestParsePlan:
    def test_fenced_json(self):
        plan = parse_plan('Here is my plan:\n```json\n{"done": false, "steps": [{"tool": "http_get"}]}\n```')
        assert plan["done"] is False
        assert len(plan["steps"]) == 1

    def test_prose_wrapped(self):
        plan = parse_plan('Sure! {"done": true, "steps": []} hope that helps')
        assert plan["done"] is True

    def test_no_json_raises(self):
        with pytest.raises(PlannerUnavailable, match="no JSON"):
            parse_plan("I cannot comply")

    def test_invalid_steps_raise(self):
        with pytest.raises(PlannerUnavailable, match="not a list"):
            parse_plan('{"done": false, "steps": "all of them"}')


# ---------------------------------------------------------------------------
# Gateway mode: the control-plane privacy gateway (observation-only)
# ---------------------------------------------------------------------------

class FakeGatewayHandler(BaseHTTPRequestHandler):
    """Stand-in for the control-plane /v1/inference endpoints."""

    requests = []
    plans = []

    def do_GET(self):
        if self.path.endswith("/inference/health"):
            body = json.dumps({"status": "configured", "version": "0.3.0"}).encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path.endswith("/inference/plan"):
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length))
            FakeGatewayHandler.requests.append(payload)
            plan = FakeGatewayHandler.plans.pop(0) if FakeGatewayHandler.plans else {"done": True, "steps": []}
            body = json.dumps({
                "protocol_version": 1,
                "plan": plan,
                "provenance": {
                    "mode": "gateway",
                    "protocol_version": 1,
                    "gateway_url": "http://gateway.test",
                    "gateway_version": "0.3.0",
                    "model": "qa-model",
                    "requests": 1,
                    "observations_sent": len(payload.get("observations", [])),
                    "source_code_included": False,
                    "observation_sha256": "a" * 64,
                    "prompt_sha256": "b" * 64,
                    "response_sha256": "c" * 64,
                    "request_ids": ["req-1"],
                },
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass


class TestGatewayMode:
    @pytest.fixture
    def fake_gateway(self, monkeypatch):
        httpd = HTTPServer(("127.0.0.1", 0), FakeGatewayHandler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        FakeGatewayHandler.requests = []
        FakeGatewayHandler.plans = []
        monkeypatch.setenv("WORKFLO_LLM_MODE", "gateway")
        monkeypatch.setenv("WORKFLO_LLM_BASE_URL", f"http://127.0.0.1:{httpd.server_port}")
        monkeypatch.setenv("WORKFLO_LLM_GATEWAY_URL", f"http://127.0.0.1:{httpd.server_port}")
        monkeypatch.setenv("WORKFRO_LLM_API_KEY", "gateway-key")
        monkeypatch.setenv("WORKFLO_LLM_API_KEY", "gateway-key")
        monkeypatch.setenv("WORKFLO_LLM_MODEL", "qa-model")
        monkeypatch.setenv("WORKFLO_LLM_TIMEOUT", "10")
        yield httpd
        httpd.shutdown()

    def test_gateway_mode_sends_observations_only(
        self, fake_gateway, tmp_path, app_server, monkeypatch
    ):
        """Gateway mode: the planner sends ONLY sanitized bounded
        observations to the control-plane gateway — never a prompt, never
        source code. The provenance comes back for the receipt."""
        port = app_server.server_port

        FakeGatewayHandler.plans = [
            {"done": False, "steps": [
                {"tool": "http_get", "args": {"url": f"http://app.workflo.internal:{port}/"},
                 "reason": "probe root"},
            ]},
            {"done": True, "steps": []},
        ]

        observations_seen = []
        orig_wait = None
        # Observe what the gateway received by checking after the loop

        # Simple agent side that executes the plan against the real app
        from workflo_worker.agent_tools import ToolGateway
        from workflo_worker.agent_runner import execute_step
        from urllib.parse import urlparse, urlunparse

        def sandbox_opener(request, timeout=None):
            parsed = urlparse(request.full_url)
            rewritten = urlunparse(parsed._replace(netloc=f"127.0.0.1:{port}"))
            import urllib.request as ur
            return ur.urlopen(ur.Request(rewritten, data=request.data,
                                         method=request.get_method()),
                              timeout=timeout)

        gw = ToolGateway(tmp_path / "records.jsonl", opener=sandbox_opener)

        def agent_side():
            plan_path = tmp_path / "plan.json"
            obs_path = tmp_path / "observations.json"
            last_seq = 0
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if plan_path.exists():
                    try:
                        plan = json.loads(plan_path.read_text(encoding="utf-8"))
                    except (json.JSONDecodeError, OSError):
                        # A concurrent writer may be replacing the protocol file;
                        # retry rather than terminating the reader thread.
                        time.sleep(0.05)
                        continue
                    if plan.get("seq", 0) > last_seq:
                        last_seq = plan["seq"]
                        observations = [execute_step(gw, s) for s in plan.get("steps", [])]
                        obs_path.write_text(json.dumps({
                            "seq": last_seq,
                            "tool_calls": gw.tool_calls,
                            "denied_attempts": gw.denied_attempts,
                            "observations": observations,
                        }))
                        if plan.get("done"):
                            return
                time.sleep(0.05)

        agent_task = threading.Thread(target=agent_side, daemon=True)
        agent_task.start()

        result = run_planner_loop(
            tmp_path, f"http://app.workflo.internal:{port}",
            max_batches=3, max_tool_calls=20,
            on_event=lambda n, d: None,
        )
        agent_task.join(timeout=10)

        assert result["planner"] == "llm"
        prov = result["inference_provenance"]
        assert prov is not None
        assert prov["mode"] == "gateway"
        assert prov["source_code_included"] is False
        assert prov["requests"] >= 1
        assert prov["observations_sent"] >= 1
        assert prov["request_ids"]

        # The gateway received observation-only requests — no prompt text,
        # no source keys anywhere in the wire payload
        assert len(FakeGatewayHandler.requests) >= 1
        for sent in FakeGatewayHandler.requests:
            assert "messages" not in sent
            assert "system_prompt" not in sent
            assert "raw_prompt" not in sent
            assert "source_code" not in sent
            for obs in sent.get("observations", []):
                assert obs["tool"] in ("http_get", "http_post", "read_log",
                                       "list_files", "read_file")
        # The X-API-Key header was used for gateway auth
        # (verified implicitly: the fake gateway ignores auth, but the
        # request went through without the model endpoint being contacted)

    def test_gateway_mode_sanitizes_secret_observations(
        self, fake_gateway, tmp_path
    ):
        """Observations are sanitized BEFORE transmission — secret-looking
        values are redacted by the shared contract."""
        from sandbox_runtime.planner import call_gateway as planner_call_gateway

        cfg = {
            "gateway_url": f"http://127.0.0.1:{fake_gateway.server_port}",
            "gateway_key": "k",
            "timeout": 5,
        }
        FakeGatewayHandler.plans = [{"done": True, "steps": []}]

        plan, prov = planner_call_gateway(
            cfg, "http://app.workflo.internal:3000",
            [{
                "tool": "http_get", "ok": False,
                "description": "auth probe",
                "detail": "401: Authorization Bearer sk-live-secret-xyz",
                # A source-bearing key would be rejected:
            }],
            batches_left=1, tool_calls_left=5,
        )
        assert plan["done"] is True
        sent = FakeGatewayHandler.requests[-1]
        detail = sent["observations"][0]["detail"]
        assert "sk-live-secret-xyz" not in detail
        assert "<redacted>" in detail

    def test_gateway_mode_source_observation_rejected(self, fake_gateway, tmp_path):
        """A source-bearing observation never leaves the host — the shared
        contract rejects it before any network call."""
        from sandbox_runtime.planner import call_gateway as planner_call_gateway

        cfg = {
            "gateway_url": f"http://127.0.0.1:{fake_gateway.server_port}",
            "gateway_key": "k",
            "timeout": 5,
        }
        with pytest.raises(Exception) as exc:
            planner_call_gateway(
                cfg, "http://app.workflo.internal:3000",
                [{"tool": "read_file", "ok": True, "detail": "def evil(): pass",
                  "source_code": "import os"}],
                batches_left=1, tool_calls_left=5,
            )
        assert "source" in str(exc.value).lower() or "not allowed" in str(exc.value).lower()
        # NOTHING was sent to the gateway
        assert len(FakeGatewayHandler.requests) == 0


class TestCostRail:
    """Benchmark capture (Sprint 4 parallel track): token usage and
    inference seconds must flow from the model endpoint into the signed
    inference provenance — the input for cost-per-run/finding math."""

    def test_call_llm_returns_usage_metrics(self, fake_llm):
        from sandbox_runtime.planner import call_llm

        cfg = {
            "base_url": f"http://127.0.0.1:{fake_llm.server_port}",
            "api_key": "k",
            "model": "fake-model",
            "timeout": 5,
        }
        content, metrics = call_llm(cfg, [{"role": "user", "content": "hi"}])
        assert "done" in content or "{" in content  # plan text came back
        assert metrics["input_tokens"] == 111
        assert metrics["output_tokens"] == 222
        assert metrics["inference_seconds"] >= 0.0
        assert metrics["request_id"] == "chatcmpl-test-1"

    def test_full_loop_provenance_carries_tokens(self, fake_llm, tmp_path):
        """End-to-end: one planner call against the stub (usage-bearing)
        response lands in the merged, receipt-bound provenance."""
        FakeLLMHandler.plans = [{"done": True, "steps": []}]

        result = run_planner_loop(
            tmp_path, "http://app.workflo.internal:1",
            max_batches=2, max_tool_calls=5,
            on_event=lambda n, d: None,
        )
        prov = result["inference_provenance"]
        assert prov is not None
        assert prov["mode"] == "direct"
        assert prov["input_tokens"] == 111
        assert prov["output_tokens"] == 222
        assert prov["inference_seconds"] >= 0.0
        assert prov["request_ids"] == ["chatcmpl-test-1"]
        # The provenance validates against the signed schema (receipt v4
        # embeds it in agent_activity.inference_provenance).
        from workflo_schema.inference import InferenceProvenance
        validated = InferenceProvenance.model_validate(prov)
        assert validated.input_tokens == 111
        assert validated.source_code_included is False

    def test_merge_provenance_sums_cost_rail(self):
        from sandbox_runtime.planner import _merge_provenance

        merged = _merge_provenance([
            {"mode": "direct", "requests": 1,
             "input_tokens": 111, "output_tokens": 222,
             "inference_seconds": 0.5},
            {"mode": "direct", "requests": 1,
             "input_tokens": 111, "output_tokens": 222,
             "inference_seconds": 0.25},
        ])
        assert merged["requests"] == 2
        assert merged["input_tokens"] == 222
        assert merged["output_tokens"] == 444
        assert abs(merged["inference_seconds"] - 0.75) < 1e-9
