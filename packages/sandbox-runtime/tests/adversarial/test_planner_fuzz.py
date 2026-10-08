"""Planner-output fuzzing + adversarial loop behavior (spec §17, MO-1..MO-5).

Model responses are untrusted input. Every response must either parse and
validate, or be a classified rejection — never an unhandled exception,
never an undefined state.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from sandbox_runtime.planner import (
    DEFAULT_MAX_BATCHES,
    DEFAULT_MAX_TOOL_CALLS,
    parse_plan,
    run_planner_loop,
    PlannerUnavailable,
)


# ---------------------------------------------------------------------------
# Inline fake LLM server
# ---------------------------------------------------------------------------

class FakeLLMHandler(BaseHTTPRequestHandler):
    plans = []
    calls = []

    def do_GET(self):
        if self.path == "/models":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"data": []}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path != "/chat/completions":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length))
        FakeLLMHandler.calls.append(payload)
        plan = (FakeLLMHandler.plans.pop(0) if FakeLLMHandler.plans
                else {"done": True, "steps": []})
        body = json.dumps({
            "choices": [{"message": {"role": "assistant",
                                     "content": json.dumps(plan)}}]
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def fake_llm(monkeypatch):
    httpd = HTTPServer(("127.0.0.1", 0), FakeLLMHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    FakeLLMHandler.plans = []
    FakeLLMHandler.calls = []
    monkeypatch.setenv("WORKFLO_LLM_BASE_URL", f"http://127.0.0.1:{httpd.server_port}")
    monkeypatch.setenv("WORKFLO_LLM_API_KEY", "test-key")
    monkeypatch.setenv("WORKFLO_LLM_MODEL", "fake-model")
    monkeypatch.setenv("WORKFLO_LLM_TIMEOUT", "10")
    yield httpd
    httpd.shutdown()


class TestParsePlanFuzzing:
    """MO-1: malformed model output is a classified rejection."""

    def test_not_json(self):
        with pytest.raises(PlannerUnavailable):
            parse_plan("the answer is 42")

    def test_json_array_not_object(self):
        with pytest.raises(PlannerUnavailable):
            parse_plan('["not", "a", "plan"]')

    def test_json_number_scalar(self):
        with pytest.raises(PlannerUnavailable):
            parse_plan("42")

    def test_zero_byte_input(self):
        with pytest.raises(PlannerUnavailable):
            parse_plan("")

    def test_unicode_garbage(self):
        with pytest.raises(PlannerUnavailable):
            parse_plan("\ufffd\ufffd\ufffd")

    def test_json_with_bern_slide(self):
        """A decorator-adjacent looking JSON with a nul after quotes."""
        with pytest.raises(PlannerUnavailable):
            parse_plan('{"done": true\x00}')

    def test_valid_wrapped_in_markdown(self):
        plan = parse_plan('```json\n{"done": true, "steps": []}\n```')
        assert plan["done"] is True

    def test_steps_not_a_list_rejected(self):
        with pytest.raises(PlannerUnavailable):
            parse_plan('{"done": false, "steps": "not-a-list"}')

    def test_duplicate_keys_tolerated(self):
        p = parse_plan('{"done": false, "done": true, "steps": []}')
        assert p["done"] is True  # json.loads keeps the last value

    def test_oversized_response_bounded(self):
        big_steps = [{"tool": "http_get", "args": {}} for _ in range(2000)]
        plan = parse_plan(json.dumps({"done": False, "steps": big_steps}))
        assert len(plan["steps"]) == 2000


def _observations_response(plan_dir: Path, seq: int, tool_calls_total: int):
    # The real agent reports cumulative totals; the planner's budget reads
    # tool_calls as an absolute counter, so tests must send cumulative
    # values or the budget never exhausts.
    (plan_dir / "observations.json").write_text(json.dumps({
        "seq": seq, "tool_calls": tool_calls_total, "denied_attempts": 0,
        "observations": [{"note": f"batch-{seq}"}],
    }))


def _read_plan(plan_path: Path) -> dict | None:
    """Reads can race a concurrent write (partial file)."""
    try:
        return json.loads(plan_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


class TestPlannerLoopHangAndBudget:
    """MO-4/MO-5: infinite planning loops and budget abuse terminate deterministically."""

    def test_planner_obeys_max_batches(self, fake_llm, tmp_path):
        FakeLLMHandler.plans = [
            {"done": False, "steps": [{"tool": "http_get", "args": {"url": "http://app.workflo.internal:1/"} }]}
            for _ in range(100)
        ]

        def agent_side():
            plan_path = tmp_path / "plan.json"
            seen = 0
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if plan_path.exists():
                    plan = _read_plan(plan_path)
                    if plan and plan.get("seq", 0) > seen:
                        seen = plan["seq"]
                        _observations_response(tmp_path, seen, tool_calls_total=seen)
                        if plan.get("done"):
                            return
                time.sleep(0.02)

        t = threading.Thread(target=agent_side, daemon=True)
        t.start()
        result = run_planner_loop(
            tmp_path, "http://app.workflo.internal:1",
            max_batches=3, max_tool_calls=10,
        )
        t.join(timeout=15)
        assert result["batches"] <= 4  # 3 batches + final done plan

    def test_tool_call_budget_stops_loop(self, fake_llm, tmp_path):
        FakeLLMHandler.plans = [
            {"done": False, "steps": [{"tool": "http_get", "args": {}}]}
            for _ in range(50)
        ]

        def agent_side():
            plan_path = tmp_path / "plan.json"
            seen = 0
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if plan_path.exists():
                    plan = _read_plan(plan_path)
                    if plan and plan.get("seq", 0) > seen:
                        seen = plan["seq"]
                        _observations_response(tmp_path, seen, tool_calls_total=seen)
                        if plan.get("done"):
                            return
                time.sleep(0.02)

        t = threading.Thread(target=agent_side, daemon=True)
        t.start()
        result = run_planner_loop(
            tmp_path, "http://app.workflo.internal:1",
            max_batches=5, max_tool_calls=2,
        )
        t.join(timeout=15)
        # budget of 2 tool calls: 2 batches planned (1 -> 1 call,
        # 2 -> 2 cumulative calls), then calls_left=0 stops the loop
        assert len(FakeLLMHandler.calls) == 2
