"""Unit tests for the web tier's app_starter module.

Covers the three distinct failure modes the module promises to keep apart:
  - app exited early      -> RuntimeError("app process exited early ...")
  - app never bound       -> TimeoutError("app did not bind to port ...")
  - app bound + serving   -> returns a live Popen handle
"""

from __future__ import annotations

import subprocess
import sys
from unittest.mock import patch

import pytest

from workflo_worker.web.app_starter import (
    start_app_under_test,
    stop_app_under_test,
)


class FakePopen:
    """A minimal stand-in for subprocess.Popen we control fully."""

    def __init__(self, returncode=None, terminate_raises=False):
        self.returncode = returncode
        self._terminated = False
        self._terminate_raises = terminate_raises

    def poll(self):
        return self.returncode

    def terminate(self):
        if self._terminate_raises:
            raise OSError("already dead")
        self._terminated = True

    def kill(self):
        self._terminated = True

    def wait(self, timeout=None):
        if self._terminated:
            return 0
        raise subprocess.TimeoutExpired("fake", timeout)

    @property
    def terminated(self):
        return self._terminated


@pytest.fixture
def fake_popen():
    return FakePopen()


class TestStartAppUnderTest:
    def test_returns_popen_when_port_binds(self, fake_popen):
        """Happy path: the app binds the port -> we return the Popen handle."""
        with patch(
            "workflo_worker.web.app_starter.subprocess.Popen",
            return_value=fake_popen,
        ), patch(
            "workflo_worker.web.app_starter.socket.create_connection",
        ) as mock_connect:
            proc = start_app_under_test("/repo", "python app.py", 5000, timeout=2)

        assert proc is fake_popen
        mock_connect.assert_called()

    def test_raises_runtime_error_when_app_exits_early(self):
        """A crashing app must raise RuntimeError (the "app died" case) —
        NOT TimeoutError. The two failure modes are semantically different
        (app crashed vs never bound) and must stay distinguishable."""
        dead_popen = FakePopen(returncode=1)
        with patch(
            "workflo_worker.web.app_starter.subprocess.Popen",
            return_value=dead_popen,
        ), patch(
            "workflo_worker.web.app_starter.socket.create_connection",
            side_effect=OSError("connection refused"),
        ):
            with pytest.raises(RuntimeError, match="app process exited early"):
                start_app_under_test("/repo", "python broken.py", 5000, timeout=1)

    def test_raises_timeout_error_when_port_never_binds(self, fake_popen):
        """App alive but never binds -> TimeoutError, and the app gets
        terminated so we don't leak a background process."""
        with patch(
            "workflo_worker.web.app_starter.subprocess.Popen",
            return_value=fake_popen,
        ), patch(
            "workflo_worker.web.app_starter.socket.create_connection",
            side_effect=OSError("connection refused"),
        ):
            with pytest.raises(TimeoutError, match="did not bind to port 5000"):
                start_app_under_test("/repo", "python app.py", 5000, timeout=1)

        assert fake_popen.terminated

    def test_empty_start_command_raises_before_launch(self):
        """An empty start_command is a config bug — fail before spawning
        anything (defense in depth: never invoke subprocess with [''])."""
        with patch("workflo_worker.web.app_starter.subprocess.Popen") as mock_popen:
            with pytest.raises(RuntimeError, match="start_command is empty"):
                start_app_under_test("/repo", "   ", 5000, timeout=1)
        mock_popen.assert_not_called()


class TestStopAppUnderTest:
    def test_never_raises_on_dead_process(self):
        """Best-effort stop: a process that's already gone must not raise."""
        stop_app_under_test(None)
        stop_app_under_test(FakePopen(returncode=0))
        stop_app_under_test(FakePopen(terminate_raises=True))

    def test_terminates_live_process(self):
        p = FakePopen()
        stop_app_under_test(p)
        assert p.terminated
