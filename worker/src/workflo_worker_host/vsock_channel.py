"""Host-side vsock transport for the microVM slice (ADR-0022).

Firecracker's virtio-vsock bridges AF_VSOCK (guest) to AF_UNIX (host).
This slice uses the **guest-initiated** direction (docs/vsock.md):

- the guest connects to ``HOST_CID=2`` on a well-known port;
- Firecracker forwards it to an AF_UNIX socket the HOST listens on at
  ``<uds_path>_<PORT>`` (decimal port appended to the configured uds path);
- ports in ``[2^30, 2^31)`` are reserved for host-initiated channels and
  are always rejected for guest-initiated connections — the supervisor
  port below deliberately lives outside that range.

The channel carries already-framed protocol bytes (4-byte BE length +
canonical JSON, as ``protocol.frame_message`` produces). The transport
never interprets message contents: framing/policy stay in ``protocol``.

When the VMM is jailed, Firecracker resolves ``uds_path`` inside its
chroot, so the host listener must bind at the *host view* of that path
(``<chroot>/uds_path_<PORT>``) — callers pass the fully resolved path.
"""

from __future__ import annotations

import os
import socket
import struct
import time
from pathlib import Path

from workflo_worker_host.protocol import MAX_MESSAGE_BYTES

__all__ = [
    "HOST_CID",
    "VSOCK_SUPERVISOR_PORT",
    "ChannelError",
    "HostVsockChannel",
    "guest_initiated_listen_path",
    "recv_frame",
    "send_frame",
]

# Guest-initiated supervisor channel. OUTSIDE the reserved
# [2^30, 2^31) host-side range (guest requests there are rejected).
VSOCK_SUPERVISOR_PORT = 4242
# The host context CID on the firecracker virtio-vsock bus.
HOST_CID = 2

_HEADER = struct.Struct(">I")


class ChannelError(RuntimeError):
    """Transport-level failure on the host channel (not a protocol error)."""


def guest_initiated_listen_path(uds_path: str, port: int = VSOCK_SUPERVISOR_PORT) -> str:
    """The AF_UNIX path the host listens on for guest-initiated connections."""
    return f"{uds_path}_{port}"


def send_frame(sock: socket.socket, frame: bytes) -> None:
    """Send one already-framed message (length prefix included)."""
    if len(frame) < _HEADER.size:
        raise ChannelError("refusing to send a frame shorter than its header")
    declared = _HEADER.unpack_from(frame)[0]
    if declared != len(frame) - _HEADER.size:
        raise ChannelError(
            f"frame length prefix ({declared}) does not match body "
            f"({len(frame) - _HEADER.size})"
        )
    if declared > MAX_MESSAGE_BYTES:
        raise ChannelError(f"frame of {declared} bytes exceeds the protocol maximum")
    try:
        sock.sendall(frame)
    except OSError as exc:
        raise ChannelError(f"send failed: {type(exc).__name__}: {exc}") from exc


def _read_exact(sock: socket.socket, count: int, deadline: float) -> bytes | None:
    """Read exactly ``count`` bytes before ``deadline``.

    Returns None only if ZERO bytes arrived before the deadline (a clean
    timeout with no data). A partial read that then times out, or EOF in
    the middle, raises: half a frame is a broken stream, never a timeout.
    """
    chunks: list[bytes] = []
    got = 0
    while got < count:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            if got == 0:
                return None
            raise ChannelError(
                f"timed out mid-frame after {got}/{count} bytes"
            )
        sock.settimeout(remaining)
        try:
            chunk = sock.recv(count - got)
        except TimeoutError:
            if got == 0:
                return None
            raise ChannelError(
                f"timed out mid-frame after {got}/{count} bytes"
            ) from None
        except OSError as exc:
            raise ChannelError(f"recv failed: {type(exc).__name__}: {exc}") from exc
        if not chunk:
            if got == 0:
                raise ChannelError("peer closed the connection")
            raise ChannelError(
                f"peer closed mid-frame after {got}/{count} bytes"
            )
        chunks.append(chunk)
        got += len(chunk)
    return b"".join(chunks)


