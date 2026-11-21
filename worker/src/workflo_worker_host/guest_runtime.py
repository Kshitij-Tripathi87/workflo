"""Guest runtime for the microVM slice — runs INSIDE the microVM.

The in-guest program for one attempt. Its contract, in order (fail closed
at every step):

1. **Receive the run capability** — the FIRST host frame must be
   ``RUN_CAPABILITY_DELIVERED`` carrying a ``GuestCapabilityV1`` whose
   digest matches the envelope, bound to the attempt/sandbox identity the
   boot args declare (``workflo.attempt_id=… workflo.sandbox_id=…`` from
   ``/proc/cmdline``). Nothing else on the wire is trusted before this.
2. **Verify identity, then announce** — the supervisor refuses on any
   mismatch (capability vs boot args, expiry) and only then sends
   ``GUEST_READY`` as its first message.
3. **Run the fixed workload** — the slice's only work: deterministic,
   offline, bounded (see ``workload.py``).
4. **Submit evidence** — the evidence manifest carries the workload
   result and its digest; the host re-derives QA from it.
5. **Await host direction** — ``SHUTDOWN_REQUESTED`` ends the slice;
   ``RUN_CANCELLATION_RECEIVED`` stops new actions and keeps waiting for
   shutdown; any other host message type is a protocol violation and is
   reported as a guest failure (never silently ignored).

The transport is injected (AF_VSOCK in the guest; socketpair/queues in
tests), so this module is fully exercisable without a VM. ``main()`` is
the entrypoint wired into the guest image's init.
"""

from __future__ import annotations

import sys

from workflo_schema.contracts.canonical import (
    canonical_bytes,
    digest_matches,
    digest_of,
)
from workflo_schema.contracts.common import utc_now_ms

from workflo_worker_host.guest_supervisor import (
    GuestCapabilityV1,
    GuestIdentityError,
    GuestSupervisor,
)
from workflo_worker_host.protocol import (
    GuestMessageType,
    ProtocolError,
    parse_frame,
)
from workflo_worker_host.workload import run_fixed_workload

__all__ = [
    "GuestSliceResult",
    "main",
    "parse_boot_identity",
    "run_guest_slice",
]


class GuestSliceError(RuntimeError):
    """The slice cannot proceed; fail closed and do not announce ready."""


class GuestSliceResult:
    """Outcome of one in-guest slice run (serialised to the host log)."""

    def __init__(self, *, status: str, detail: str, workload: dict | None = None):
        self.status = status  # "completed" | "failed"
        self.detail = detail
        self.workload = workload
        self.finished_at = utc_now_ms()

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "detail": self.detail,
            "workload": self.workload,
            "finished_at": self.finished_at,
        }


def parse_boot_identity(cmdline: str) -> tuple[str, str]:
    """Extract (attempt_id, sandbox_id) from the kernel command line.

    The host appends both to ``kernel_boot_args`` (manager.build_vm_config),
    so a guest that cannot find them was not booted by this host — refuse.
    """
    attempt_id: str | None = None
    sandbox_id: str | None = None
    for token in cmdline.split():
        if token.startswith("workflo.attempt_id="):
            attempt_id = token.split("=", 1)[1] or None
        elif token.startswith("workflo.sandbox_id="):
            sandbox_id = token.split("=", 1)[1] or None
    if not attempt_id or not sandbox_id:
        raise GuestSliceError(
            "boot cmdline is missing workflo.attempt_id/workflo.sandbox_id; "
            "this guest was not provisioned by a workflo host"
        )
    return attempt_id, sandbox_id


