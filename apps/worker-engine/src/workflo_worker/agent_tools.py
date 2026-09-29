"""Governed agent tools — the allowlist-enforced tool layer for the agent.

This module runs INSIDE the sandbox. It is the boundary between the
agent and the outside world:

  - HTTP tools may only reach ``*.workflo.internal`` hosts (the netns
    nftables rules enforce the same constraint at the packet level —
    this allowlist is defense in depth, not the only gate).
  - File tools may only read under the sandbox's own writable binds
    (/workspace, /workflo/artifacts).
  - Every call — allowed OR denied — is recorded to a JSONL file in the
    artifacts directory. The host ingests those records into the
    hash-chained evidence ledger, so the set of calls an agent made is
    provable after the fact.

The trust model (v0.3): agent tool records are SELF-REPORTED by the
sandboxed process and NOTARIZED by the host (hash-chained into the
ledger, bound to the receipt via the evidence binding). Host-observed
evidence (isolation probes, canary, teardown verification) is produced
by the supervisor and is the stronger claim. A compromised agent can
omit its own records; it cannot forge host-observed evidence, tamper
with the ledger, or sign a receipt.

Standard library only — the runtime image ships no third-party deps for
the agent.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Allowlist contract
# ---------------------------------------------------------------------------

ALLOWED_HTTP_HOST_SUFFIX = ".workflo.internal"
ALLOWED_FILE_ROOTS = ("/workspace", "/workflo/artifacts")

MAX_HTTP_BODY_BYTES = 64 * 1024          # 64 KB preview cap
MAX_LOG_LINES = 200
MAX_LOG_BYTES = 16 * 1024                # 16 KB
MAX_LISTED_FILES = 500
MAX_LIST_DEPTH = 3
MAX_READ_FILE_BYTES = 16 * 1024          # 16 KB
HTTP_TIMEOUT_SECONDS = 5
# AG-3 (adversarial suite): request-side caps. The response caps above
# bound what the app can push INTO the agent; these bound what the agent
# can push OUT — oversized requests waste budget and only ever target
# the internal app, but the boundary stays enforcement-not-convention.
MAX_URL_LENGTH = 4096
MAX_REQUEST_BODY_BYTES = 1024 * 1024     # 1 MB

TOOLS = ("http_get", "http_post", "read_log", "list_files", "read_file")


class ToolDenied(Exception):
    """A tool call was rejected by the allowlist. Always recorded."""

    def __init__(self, tool: str, reason: str):
        super().__init__(reason)
        self.tool = tool
        self.reason = reason


class ToolError(Exception):
    """A tool call was allowed but failed at execution time."""

    def __init__(self, tool: str, reason: str):
        super().__init__(reason)
        self.tool = tool
        self.reason = reason


class ToolGateway:
    """Allowlist-enforced, fully-recorded tool access for the agent.

    opener: the callable used for HTTP calls (default
    urllib.request.urlopen). Injectable so embedders/tests can route
    HTTP through their own transport — the allowlist still applies
    before the opener is invoked.
    """

    def __init__(self, records_path: Path, app_log_path: Path = None,
                 opener=None):
        self.records_path = Path(records_path)
        self._app_log_path = Path(app_log_path) if app_log_path else Path("/workspace/app.log")
        self._opener = opener or urllib.request.urlopen
        self._seq = 0
        self.tool_calls = 0
        self.denied_attempts = 0
        self.errors = 0
        self.tools_used: list[str] = []

    # -- public entry point ------------------------------------------------

    def call(self, tool: str, args: Optional[dict] = None) -> dict:
        """Execute one governed tool call. Allowed OR denied, it is recorded."""
        args = dict(args or {})
        started = time.monotonic()
        denied = None
        result = None

        if tool not in TOOLS:
            denied = f"unknown tool {tool!r}"
        else:
            try:
                result = self._execute(tool, args)
            except ToolDenied as e:
                denied = e.reason
            except Exception as e:
                self.errors += 1
                result = {"ok": False, "error": f"{type(e).__name__}: {e}"}

        duration_ms = int((time.monotonic() - started) * 1000)
        record = {
            "seq": self._seq + 1,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "tool": tool,
            "args": _bounded_args(args),
            "denied": denied is not None,
            "ok": denied is None and bool(result and result.get("ok", True)),
            "duration_ms": duration_ms,
        }
        if denied is not None:
            record["reason"] = denied
            self.denied_attempts += 1
        elif result is not None:
            record["result_summary"] = _bounded_result(result)

        self._seq += 1
        self.tool_calls += 1
        if denied is None and tool not in self.tools_used:
            self.tools_used.append(tool)
        self._append_record(record)
        return record

    # -- tool implementations ----------------------------------------------

    def _execute(self, tool: str, args: dict) -> dict:
        if tool == "http_get":
            return self._http("GET", args)
        if tool == "http_post":
            return self._http("POST", args)
        if tool == "read_log":
            return self._read_log(args)
        if tool == "list_files":
            return self._list_files(args)
        if tool == "read_file":
            return self._read_file(args)
        raise ToolDenied(tool, "unknown tool")

    def _http(self, method: str, args: dict) -> dict:
        url = str(args.get("url", ""))
        if not url:
            raise ToolError(method.lower(), "url required")
        _validate_http_url(url)

        body = args.get("body")
        data = None
        if method == "POST":
            if body is None:
                raise ToolError("http_post", "body required for POST")
            data = json.dumps(body).encode("utf-8")
            if len(data) > MAX_REQUEST_BODY_BYTES:
                raise ToolDenied(
                    "http_post",
                    f"body exceeds {MAX_REQUEST_BODY_BYTES} bytes"
                )

        request = urllib.request.Request(
            url, data=data, method=method,
            headers={"User-Agent": "workflo-agent/0.3",
                     "Content-Type": "application/json"} if data else
                    {"User-Agent": "workflo-agent/0.3"},
        )
        try:
            with self._opener(request, timeout=HTTP_TIMEOUT_SECONDS) as resp:
                status = resp.status
                headers = dict(list(resp.headers.items())[:10])
                raw = resp.read(MAX_HTTP_BODY_BYTES)
                content_sha = hashlib.sha256(raw).hexdigest()
                body_truncated = len(raw) == MAX_HTTP_BODY_BYTES
        except urllib.error.HTTPError as e:
            # An HTTP error response IS a successful observation of the app
            return {
                "ok": True, "status": e.code,
                "headers": dict(list(e.headers.items())[:10]) if e.headers else {},
                "body_preview": e.read(MAX_HTTP_BODY_BYTES).decode("utf-8", "replace")[:512],
            }
        except (urllib.error.URLError, socket.timeout, OSError) as e:
            return {"ok": True, "status": None,
                    "error": f"{type(e).__name__}: {e}"}

        return {
            "ok": True,
            "status": status,
            "headers": headers,
            "body_preview": raw.decode("utf-8", "replace")[:512],
            "body_sha256": content_sha,
            "body_truncated": body_truncated,
        }

    def _read_log(self, args: dict) -> dict:
        path = self._app_log_path
        lines_arg = args.get("lines", MAX_LOG_LINES)
        try:
            lines = min(int(lines_arg), MAX_LOG_LINES)
        except (TypeError, ValueError):
            lines = MAX_LOG_LINES
        if not path.exists():
            return {"ok": True, "lines": [], "note": f"{path.name} not present yet"}
        raw = path.read_bytes()[-MAX_LOG_BYTES:]
        tail = raw.decode("utf-8", "replace").splitlines()[-lines:]
        return {"ok": True, "lines": tail, "line_count": len(tail)}

    def _list_files(self, args: dict) -> dict:
        root = Path(str(args.get("path", "/workspace/repo")))
        resolved = Path(os.path.realpath(str(root)))
        if not _path_allowed(resolved):
            raise ToolDenied("list_files", f"path outside approved roots: {root}")
        if not resolved.exists():
            return {"ok": True, "files": [], "note": "path does not exist"}
        files = []
        for dirpath, dirnames, filenames in os.walk(resolved):
            rel = Path(dirpath).relative_to(resolved)
            depth = len(rel.parts)
            if depth >= MAX_LIST_DEPTH:
                dirnames.clear()
                continue
            for name in filenames:
                p = rel / name
                files.append(p.as_posix() if rel.as_posix() != "." else name)
                if len(files) >= MAX_LISTED_FILES:
                    return {"ok": True, "files": files, "truncated": True}
        return {"ok": True, "files": sorted(files)}

    def _read_file(self, args: dict) -> dict:
        path_arg = str(args.get("path", ""))
        if not path_arg:
            raise ToolError("read_file", "path required")
        resolved = Path(os.path.realpath(path_arg))
        if not _path_allowed(resolved):
            raise ToolDenied("read_file", f"path outside approved roots: {path_arg}")
        if not resolved.is_file():
            return {"ok": True, "note": "not a file", "path": path_arg}
        raw = resolved.read_bytes()[:MAX_READ_FILE_BYTES]
        return {
            "ok": True,
            "path": path_arg,
            "size": resolved.stat().st_size,
            "content_preview": raw.decode("utf-8", "replace")[:512],
            "content_sha256": hashlib.sha256(resolved.read_bytes()).hexdigest(),
        }

    # -- recording ----------------------------------------------------------

    def _append_record(self, record: dict) -> None:
        self.records_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.records_path, "a") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _validate_http_url(url: str) -> None:
    """HTTP tools may only reach *.workflo.internal over http.

    AG-3/AG-4 hardening: oversized URLs are denied, and URLs carrying
    userinfo (``user@host``) are denied — embedded credentials have no
    legitimate use against the internal app and are a classic exfil
    vector (spec §4.3 AG-4).
    """
    from urllib.parse import urlparse
    if len(url) > MAX_URL_LENGTH:
        raise ToolDenied("http", f"url exceeds {MAX_URL_LENGTH} bytes")
    parsed = urlparse(url)
    if parsed.scheme != "http":
        raise ToolDenied("http", f"scheme must be http, got {parsed.scheme!r}")
    if parsed.username or parsed.password:
        raise ToolDenied("http", "URLs with embedded credentials are denied")
    host = parsed.hostname or ""
    if not (host == ALLOWED_HTTP_HOST_SUFFIX.lstrip(".")
            or host.endswith(ALLOWED_HTTP_HOST_SUFFIX)):
        raise ToolDenied(
            "http", f"host {host!r} not under {ALLOWED_HTTP_HOST_SUFFIX}"
        )


def _path_allowed(resolved: Path) -> bool:
    """File tools may only read under the sandbox's own writable binds."""
    for root in ALLOWED_FILE_ROOTS:
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _bounded_args(args: dict) -> dict:
    """Record args without unbounded payloads (bodies are summarized)."""
    out = {}
    for key, value in args.items():
        text = json.dumps(value, default=str)
        out[key] = text if len(text) <= 256 else text[:253] + "..."
    return out


def _bounded_result(result: dict) -> dict:
    """Record a bounded summary of a tool result."""
    summary = {}
    for key, value in result.items():
        if isinstance(value, list) and len(value) > 20:
            summary[key] = value[:20] + ["..."]
        elif isinstance(value, str) and len(value) > 512:
            summary[key] = value[:509] + "..."
        else:
            summary[key] = value
    return summary
