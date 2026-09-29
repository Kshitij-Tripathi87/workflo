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