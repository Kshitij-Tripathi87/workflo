"""Day 7 — application lifecycle: CRASHED vs READY_TIMEOUT vs READY.

The failure state is the difference between "your start command is wrong"
and "the app needs more time"; the lifecycle must not conflate them.
"""

from __future__ import annotations

import asyncio
import threading
import socket
import time

import pytest

from sandbox_runtime.config import RunConfig
from sandbox_runtime.workloads.app import (
    AppCrashedError,
    AppReadyTimeoutError,
    _wait_for_health,
    base_url_for,
)


class _FakeProc:
    """A process double with poll()/returncode semantics."""

    def __init__(self, returncode=None):
        self.returncode = returncode

    def poll(self):
        return self.returncode


def _run(coro):
    return asyncio.run(coro)


def test_crashed_process_fails_fast(tmp_path):
    log = tmp_path / "app.log"
    log.write_text("Traceback: import error\n")
    proc = _FakeProc(returncode=1)

    started = time.monotonic()
    # netns=None -> host-loopback probe (no Linux needed)
    with pytest.raises(AppCrashedError) as exc_info:
        _run(_wait_for_health(
            9, evidence=None, proc=proc, netns=None, timeout=30,
            app_log_path=log,
        ))
    elapsed = time.monotonic() - started

    assert "exited with code 1" in str(exc_info.value)
    assert "import error" in str(exc_info.value)  # log tail surfaced
    assert elapsed < 5  # did not burn the readiness window


def test_ready_when_port_accepts():
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    try:
        _run(_wait_for_health(
            port, evidence=None, proc=None, netns=None, timeout=5,
        ))
    finally:
        listener.close()


def test_ready_timeout_when_never_listens(tmp_path):
    proc = _FakeProc(returncode=None)  # alive but silent
    # Find a port nothing listens on
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    dead_port = probe.getsockname()[1]
    probe.close()

    with pytest.raises(AppReadyTimeoutError):
        _run(_wait_for_health(
            dead_port, evidence=None, proc=proc, netns=None, timeout=1,
        ))


def test_failure_state_labels():
    assert AppCrashedError("x").failure_state == "CRASHED"
    assert AppReadyTimeoutError("x").failure_state == "READY_TIMEOUT"


def test_base_url_uses_configured_port():
    cfg = RunConfig(sandbox_id="x", port=8123)
    assert base_url_for(cfg) == "http://app.workflo.internal:8123"
    cfg2 = RunConfig(sandbox_id="y", port=None)
    assert base_url_for(cfg2).endswith(":3000")