def recv_frame(sock: socket.socket, *, timeout: float) -> bytes | None:
    """Receive one full frame. None = no data within ``timeout``."""
    deadline = time.monotonic() + timeout
    header = _read_exact(sock, _HEADER.size, deadline)
    if header is None:
        return None
    (length,) = _HEADER.unpack(header)
    if length > MAX_MESSAGE_BYTES:
        raise ChannelError(
            f"peer declared a {length} byte frame; protocol maximum is "
            f"{MAX_MESSAGE_BYTES}"
        )
    body = _read_exact(sock, length, deadline)
    if body is None:  # pragma: no cover — header already consumed time
        raise ChannelError("timed out after frame header")
    return header + body


class HostVsockChannel:
    """Host endpoint: bind ``<uds_path>_<PORT>``, accept one guest, move frames.

    The guest initiates, so the listener is up BEFORE the VM boots and the
    first ``send``/``receive`` accepts the connection (bounded by
    ``connect_timeout``). A single connection serves the whole slice —
    the protocol is a session, not a datagram stream.
    """

    def __init__(
        self,
        listen_path: str,
        *,
        port: int = VSOCK_SUPERVISOR_PORT,
        connect_timeout: float = 30.0,
    ):
        self._listen_path = listen_path
        self._port = port
        self._connect_timeout = connect_timeout
        self._listener: socket.socket | None = None
        self._conn: socket.socket | None = None
        self._closed = False

    @property
    def listen_path(self) -> str:
        return self._listen_path

    @property
    def connected(self) -> bool:
        return self._conn is not None

    def listen(self) -> None:
        """Bind and listen. Replaces a stale socket file from a dead run."""
        if self._closed:
            raise ChannelError("channel is closed")
        if self._listener is not None:
            return
        path = Path(self._listen_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if path.exists() or path.is_symlink():
                path.unlink()
        except OSError as exc:
            raise ChannelError(
                f"cannot clear stale socket {path}: {type(exc).__name__}: {exc}"
            ) from exc
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            listener.bind(self._listen_path)
            listener.listen(1)
        except OSError as exc:
            listener.close()
            raise ChannelError(
                f"cannot listen on {self._listen_path}: {type(exc).__name__}: {exc}"
            ) from exc
        self._listener = listener

    def _ensure_connection(self, timeout: float) -> bool:
        """Accept the guest connection if it has not arrived yet."""
        if self._conn is not None:
            return True
        if self._listener is None:
            raise ChannelError("channel is not listening")
        if self._closed:
            raise ChannelError("channel is closed")
        self._listener.settimeout(max(timeout, 0.001))
        try:
            conn, _ = self._listener.accept()
        except TimeoutError:
            return False
        except OSError as exc:
            raise ChannelError(
                f"accept failed: {type(exc).__name__}: {exc}"
            ) from exc
        self._conn = conn
        # The listener has done its job for this slice; close it so the
        # socket file can be unlinked at teardown while conn stays live.
        try:
            self._listener.close()
        except OSError:  # pragma: no cover — best effort
            pass
        self._listener = None
        return True

    def send(self, frame: bytes) -> None:
        """Send one frame, accepting the guest connection if needed."""
        if not self._ensure_connection(self._connect_timeout):
            raise ChannelError(
                f"guest did not connect within {self._connect_timeout}s"
            )
        assert self._conn is not None
        send_frame(self._conn, frame)

    def receive(self, *, timeout: float) -> bytes | None:
        """Receive one frame within ``timeout``; None on clean timeout."""
        if self._conn is None:
            if not self._ensure_connection(min(timeout, self._connect_timeout)):
                return None
        assert self._conn is not None
        return recv_frame(self._conn, timeout=timeout)

    def close(self) -> None:
        """Close connection + listener and unlink the socket file."""
        if self._closed:
            return
        self._closed = True
        for sock in (self._conn, self._listener):
            if sock is not None:
                try:
                    sock.close()
                except OSError:  # pragma: no cover — best effort
                    pass
        self._conn = None
        self._listener = None
        try:
            os.unlink(self._listen_path)
        except FileNotFoundError:
            pass
        except OSError:  # pragma: no cover — best effort
            pass
