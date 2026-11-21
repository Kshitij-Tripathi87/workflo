"""Host vsock channel tests: framing, guest-initiated accept, teardown.

Runs entirely on AF_UNIX (the host half of Firecracker's vsock bridge),
so no KVM/vsock device is needed — the guest side is simulated with a
plain socket client, exactly what Firecracker does with AF_VSOCK.
"""

from __future__ import annotations

import socket
import struct
import threading
import time

import pytest
from workflo_worker_host.protocol import (
    MAX_MESSAGE_BYTES,
    GuestMessageType,
    build_guest_message,
    frame_message,
    parse_frame,
)
from workflo_worker_host.vsock_channel import (
    HOST_CID,
    VSOCK_SUPERVISOR_PORT,
    ChannelError,
    HostVsockChannel,
    guest_initiated_listen_path,
    recv_frame,
    send_frame,
)


def _frame(payload_size: int = 16) -> bytes:
    return frame_message(
        build_guest_message(
            message_id="msg-1",
            attempt_id="attempt-1",
            sandbox_id="sbx-1",
            sequence_number=1,
            message_type=GuestMessageType.GUEST_READY,
            sent_at="2026-01-01T00:00:00.000Z",
            payload={"pad": "x" * payload_size},
        )
    )


def test_supervisor_port_is_outside_reserved_range():
    # docs/vsock.md: ports in [2^30, 2^31) are reserved for host-initiated
    # channels; guest requests there are always rejected.
    assert not (2**30 <= VSOCK_SUPERVISOR_PORT < 2**31)
    assert HOST_CID == 2


def test_listen_path_appends_decimal_port():
    assert (
        guest_initiated_listen_path("/run/workflo/vsock/sbx-1.sock")
        == f"/run/workflo/vsock/sbx-1.sock_{VSOCK_SUPERVISOR_PORT}"
    )


def test_send_frame_roundtrips_and_validates_length():
    left, right = socket.socketpair()
    try:
        frame = _frame()
        send_frame(left, frame)
        got = recv_frame(right, timeout=1.0)
        assert got == frame
        assert parse_frame(got).message_type is GuestMessageType.GUEST_READY
    finally:
        left.close()
        right.close()


def test_send_frame_rejects_tampered_length_prefix():
    left, right = socket.socketpair()
    try:
        frame = bytearray(_frame())
        struct.pack_into(">I", frame, 0, 999_999)
        with pytest.raises(ChannelError, match="length prefix"):
            send_frame(left, bytes(frame))
    finally:
        left.close()
        right.close()


def test_recv_frame_times_out_cleanly_returns_none():
    left, right = socket.socketpair()
    try:
        started = time.monotonic()
        assert recv_frame(right, timeout=0.15) is None
        assert time.monotonic() - started >= 0.1
    finally:
        left.close()
        right.close()


def test_recv_frame_raises_on_eof():
    left, right = socket.socketpair()
    left.close()
    try:
        with pytest.raises(ChannelError, match="closed"):
            recv_frame(right, timeout=1.0)
    finally:
        right.close()


def test_recv_frame_rejects_oversize_declared_length():
    left, right = socket.socketpair()
    try:
        left.sendall(struct.pack(">I", MAX_MESSAGE_BYTES + 1))
        with pytest.raises(ChannelError, match="protocol maximum"):
            recv_frame(right, timeout=1.0)
    finally:
        left.close()
        right.close()


def test_channel_accepts_guest_and_exchanges_frames(tmp_path):
    listen_path = str(tmp_path / "vsock" / "sbx-1.sock_4242")
    channel = HostVsockChannel(listen_path, connect_timeout=5.0)
    channel.listen()
    assert channel.listen_path == listen_path

    connected = threading.Event()
    errors: list = []

    def guest():
        try:
            deadline = time.monotonic() + 5.0
            while True:
                try:
                    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    sock.settimeout(1.0)
                    sock.connect(listen_path)
                    break
                except (FileNotFoundError, ConnectionRefusedError):
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.02)
            connected.set()
            # Host speaks first (capability): read one frame, reply ready.
            frame = recv_frame(sock, timeout=5.0)
            assert parse_frame(frame).message_type is (
                GuestMessageType.RUN_CAPABILITY_DELIVERED
            )
            send_frame(
                sock,
                frame_message(
                    build_guest_message(
                        message_id="msg-ready",
                        attempt_id="attempt-1",
                        sandbox_id="sbx-1",
                        sequence_number=1,
                        message_type=GuestMessageType.GUEST_READY,
                        sent_at="2026-01-01T00:00:00.000Z",
                        payload={},
                    )
                ),
            )
            sock.close()
        except Exception as exc:  # noqa: BLE001 — surfaced via errors list
            errors.append(exc)

    thread = threading.Thread(target=guest, daemon=True)
    thread.start()

    capability = frame_message(
        build_guest_message(
            message_id="host-capability-1",
            attempt_id="attempt-1",
            sandbox_id="sbx-1",
            sequence_number=1,
            message_type=GuestMessageType.RUN_CAPABILITY_DELIVERED,
            sent_at="2026-01-01T00:00:00.000Z",
            payload={"capability": {"x": 1}, "capability_digest": "sha256:00"},
        )
    )
    channel.send(capability)  # blocks until the guest connects
    assert connected.is_set()

    reply = channel.receive(timeout=5.0)
    assert reply is not None
    assert parse_frame(reply).message_type is GuestMessageType.GUEST_READY

    thread.join(timeout=5.0)
    assert not thread.is_alive()
    assert errors == []

    channel.close()
    # The socket file must be gone after close (teardown probe depends on it).
    import os

    assert not os.path.exists(listen_path)


def test_channel_send_fails_when_guest_never_connects(tmp_path):
    listen_path = str(tmp_path / "never.sock_4242")
    channel = HostVsockChannel(listen_path, connect_timeout=0.2)
    channel.listen()
    try:
        with pytest.raises(ChannelError, match="did not connect"):
            channel.send(_frame())
    finally:
        channel.close()


def test_channel_listen_replaces_stale_socket_file(tmp_path):
    listen_path = str(tmp_path / "stale.sock_4242")
    tmp_path.mkdir(parents=True, exist_ok=True)
    with open(listen_path, "wb"):
        pass  # stale file from a dead run
    channel = HostVsockChannel(listen_path, connect_timeout=1.0)
    channel.listen()  # must not raise
    channel.close()


def test_channel_close_is_idempotent(tmp_path):
    channel = HostVsockChannel(str(tmp_path / "c.sock_4242"), connect_timeout=1.0)
    channel.listen()
    channel.close()
    channel.close()  # second close is a no-op
