"""Tests for supervisor IPC."""

import pytest
import tempfile
import threading
import time
import sys
from pathlib import Path

from workflo_supervisor.ipc import SupervisorServer, SupervisorClient


# Skip all tests on Windows since Unix sockets not supported
pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="Unix sockets not available on Windows")


def test_server_start_stop():
    """Test server starts and stops."""
    with tempfile.TemporaryDirectory() as tmpdir:
        socket_path = Path(tmpdir) / "test.sock"
        server = SupervisorServer(str(socket_path))
        
        server.start()
        time.sleep(0.1)  # Give server time to start
        
        assert socket_path.exists()
        
        server.stop()
        assert not socket_path.exists()


def test_client_server_roundtrip():
    """Test client can call server method."""
    with tempfile.TemporaryDirectory() as tmpdir:
        socket_path = Path(tmpdir) / "test.sock"
        server = SupervisorServer(str(socket_path))
        
        @server.register("echo")
        def echo(params):
            return {"message": params.get("msg", "")}
        
        server.start()
        time.sleep(0.1)
        
        client = SupervisorClient(str(socket_path))
        result = client.call("echo", {"msg": "hello"})
        
        assert result == {"message": "hello"}
        
        server.stop()


def test_unknown_method():
    """Test calling unknown method returns error."""
    with tempfile.TemporaryDirectory() as tmpdir:
        socket_path = Path(tmpdir) / "test.sock"
        server = SupervisorServer(str(socket_path))
        server.start()
        time.sleep(0.1)
        
        client = SupervisorClient(str(socket_path))
        
        with pytest.raises(RuntimeError, match="Unknown method"):
            client.call("nonexistent", {})
        
        server.stop()


def test_streaming_handler():
    """Test streaming handler yields multiple events."""
    with tempfile.TemporaryDirectory() as tmpdir:
        socket_path = Path(tmpdir) / "test.sock"
        server = SupervisorServer(str(socket_path))
        
        @server.register_stream("stream_test")
        def stream_test(params):
            yield "event1", {"data": "first"}
            yield "event2", {"data": "second"}
        
        server.start()
        time.sleep(0.1)
        
        client = SupervisorClient(str(socket_path))
        events = list(client.stream_events("stream_test", {}))
        
        assert len(events) == 3  # 2 events + done
        assert events[0] == ("event1", {"data": "first"})
        assert events[1] == ("event2", {"data": "second"})
        assert events[2][0] == "done"
        
        server.stop()

# ---------------------------------------------------------------------------
# P0 regression coverage: the IPC layer must never hang.
#
# Before this was fixed, `_serve_loop` raised NameError on the first inbound
# connection (threading was imported inside start(), so it was not in scope),
# the connection was never serviced, and SupervisorClient.call() blocked in
# recv() forever with no socket timeout — an indefinite hang rather than an
# error. The tests below assert a hard wall-clock bound so a regression FAILS
# instead of hanging the suite.
# ---------------------------------------------------------------------------

import socket as _socket
import time as _time


def _wait_for_socket(path, limit=5.0):
    """Wait until the server socket exists and accepts connections."""
    deadline = _time.monotonic() + limit
    while _time.monotonic() < deadline:
        if path.exists():
            return
        _time.sleep(0.01)
    raise AssertionError(f"server socket never appeared at {path}")


def _call_with_wall_clock_limit(client, method, params, limit=10.0):
    """Run client.call() in a daemon thread; fail if it has not returned.

    Daemon thread (not ThreadPoolExecutor) so a regression cannot block
    interpreter shutdown and hang pytest.
    """
    outcome = {}

    def target():
        try:
            outcome["value"] = client.call(method, params)
        except BaseException as e:  # noqa: BLE001 - re-raised below
            outcome["error"] = e

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(limit)
    assert not thread.is_alive(), (
        f"client.call({method!r}) did not return within {limit}s — the client "
        "is hanging (the exact failure mode this suite guards against)"
    )
    if "error" in outcome:
        raise outcome["error"]
    return outcome["value"]


def test_roundtrip_completes_without_hanging():
    """P0 acceptance: connect -> request handled -> response -> no hang."""
    with tempfile.TemporaryDirectory() as tmpdir:
        socket_path = Path(tmpdir) / "test.sock"
        server = SupervisorServer(str(socket_path))

        @server.register("echo")
        def echo(params):
            return {"message": params.get("msg", "")}

        server.start()
        try:
            _wait_for_socket(socket_path)
            client = SupervisorClient(str(socket_path))
            result = _call_with_wall_clock_limit(client, "echo", {"msg": "hello"})
            assert result == {"message": "hello"}
        finally:
            server.stop()


