"""Benchmark harness tests — against a local stub OpenAI-compatible server.

The stub simulates a real model endpoint: it sleeps briefly per request
(so concurrency actually matters) and returns usage counters, letting us
verify the harness math (rps, p50/p95, unit economics) without a GPU.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


class _StubModelHandler(BaseHTTPRequestHandler):
    latency_s = 0.05

    def do_POST(self):  # noqa: N802 - stdlib API
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        time.sleep(self.latency_s)
        body = json.dumps({
            "id": "chatcmpl-stub",
            "object": "chat.completion",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": '{"done": true, "steps": []}',
                },
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 64, "completion_tokens": 12,
                      "total_tokens": 76},
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # silence
        pass


@pytest.fixture
def stub_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StubModelHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


BENCH_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "bench" / "model-serving" / "bench_inference.py"
)


def _load_bench_module():
    """Load bench_inference.py by path (it lives outside the package tree).

    A missing harness is a FAILURE, not a skip: the file is part of the repo, and
    the model-serving economics depend on it running (see PRODUCT_BOUNDARIES.md).
    """
    import importlib.util
    import sys

    target = BENCH_SCRIPT
    assert target.exists(), (
        f"benchmark harness missing: {target} — restore it or delete this test; "
        "a permanently skipped economics test is not evidence of anything"
    )
    spec = importlib.util.spec_from_file_location("bench_inference", target)
    module = importlib.util.module_from_spec(spec)
    # Register before exec: dataclass field resolution looks the module up
    # in sys.modules (Python 3.14 evaluates deferred annotations at wrap).
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(spec.name, None)
        raise
    return module


def test_direct_mode_against_stub(stub_server, tmp_path):
    bench = _load_bench_module()
    out_json = tmp_path / "bench.json"
    out_md = tmp_path / "bench.md"

    argv = [
        "bench_inference.py",
        "--mode", "direct",
        "--base-url", stub_server,
        "--model", "stub",
        "--gpu-hourly-usd", "1.00",  # explicit test assumption; not a measured GPU price
        "--levels", "1,4",
        "--requests-per-level", "8",
        "--timeout", "10",
        "--out", str(out_json),
        "--md", str(out_md),
    ]
    import sys
    old = sys.argv
    sys.argv = argv
    try:
        rc = bench.main()
    finally:
        sys.argv = old

    assert rc == 0
    report = json.loads(out_json.read_text())
    assert report["mode"] == "direct"
    assert len(report["levels"]) == 2
    # 8 requests at ~50ms each: level-1 must be materially slower than
    # level-4 in wall terms (parallelism actually happened).
    econ = report["economics"]
    assert set(econ.keys()) == {"1", "4"}
    assert econ["4"]["rps"] > econ["1"]["rps"]
    assert econ["1"]["cost_per_request_usd"] > 0
    md = out_md.read_text()
    assert "| concurrency |" in md


def test_benchmark_requires_explicit_cost_assumption(stub_server):
    """Unit economics must never silently inherit an invented hourly price."""
    bench = _load_bench_module()
    with pytest.raises(SystemExit) as error:
        bench.main(["--base-url", stub_server, "--model", "stub"])
    assert error.value.code == 2

 
def test_benchmark_rejects_success_status_without_openai_usage():
    """HTTP 200 is not a successful inference when the response contract is broken."""
    bench = _load_bench_module()
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class MalformedHandler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 - stdlib API
            length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(length)
            body = json.dumps({
                "choices": [{"message": {"role": "assistant", "content": "ok"}}]
            }).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), MalformedHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = bench.one_request(
            f"http://127.0.0.1:{server.server_address[1]}/v1/chat/completions",
            bench.build_payload("stub", "ping", 8),
            timeout_s=5,
            api_key=None,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert not result.ok
    assert "usage.prompt_tokens" in (result.error or "")
