"""Unix socket IPC protocol for supervisor communication."""

from __future__ import annotations

import json
import socket
import struct
from dataclasses import dataclass
from typing import Optional, Dict, Any
from pathlib import Path


SOCKET_PATH = "/run/workflo/workflod.sock"
USER_SOCKET_PATH = "~/.workflo/workflod.sock"


@dataclass
class Request:
    method: str
    params: Dict[str, Any]
    id: int


@dataclass
class Response:
    id: int
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    event: Optional[str] = None
    event_data: Optional[Dict[str, Any]] = None


class SupervisorClient:
    """Client for communicating with workflod supervisor."""
    
    def __init__(self, socket_path: Optional[str] = None):
        self.socket_path = socket_path or SOCKET_PATH
        self._request_id = 0
    
    def _get_socket_path(self) -> Path:
        """Resolve socket path, trying system then user."""
        paths = [
            Path(self.socket_path),
            Path(USER_SOCKET_PATH).expanduser(),
        ]
        for p in paths:
            if p.exists():
                return p
        raise FileNotFoundError(f"Supervisor socket not found at {paths}")
    
    def call(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Make a blocking RPC call to supervisor."""
        sock_path = self._get_socket_path()
        
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.connect(str(sock_path))
            
            self._request_id += 1
            request = Request(method=method, params=params, id=self._request_id)
            
            # Send request (length-prefixed JSON)
            request_json = json.dumps(request.__dict__)
            sock.sendall(struct.pack(">I", len(request_json)))
            sock.sendall(request_json.encode())
            
            # Read response
            length_data = sock.recv(4)
            if not length_data:
                raise ConnectionError("Supervisor closed connection")
            length = struct.unpack(">I", length_data)[0]
            
            response_data = b""
            while len(response_data) < length:
                chunk = sock.recv(length - len(response_data))
                if not chunk:
                    break
                response_data += chunk
            
            response = json.loads(response_data.decode())
            
            if response.get("error"):
                raise RuntimeError(f"Supervisor error: {response['error']}")
            
            return response.get("result", {})
    
    def stream_events(self, method: str, params: Dict[str, Any]):
        """Stream events from a long-running operation."""
        sock_path = self._get_socket_path()
        
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.connect(str(sock_path))
            
            self._request_id += 1
            request = Request(method=method, params=params, id=self._request_id)
            
            request_json = json.dumps(request.__dict__)
            sock.sendall(struct.pack(">I", len(request_json)))
            sock.sendall(request_json.encode())
            
            # Stream events until final result
            while True:
                length_data = sock.recv(4)
                if not length_data:
                    break
                length = struct.unpack(">I", length_data)[0]
                
                response_data = b""
                while len(response_data) < length:
                    chunk = sock.recv(length - len(response_data))
                    if not chunk:
                        break
                    response_data += chunk
                
                response = json.loads(response_data.decode())
                
                if response.get("event"):
                    yield response["event"], response.get("event_data", {})
                elif response.get("result") is not None or response.get("error"):
                    if response.get("error"):
                        raise RuntimeError(f"Supervisor error: {response['error']}")
                    yield "done", response.get("result", {})
                    break


class SupervisorServer:
    """Unix socket server for workflod supervisor."""
    
    def __init__(self, socket_path: str = SOCKET_PATH):
        self.socket_path = Path(socket_path)
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        self._handlers: Dict[str, callable] = {}
        self._stream_handlers: Dict[str, callable] = {}
        self._server_socket: Optional[socket.socket] = None
    
    def register(self, method: str):
        """Decorator to register a handler for a method."""
        def decorator(func):
            self._handlers[method] = func
            return func
        return decorator
    
    def register_stream(self, method: str):
        """Decorator to register a streaming handler."""
        def decorator(func):
            self._stream_handlers[method] = func
            return func
        return decorator
    
    def start(self):
        """Start the server."""
        # Remove existing socket
        if self.socket_path.exists():
            self.socket_path.unlink()
        
        self._server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server_socket.bind(str(self.socket_path))
        # Set permissions: user/group read-write only
        self.socket_path.chmod(0o660)
        self._server_socket.listen(5)
        
        import threading
        threading.Thread(target=self._serve_loop, daemon=True).start()
    
    def _serve_loop(self):
        """Main server loop."""
        while True:
            conn, _ = self._server_socket.accept()
            threading.Thread(target=self._handle_connection, args=(conn,), daemon=True).start()
    
    def _handle_connection(self, conn: socket.socket):
        """Handle a single connection."""
        import struct
        import json
        
        try:
            while True:
                length_data = conn.recv(4)
                if not length_data:
                    break
                length = struct.unpack(">I", length_data)[0]
                
                request_data = b""
                while len(request_data) < length:
                    chunk = conn.recv(length - len(request_data))
                    if not chunk:
                        break
                    request_data += chunk
                
                request = json.loads(request_data.decode())
                method = request.get("method")
                params = request.get("params", {})
                req_id = request.get("id", 0)
                
                if method in self._stream_handlers:
                    # Streaming handler
                    for event_type, event_data in self._stream_handlers[method](params):
                        response = {
                            "id": req_id,
                            "event": event_type,
                            "event_data": event_data
                        }
                        self._send_response(conn, response)
                    
                    # Send final result
                    response = {"id": req_id, "result": {"status": "completed"}}
                    self._send_response(conn, response)
                elif method in self._handlers:
                    # Regular handler
                    try:
                        result = self._handlers[method](params)
                        response = {"id": req_id, "result": result}
                    except Exception as e:
                        response = {"id": req_id, "error": str(e)}
                    self._send_response(conn, response)
                else:
                    response = {"id": req_id, "error": f"Unknown method: {method}"}
                    self._send_response(conn, response)
        except Exception:
            pass
        finally:
            conn.close()
    
    def _send_response(self, conn: socket.socket, response: dict):
        """Send length-prefixed JSON response."""
        import struct
        import json
        response_json = json.dumps(response)
        conn.sendall(struct.pack(">I", len(response_json)))
        conn.sendall(response_json.encode())
    
    def stop(self):
        """Stop the server."""
        if self._server_socket:
            self._server_socket.close()
        if self.socket_path.exists():
            self.socket_path.unlink()