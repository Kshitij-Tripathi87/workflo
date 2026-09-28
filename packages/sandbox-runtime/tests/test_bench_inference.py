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


def _load_bench_module():
    """Load bench_inference.py by path (it lives outside the package tree)."""
    import importlib.util
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    target = root / "bench" / "model-serving" / "bench_inference.py"
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