def run_guest_slice(
    *,
    transport,
    cmdline: str,
    workspace: str,
    capability_timeout_seconds: float = 30.0,
    shutdown_timeout_seconds: float = 60.0,
) -> GuestSliceResult:
    """Drive one slice inside the guest over ``transport``.

    ``transport`` needs ``send(frame: bytes)`` and
    ``receive(timeout: float) -> bytes | None`` (already-framed bytes,
    exactly what ``protocol.frame_message`` produces). Never raises for
    workload failures — those become honest results — but does raise
    ``GuestSliceError``/``ProtocolError`` when the HOST violates the
    protocol (those are reported as guest failures by the caller).
    """
    # -- Step 1: the capability is the only door in ------------------------
    frame = transport.receive(timeout=capability_timeout_seconds)
    if frame is None:
        raise GuestSliceError(
            f"no capability arrived within {capability_timeout_seconds}s"
        )
    capability_message = parse_frame(frame)
    if capability_message.message_type is not GuestMessageType.RUN_CAPABILITY_DELIVERED:
        raise GuestSliceError(
            "first host message was "
            f"{capability_message.message_type.value}, not run_capability_delivered"
        )
    payload = capability_message.payload
    capability_dict = payload.get("capability")
    claimed_digest = payload.get("capability_digest")
    if not isinstance(capability_dict, dict) or not isinstance(claimed_digest, str):
        raise GuestSliceError("capability envelope is missing capability/digest")
    # Re-derive the digest from the received bytes: tampering with either
    # the capability or the digest must break this check.
    if not digest_matches(claimed_digest, capability_dict):
        raise GuestSliceError("capability digest does not match its payload")
    capability = GuestCapabilityV1.model_validate(capability_dict)

    # -- Step 2: identity from boot args, then verify, then announce -------
    attempt_id, sandbox_id = parse_boot_identity(cmdline)
    supervisor = GuestSupervisor(
        capability=capability,
        send_frame=transport.send,
    )
    try:
        supervisor.verify_identity(attempt_id, sandbox_id)
    except GuestIdentityError as exc:
        raise GuestSliceError(f"identity verification failed: {exc}") from exc
    supervisor.announce_ready()

    # -- Step 3: the fixed workload (the slice's only work) ----------------
    workload_result = run_fixed_workload(workspace)

    # -- Step 4: evidence manifest carries the workload result -------------
    workload_bytes = canonical_bytes(workload_result)
    entry = {
        "artifact_type": "workload_result",
        "sha256": digest_of(workload_result),
        "size_bytes": len(workload_bytes),
    }
    try:
        supervisor.build_evidence_manifest(
            [entry], workload_result=workload_result
        )
    except Exception as exc:  # noqa: BLE001 — manifest failure is a result
        supervisor.report_failure(
            error_class="evidence_submission_failed",
            detail=f"{type(exc).__name__}: {exc}",
        )
        return GuestSliceResult(
            status="failed",
            detail=f"evidence manifest failed: {type(exc).__name__}: {exc}",
            workload=workload_result,
        )

    # -- Step 5: await host direction (shutdown / cancellation) ------------
    import time

    deadline = time.monotonic() + shutdown_timeout_seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            detail = (
                f"no shutdown arrived within {shutdown_timeout_seconds}s"
            )
            supervisor.report_failure(error_class="shutdown_timeout", detail=detail)
            return GuestSliceResult(
                status="failed", detail=detail, workload=workload_result
            )
        host_frame = transport.receive(timeout=min(remaining, 5.0))
        if host_frame is None:
            continue
        try:
            action = supervisor.receive_host_message(host_frame)
        except ProtocolError as exc:
            # An unknown/violating host message is reported, not obeyed.
            supervisor.report_failure(
                error_class="protocol_violation", detail=str(exc)
            )
            return GuestSliceResult(
                status="failed",
                detail=f"host protocol violation: {exc}",
                workload=workload_result,
            )
        if action == "shutdown_requested":
            # receive_host_message already moved the supervisor to STOPPING.
            return GuestSliceResult(
                status="completed",
                detail="workload submitted and shutdown honoured",
                workload=workload_result,
            )
        # cancellation_received: record and keep waiting for shutdown —
        # cancellations are requests, not proof (brief §5).
        continue


def main(argv: list | None = None) -> int:
    """Entrypoint for the guest image's init (rootfs wiring).

    Reads the real kernel cmdline, connects AF_VSOCK to the host
    (CID 2, supervisor port), runs the slice, prints the result as JSON on
    serial, and exits 0 only on a completed slice.
    """
    import json
    import os
    from pathlib import Path

    from workflo_worker_host.vsock_channel import HOST_CID, VSOCK_SUPERVISOR_PORT

    args = list(sys.argv[1:] if argv is None else argv)
    workspace = os.environ.get("WORKFLO_WORKSPACE", "/workspace")
    for arg in args:
        if arg.startswith("--workspace="):
            workspace = arg.split("=", 1)[1]
    try:
        cmdline = Path("/proc/cmdline").read_text().strip()
    except OSError as exc:
        print(
            json.dumps(
                {"status": "failed", "detail": f"cannot read cmdline: {exc}"}
            ),
            flush=True,
        )
        return 1

    try:
        import socket

        if not hasattr(socket, "AF_VSOCK"):
            raise GuestSliceError("kernel has no AF_VSOCK support")
        sock = socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)
        sock.settimeout(30.0)
        sock.connect((HOST_CID, VSOCK_SUPERVISOR_PORT))
    except Exception as exc:  # noqa: BLE001 — connection failure is terminal
        print(
            json.dumps(
                {"status": "failed", "detail": f"vsock connect failed: {exc}"}
            ),
            flush=True,
        )
        return 1

    class _SocketTransport:
        def send(self, frame: bytes) -> None:
            sock.sendall(frame)

        def receive(self, *, timeout: float):
            from workflo_worker_host.vsock_channel import recv_frame

            sock.settimeout(timeout)
            return recv_frame(sock, timeout=timeout)

    try:
        result = run_guest_slice(
            transport=_SocketTransport(),
            cmdline=cmdline,
            workspace=workspace,
        )
        print(json.dumps(result.as_dict()), flush=True)
        return 0 if result.status == "completed" else 1
    except Exception as exc:  # noqa: BLE001 — report, never traceback-silently
        print(
            json.dumps(
                {"status": "failed", "detail": f"{type(exc).__name__}: {exc}"}
            ),
            flush=True,
        )
        return 1
    finally:
        try:
            sock.close()
        except OSError:  # pragma: no cover — best effort
            pass
