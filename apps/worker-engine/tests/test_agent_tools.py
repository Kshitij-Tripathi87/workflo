"""Tests for the governed agent tool gateway.

The gateway is plain stdlib python — fully testable without a sandbox.
The allowlist contract is the security-critical part: HTTP tools only
reach *.workflo.internal, file tools only read approved roots, and every
call (allowed OR denied) is recorded.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from workflo_worker.agent_tools import (
    ToolGateway,
    ToolDenied,
    _validate_http_url,
    _path_allowed,
)


@pytest.fixture
def records(tmp_path):
    return tmp_path / "records.jsonl"


class TestHttpAllowlist:
    def test_internal_host_allowed(self):
        _validate_http_url("http://app.workflo.internal:3000/x")

    def test_bare_internal_allowed(self):
        _validate_http_url("http://workflo.internal/")

    def test_external_host_denied(self):
        with pytest.raises(ToolDenied, match="not under"):
            _validate_http_url("http://exfiltrate.example.com/steal")

    def test_https_denied(self):
        with pytest.raises(ToolDenied, match="scheme"):
            _validate_http_url("https://app.workflo.internal/")

    def test_lookalike_host_denied(self):
        with pytest.raises(ToolDenied):
            _validate_http_url("http://evil-workflo.internal.attacker.com/")


class TestFileAllowlist:
    def test_workspace_allowed(self):
        assert _path_allowed(Path("/workspace/repo/x.py"))

    def test_artifacts_allowed(self):
        assert _path_allowed(Path("/workflo/artifacts/report.json"))

    def test_etc_denied(self):
        assert not _path_allowed(Path("/etc/passwd"))

    def test_traversal_denied(self):
        # realpath of /workspace/../../etc/passwd escapes the root
        assert not _path_allowed(Path("/workspace/../../etc/passwd").resolve())


class TestRecordedCalls:
    def test_allowed_call_recorded(self, records, tmp_path):
        log = tmp_path / "app.log"
        log.write_text("line1\nline2\n")
        gw = ToolGateway(records, app_log_path=log)

        record = gw.call("read_log", {"lines": 10})

        assert record["denied"] is False
        assert record["ok"] is True
        assert record["seq"] == 1
        assert gw.tool_calls == 1
        assert gw.tools_used == ["read_log"]

        lines = records.read_text().strip().splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["tool"] == "read_log"

    def test_denied_call_recorded_with_reason(self, records):
        gw = ToolGateway(records)

        record = gw.call("http_get", {"url": "http://exfiltrate.example.com/"})

        assert record["denied"] is True
        assert "not under" in record["reason"]
        assert gw.denied_attempts == 1

        lines = records.read_text().strip().splitlines()
        assert json.loads(lines[0])["denied"] is True

    def test_unknown_tool_denied(self, records):
        gw = ToolGateway(records)

        record = gw.call("rm_rf", {"path": "/"})

        assert record["denied"] is True
        assert "unknown tool" in record["reason"]

    def test_every_call_recorded_in_order(self, records, tmp_path):
        log = tmp_path / "app.log"
        log.write_text("x\n")
        gw = ToolGateway(records, app_log_path=log)

        gw.call("read_log")
        gw.call("http_get", {"url": "http://evil.example.com/"})
        gw.call("read_log")

        assert gw.tool_calls == 3
        assert gw.denied_attempts == 1
        lines = [json.loads(l) for l in records.read_text().strip().splitlines()]
        assert [r["seq"] for r in lines] == [1, 2, 3]


class TestToolsAgainstRealHttp:
    """The HTTP tools run against a real local server (loopback stand-in
    for the in-netns app under test)."""

    @pytest.fixture(scope="class")
    def server(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/health":
                    body = b'{"status":"ok"}'
                else:
                    body = b"<html>fixture</html>"
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                self.rfile.read(length)
                self.send_response(201)
                self.end_headers()
                self.wfile.write(b'{"created": true}')

            def log_message(self, *args):
                pass

        httpd = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        yield httpd
        httpd.shutdown()

    def _rewriting_gateway(self, records, server):
        """A gateway whose opener rewrites *.workflo.internal URLs to the
        local app server (the same translation the netns performs)."""
        from urllib.parse import urlparse, urlunparse
        port = server.server_port

        def opener(request, timeout=None):
            parsed = urlparse(request.full_url)
            rewritten = urlunparse(parsed._replace(netloc=f"127.0.0.1:{port}"))
            import urllib.request as ur
            return ur.urlopen(ur.Request(rewritten, data=request.data,
                                         method=request.get_method()),
                              timeout=timeout)

        return ToolGateway(records, opener=opener)

    def test_http_get(self, records, server):
        gw = self._rewriting_gateway(records, server)
        record = gw.call("http_get", {"url": "http://app.workflo.internal:3000/health"})

        assert record["ok"] is True
        summary = record["result_summary"]
        assert summary["status"] == 200
        assert "ok" in summary["body_preview"]

    def test_http_post(self, records, server):
        gw = self._rewriting_gateway(records, server)
        record = gw.call("http_post", {
            "url": "http://app.workflo.internal:3000/items",
            "body": {"name": "x"},
        })

        assert record["ok"] is True
        assert record["result_summary"]["status"] == 201


class TestBoundedResults:
    def test_body_truncated(self, records, tmp_path):
        """Oversized tool results are bounded so the records file stays small."""
        big_file = tmp_path / "big.txt"
        big_file.write_text("x" * 100_000)
        # read_file caps at 16KB
        gw = ToolGateway(records, app_log_path=tmp_path / "app.log")

        # put the file inside an approved root by faking realpath target
        import workflo_worker.agent_tools as at
        real_read = Path.read_bytes

        def fake_read_bytes(self):
            if self == big_file:
                return real_read(self)
            return real_read(self)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(at, "ALLOWED_FILE_ROOTS", (str(tmp_path),))
            record = gw.call("read_file", {"path": str(big_file)})

        assert record["ok"] is True
        assert record["result_summary"]["size"] == 100_000
        assert len(record["result_summary"]["content_preview"]) <= 512