def test_server_keeps_serving_after_first_connection():
    """The old bug failed on the FIRST connection; guard against that class."""
    with tempfile.TemporaryDirectory() as tmpdir:
        socket_path = Path(tmpdir) / "test.sock"
        server = SupervisorServer(str(socket_path))

        @server.register("add")
        def add(params):
            return {"sum": params["a"] + params["b"]}

        server.start()
        try:
            _wait_for_socket(socket_path)
            client = SupervisorClient(str(socket_path))
            for i in range(3):
                result = _call_with_wall_clock_limit(client, "add", {"a": i, "b": 1})
                assert result == {"sum": i + 1}
        finally:
            server.stop()


def test_handler_exception_is_returned_as_error_not_a_hang():
    """A raising handler must produce a RuntimeError reply, not silence."""
    with tempfile.TemporaryDirectory() as tmpdir:
        socket_path = Path(tmpdir) / "test.sock"
        server = SupervisorServer(str(socket_path))

        @server.register("boom")
        def boom(params):
            raise ValueError("handler exploded")

        server.start()
        try:
            _wait_for_socket(socket_path)
            client = SupervisorClient(str(socket_path))
            with pytest.raises(RuntimeError, match="handler exploded"):
                _call_with_wall_clock_limit(client, "boom", {})
        finally:
            server.stop()


def test_silent_server_times_out_instead_of_hanging():
    """Timeout/error path: an unresponsive daemon raises within the bound.

    Connects to a socket that is listening but never replies — the previous
    behaviour was an infinite block in recv().
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        socket_path = Path(tmpdir) / "silent.sock"
        listener = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
        listener.bind(str(socket_path))
        listener.listen(1)
        try:
            client = SupervisorClient(str(socket_path), timeout=1.0)
            started = _time.monotonic()
            with pytest.raises(ConnectionError) as excinfo:
                _call_with_wall_clock_limit(client, "never_answers", {}, limit=10.0)
            elapsed = _time.monotonic() - started

            assert elapsed < 10.0, f"timed out too slowly ({elapsed:.1f}s)"
            # The message must name the method so the operator can act on it.
            assert "never_answers" in str(excinfo.value)
        finally:
            listener.close()


def test_stream_events_honours_a_timeout():
    """Bounded streaming also fails fast rather than hanging."""
    with tempfile.TemporaryDirectory() as tmpdir:
        socket_path = Path(tmpdir) / "silent.sock"
        listener = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
        listener.bind(str(socket_path))
        listener.listen(1)
        try:
            client = SupervisorClient(str(socket_path))
            started = _time.monotonic()
            with pytest.raises(ConnectionError):
                list(client.stream_events("run", {}, timeout=1.0))
            assert _time.monotonic() - started < 10.0
        finally:
            listener.close()


def test_stall_raises_connection_error_so_the_cli_can_fall_back():
    """SupervisorCLIClient.run() falls back to local execution only on
    FileNotFoundError/ConnectionError — so a stall must raise exactly that,
    otherwise `workflo run` hangs instead of degrading to local execution."""
    with tempfile.TemporaryDirectory() as tmpdir:
        socket_path = Path(tmpdir) / "silent.sock"
        listener = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
        listener.bind(str(socket_path))
        listener.listen(1)
        try:
            client = SupervisorClient(str(socket_path), timeout=1.0)
            with pytest.raises(ConnectionError) as excinfo:
                _call_with_wall_clock_limit(client, "verify", {}, limit=10.0)
            # ConnectionError is an OSError subclass; assert the CLI's except
            # clause would catch it.
            assert isinstance(excinfo.value, ConnectionError)
            assert isinstance(excinfo.value, OSError)
        finally:
            listener.close()


def test_stop_is_idempotent_and_leaves_no_socket():
    """stop() twice must not raise, and must remove the socket file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        socket_path = Path(tmpdir) / "test.sock"
        server = SupervisorServer(str(socket_path))
        server.start()
        _wait_for_socket(socket_path)
        server.stop()
        server.stop()
        assert not socket_path.exists()


def test_default_client_timeout_is_bounded():
    """A default-constructed client must not be unbounded (the hang vector)."""
    assert SupervisorClient().timeout is not None
