"""Host-side sandbox manager: typed microVM operations (ADR-0022, brief §3.3).

The host's ENTIRE responsibility set is here, and it is deliberately
narrow: validate the assignment, reserve resources, enforce network
policy, start the pinned VMM through the jailer, deliver the run
capability, monitor, terminate, and independently verify cleanup.

There is NO ``execute_command``. No host shell, no Docker socket, no host
filesystem access for the guest, no project code on the host. Every
operation is typed and bound to one sandbox/attempt.

The Firecracker client is a seam: the real implementation shells out to
the pinned jailer on Linux/KVM; tests inject a fake. The VM does not start
until the assignment, host eligibility, network ruleset, and resources
have all been validated — fail-closed ordering, matching the TS
provisioner pattern and the brief §3.1 sequence.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from typing import Callable, Protocol

from workflo_schema.contracts.common import DigestString
from workflo_schema.contracts.receipt import (
    TeardownCheckId,
    TeardownCheckV1,
    TeardownVerificationV1,
)
from workflo_schema.contracts.outcomes import TrustVerificationStatus
from workflo_schema.contracts.events import ProducerComponent, ProducerIdentityV1
from workflo_schema.contracts.common import utc_now_ms

from workflo_worker_host.admission import (
    PinnedRuntime,
    WorkerCapabilities,
    check_eligibility,
)
from workflo_worker_host.assignment import SandboxAssignmentV1
from workflo_worker_host.network import EgressPolicyError, apply_ruleset_or_block
from workflo_worker_host.protocol import (
    GuestMessageType,
    GuestProtocolSession,
    build_guest_message,
    frame_message,
)

__all__ = [
    "SandboxState",
    "SandboxHandle",
    "FirecrackerClient",
    "build_vm_config",
    "build_jailer_argv",
    "build_run_capability",
    "vsock_uds_path",
    "default_teardown_probes",
    "SandboxManager",
    "ProvisionError",
    "TeardownProbeSet",
]


class ProvisionError(RuntimeError):
    """Provisioning failed before the VM could be trusted; no partial trust."""


class SandboxState:
    PROVISIONING = "PROVISIONING"
    READY = "READY"
    TERMINATED = "TERMINATED"


@dataclass
class SandboxHandle:
    sandbox_id: str
    attempt_id: str
    run_id: str
    state: str
    scratch_disk_path: str | None = None
    guest_cid: int | None = None
    vcpu_count: int = 0
    memory_size_mib: int = 0
    shutdown_requested_at: str | None = None
    shutdown_deadline: str | None = None
    host_evidence: list = field(default_factory=list)
    # -- slice additions (capability delivery + verified teardown) ----------
    vsock_path: str | None = None
    capability_id: str | None = None
    capability_digest: str | None = None
    capability_expires_at: str | None = None
    host_out_sequence: int = 0
    network_applied: bool = False
    network_removal: str | None = None
    session: GuestProtocolSession | None = field(default=None, repr=False)
    last_teardown: TeardownVerificationV1 | None = field(default=None, repr=False)


class FirecrackerClient(Protocol):
    """The VMM seam. The real client shells the pinned jailer (Linux);
    tests inject a fake. Deliberately tiny: start, stop, is_running."""

    def start(self, sandbox_id: str, vm_config: dict, argv: list) -> None: ...

    def stop(self, sandbox_id: str) -> None: ...

    def is_running(self, sandbox_id: str) -> bool: ...


def build_vm_config(
    assignment: SandboxAssignmentV1,
    *,
    scratch_disk_path: str,
    vsock_path: str,
    guest_cid: int,
    kernel_boot_args: str = "console=ttyS0 reboot=k panic=1 pci=off",
) -> dict:
    """The Firecracker VM config — every value from the assignment."""
    limits = assignment.resource_limits
    # The guest can only verify a capability if it knows its own identity:
    # boot args carry the attempt/sandbox binding so the in-guest entrypoint
    # can cross-check the host-delivered capability (identity first, §3.1).
    identity_args = (
        f" workflo.attempt_id={assignment.attempt_id}"
        f" workflo.sandbox_id={assignment.sandbox_id}"
    )
    return {
        "boot-source": {
            "kernel_image_path": assignment.guest_image.kernel_path,
            "boot_args": f"{kernel_boot_args}{identity_args}",
        },
        "drives": [
            {
                "drive_id": "rootfs",
                "path_on_host": assignment.guest_image.rootfs_path,
                "is_root_device": True,
                "is_read_only": True,
            },
            {
                "drive_id": "scratch",
                "path_on_host": scratch_disk_path,
                "is_root_device": False,
                "is_read_only": False,
            },
        ],
        "machine-config": {
            "vcpu_count": limits.vcpus,
            "mem_size_mib": limits.memory_mib,
        },
        "vsock": {
            "guest_cid": guest_cid,
            "uds_path": vsock_path,
        },
    }


def build_jailer_argv(
    pinned: PinnedRuntime,
    *,
    sandbox_id: str,
    config_path: str,
    uid: int,
    gid: int,
    chroot_base: str = "/srv/jailer",
) -> list:
    """The pinned jailer argv (brief §3: VMM under jailer, never bare).

    NOTE (defect fix): the jailer's flag is ``--chroot-base-dir`` per
    docs/jailer.md — the previous ``--chroot-base`` would make a real jailer
    reject the invocation at argument parsing.
    """
    exec_file = pinned.firecracker_path
    return [
        pinned.jailer_path,
        "--id", sandbox_id,
        "--exec-file", exec_file,
        "--uid", str(uid),
        "--gid", str(gid),
        "--chroot-base-dir", chroot_base,
        "--", "--config-file", config_path,
    ]


def vsock_uds_path(vsock_dir: str, sandbox_id: str) -> str:
    """The vsock UDS path inside the guest's (chroot) namespace.

    Shared by the manager (vm_config) and the slice runner (host listener
    path) so the two can never drift apart.
    """
    return f"{vsock_dir}/{sandbox_id}.sock"


def build_run_capability(
    assignment: SandboxAssignmentV1,
    *,
    now_ms: str | None = None,
    ttl_seconds: int | None = None,
):
    """Build the one-time, attempt-bound run capability for a slice.

    The capability is delivered over the guest transport before readiness;
    its lifetime is the assignment's wall clock (fail-closed: the guest
    cannot keep authority past the run's own deadline).
    """
    from datetime import datetime, timedelta, timezone

    from workflo_schema.contracts.common import format_utc_ms

    from workflo_worker_host.guest_supervisor import GuestCapabilityV1

    issued_at = now_ms or utc_now_ms()
    ttl = ttl_seconds if ttl_seconds is not None else (
        assignment.resource_limits.wall_clock_seconds
    )
    issued_dt = datetime.strptime(issued_at, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
        tzinfo=timezone.utc
    )
    expires_at = format_utc_ms(issued_dt + timedelta(seconds=ttl))
    return GuestCapabilityV1(
        capability_id=f"cap-{assignment.sandbox_id}",
        attempt_id=assignment.attempt_id,
        sandbox_id=assignment.sandbox_id,
        policy_digest=assignment.policy_digest,
        allowed_operations=tuple(op.value for op in assignment.capabilities),
        issued_at=issued_at,
        expires_at=expires_at,
    )


def _derive_guest_cid(sandbox_id: str) -> int:
    # vsock CID: 3..0xFFFFFFFE (0/1/2 reserved). Deterministic per sandbox.
    digest = hashlib.sha256(sandbox_id.encode("utf-8")).digest()
    return 3 + (int.from_bytes(digest[:4], "big") % (0xFFFFFFFE - 3))


def _create_scratch_disk(path: str, disk_mib: int) -> None:
    """A fresh, bounded writable disk per attempt (never reused)."""
    from pathlib import Path

    target = Path(path)
    if target.exists():
        raise ProvisionError(f"scratch disk {path} already exists (fresh disk required)")
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "wb") as handle:
        handle.truncate(disk_mib * 1024 * 1024)


class TeardownProbeSet:
    """Injected probes for the eight canonical teardown checks.

    Every probe returns (passed: bool, detail: str|None). A probe that
    cannot run reports a FAILURE — "a check that cannot be performed
    counts as a failure" (the repo's own teardown rule).
    """

    def __init__(self, probes: dict | None = None):
        # NOTE: an explicitly EMPTY probe set means "no checks configured"
        # (all unperformable -> UNKNOWN), never the defaults.
        self._probes: dict = probes if probes is not None else default_teardown_probes()

    def run(self, handle: SandboxHandle, client: FirecrackerClient) -> tuple:
        checks = []
        for check_id in TeardownCheckId:
            probe = self._probes.get(check_id)
            if probe is None:
                checks.append(
                    TeardownCheckV1(
                        check_id=check_id,
                        passed=False,
                        detail="no probe configured; unperformable checks fail closed",
                    )
                )
                continue
            try:
                passed, detail = probe(handle, client)
            except Exception as exc:  # noqa: BLE001 — probe failure is a fact
                passed, detail = False, f"{type(exc).__name__}: {exc}"
            checks.append(
                TeardownCheckV1(check_id=check_id, passed=bool(passed), detail=detail)
            )
        return checks


def default_teardown_probes() -> dict:
    """All eight canonical probes, from the manager's own state + client seam.

    The four host-side checks (cgroups / netns / sockets / capabilities)
    are REAL filesystem + handle-state checks: this runtime never creates a
    sandbox cgroup or netns (jailer runs without ``--cgroup``/``--netns``),
    so verifying their absence at the managed paths IS the honest check —
    and a per-sandbox nftables table that was applied but never removed
    fails the netns check (the network teardown half of that check id).
    """
    from workflo_worker_host.vsock_channel import (
        VSOCK_SUPERVISOR_PORT,
        guest_initiated_listen_path,
    )

    def vmm_exited(handle: SandboxHandle, client: FirecrackerClient):
        return (not client.is_running(handle.sandbox_id)), None

    def disk_destroyed(handle: SandboxHandle, client: FirecrackerClient):
        from pathlib import Path

        if handle.scratch_disk_path is None:
            return False, "no scratch disk was recorded"
        return (not Path(handle.scratch_disk_path).exists()), None

    def process_scope_empty(handle: SandboxHandle, client: FirecrackerClient):
        # The manager tracks no child processes beyond the VMM itself;
        # an empty scope is implied by vmm_exited plus the client seam.
        return (not client.is_running(handle.sandbox_id)), "tracked scope is the VMM only"

    def cgroups_removed(handle: SandboxHandle, client: FirecrackerClient):
        from pathlib import Path

        if not Path("/sys/fs/cgroup").exists():
            return False, "cgroup filesystem not mounted; cannot verify cgroup absence"
        managed = (
            f"/sys/fs/cgroup/workflo/{handle.sandbox_id}",
            f"/sys/fs/cgroup/firecracker/{handle.sandbox_id}",
        )
        present = [p for p in managed if Path(p).exists()]
        if present:
            return False, f"sandbox cgroup still present: {', '.join(present)}"
        return True, "no sandbox cgroup at managed paths (runtime creates none)"

    def netns_removed(handle: SandboxHandle, client: FirecrackerClient):
        from pathlib import Path

        netns_paths = (
            f"/var/run/netns/{handle.sandbox_id}",
            f"/run/netns/{handle.sandbox_id}",
        )
        present = [p for p in netns_paths if Path(p).exists()]
        if present:
            return False, f"network namespace still present: {', '.join(present)}"
        if handle.network_applied:
            if handle.network_removal == "removed":
                return True, "no netns; per-sandbox nftables table removed"
            return False, (
                f"no netns, but egress table teardown is unproven: "
                f"{handle.network_removal or 'never attempted'}"
            )
        return True, "no netns and no per-sandbox egress table was applied"

    def sockets_closed(handle: SandboxHandle, client: FirecrackerClient):
        from pathlib import Path

        if handle.vsock_path is None:
            return False, "no vsock path was recorded for this sandbox"
        host_view = getattr(client, "host_view_path", None)

        def _host(p: str) -> str:
            return host_view(handle.sandbox_id, p) if host_view else p

        # Two sockets must be gone: firecracker's own host-initiated
        # listener at uds_path, and the host-side guest-initiated listener
        # at uds_path_<PORT> (both resolved through the client's chroot
        # view when the VMM is jailed).
        candidates = [
            _host(handle.vsock_path),
            _host(
                guest_initiated_listen_path(
                    handle.vsock_path, VSOCK_SUPERVISOR_PORT
                )
            ),
        ]
        present = [p for p in dict.fromkeys(candidates) if Path(p).exists()]
        if present:
            return False, f"vsock socket still present: {', '.join(present)}"
        return True, None

    def capabilities_expired(handle: SandboxHandle, client: FirecrackerClient):
        if handle.capability_id is None:
            return False, "no run capability was recorded for this sandbox"
        from workflo_schema.contracts.common import utc_now_ms

        now = utc_now_ms()
        vm_running = client.is_running(handle.sandbox_id)
        if now > handle.capability_expires_at:
            return True, f"capability {handle.capability_id} expired at {handle.capability_expires_at}"
        if vm_running:
            return False, (
                f"capability {handle.capability_id} still live "
                f"(expires {handle.capability_expires_at}) and the VMM is running"
            )
        return True, (
            f"capability {handle.capability_id} unusable: VMM terminated "
            f"(expires {handle.capability_expires_at})"
        )

    return {
        TeardownCheckId.VMM_EXITED: vmm_exited,
        TeardownCheckId.VM_STOPPED: vmm_exited,
        TeardownCheckId.DISK_DESTROYED: disk_destroyed,
        TeardownCheckId.PROCESS_SCOPE_EMPTY: process_scope_empty,
        TeardownCheckId.CGROUPS_REMOVED: cgroups_removed,
        TeardownCheckId.NETNS_REMOVED: netns_removed,
        TeardownCheckId.SOCKETS_CLOSED: sockets_closed,
        TeardownCheckId.CAPABILITIES_EXPIRED: capabilities_expired,
    }


class SandboxManager:
    """Typed host operations. Nothing here executes project code."""

    def __init__(
        self,
        *,
        client: FirecrackerClient,
        pinned: PinnedRuntime,
        capabilities: WorkerCapabilities,
        require_signed_assignment: bool = True,
        guest_ready_timeout_seconds: int = 30,
        probes: dict | None = None,
        scratch_dir: str = "/var/lib/workflo/scratch",
        vsock_dir: str = "/run/workflo/vsock",
        apply_network: Callable | None = None,
        remove_network: Callable | None = None,
        receive_guest_message: Callable | None = None,
        send_guest_message: Callable | None = None,
        close_guest_transport: Callable | None = None,
        create_scratch_disk: Callable | None = None,
        uid: int = 0,
        gid: int = 0,
    ):
        self._client = client
        self._pinned = pinned
        self._caps = capabilities
        self._require_signed = require_signed_assignment
        self._guest_ready_timeout = guest_ready_timeout_seconds
        # An explicitly EMPTY probe set means "no checks configured" (all
        # unperformable -> UNKNOWN); only None selects the defaults.
        self._probes = TeardownProbeSet(
            probes if probes is not None else default_teardown_probes()
        )
        self._scratch_dir = scratch_dir
        self._vsock_dir = vsock_dir
        self._apply_network = apply_network
        self._remove_network = remove_network
        self._receive_guest_message = receive_guest_message
        self._send_guest_message = send_guest_message
        self._close_guest_transport = close_guest_transport
        self._uid = uid
        self._gid = gid
        self._create_scratch_disk = create_scratch_disk or _create_scratch_disk
        self._sandboxes: dict = {}

    def sandbox_handle(self, sandbox_id: str) -> SandboxHandle | None:
        """Look up a handle (including for sandboxes that failed provisioning)."""
        return self._sandboxes.get(sandbox_id)

    # -- ProvisionSandbox -------------------------------------------------

    def provision_sandbox(self, assignment: SandboxAssignmentV1) -> SandboxHandle:
        """Fail-closed provisioning, in the brief's §3.1 order."""
        if self._require_signed and not assignment.signature:
            raise ProvisionError(
                "refusing an unsigned assignment (production requires "
                "authenticated execution assignments)"
            )
        blockers = check_eligibility(self._caps, assignment, self._pinned)
        if blockers:
            raise ProvisionError(
                "worker ineligible for this assignment: " + "; ".join(blockers)
            )

        sandbox_id = assignment.sandbox_id
        if sandbox_id in self._sandboxes:
            raise ProvisionError(f"sandbox {sandbox_id} already exists")

        # Network first: an unenforceable policy means NO VM (fail closed).
        verdict = apply_ruleset_or_block(
            self._apply_network or (lambda ruleset: None),
            sandbox_id,
            assignment.network_policy,
        )
        if not verdict.enforced:
            raise ProvisionError(
                f"egress policy could not be enforced: {verdict.reason}"
            )
        # Only claim enforcement when a REAL applier was wired; the noop
        # (tests / no-network deployments) applied nothing, and the netns
        # teardown probe must not be asked to remove a table that never
        # existed.
        network_applied = self._apply_network is not None and verdict.enforced

        # A VM with no capability-delivery / readiness transport would be a
        # black box: refuse before allocating anything (fail closed).
        if self._send_guest_message is None:
            raise ProvisionError(
                "no guest transport configured; refusing to provision without "
                "a capability delivery path"
            )
        if self._receive_guest_message is None:
            raise ProvisionError(
                "no guest transport configured; refusing to provision without "
                "a readiness verification path"
            )

        scratch_path = f"{self._scratch_dir}/{sandbox_id}.img"
        from pathlib import Path as _Path

        _Path(scratch_path).parent.mkdir(parents=True, exist_ok=True)
        try:
            self._create_scratch_disk(scratch_path, assignment.resource_limits.disk_mib)
        except OSError as exc:
            raise ProvisionError(
                f"scratch disk allocation failed: {type(exc).__name__}: {exc}"
            ) from exc

        guest_cid = _derive_guest_cid(sandbox_id)
        vsock_path = vsock_uds_path(self._vsock_dir, sandbox_id)
        vm_config = build_vm_config(
            assignment,
            scratch_disk_path=scratch_path,
            vsock_path=vsock_path,
            guest_cid=guest_cid,
        )
        try:
            self._client.start(sandbox_id, vm_config, [])
        except Exception as exc:  # noqa: BLE001 — boot failure is terminal for this attempt
            self._remove_scratch(sandbox_id, scratch_path)
            if network_applied:
                # The table went up before boot; boot failure must not leak it.
                removal_error: str | None = None
                if self._remove_network is not None:
                    try:
                        self._remove_network(sandbox_id)
                    except Exception as net_exc:  # noqa: BLE001
                        removal_error = (
                            f"egress table removal also failed: "
                            f"{type(net_exc).__name__}: {net_exc}"
                        )
                else:
                    removal_error = (
                        "egress table was applied but no removal transport "
                        "is configured"
                    )
                if removal_error:
                    raise ProvisionError(
                        f"VMM failed to start: {type(exc).__name__}: {exc}; "
                        f"{removal_error}"
                    ) from exc
            raise ProvisionError(
                f"VMM failed to start: {type(exc).__name__}: {exc}"
            ) from exc

        handle = SandboxHandle(
            sandbox_id=sandbox_id,
            attempt_id=assignment.attempt_id,
            run_id=assignment.run_id,
            state=SandboxState.PROVISIONING,
            scratch_disk_path=scratch_path,
            guest_cid=guest_cid,
            vcpu_count=assignment.resource_limits.vcpus,
            memory_size_mib=assignment.resource_limits.memory_mib,
            vsock_path=vsock_path,
            network_applied=network_applied,
            session=GuestProtocolSession(
                attempt_id=assignment.attempt_id, sandbox_id=sandbox_id
            ),
        )
        self._sandboxes[sandbox_id] = handle

        # The VM must prove its identity before any project work starts
        # (brief §3.1: "Verify guest supervisor identity"): the run
        # capability is delivered first — the guest cannot announce ready
        # without it — then readiness is verified on the same transport.
        try:
            capability = build_run_capability(assignment)
            self.deliver_run_capability(handle, capability)
            self._await_guest_ready(handle, assignment)
        except Exception:
            self.destroy_sandbox(handle)
            raise
        handle.state = SandboxState.READY
        return handle

    def deliver_run_capability(
        self, handle: SandboxHandle, capability
    ) -> str:
        """DeliverRunCapability (ADR-0022 §3.3): send the attempt-bound run
        capability to the guest over the host→guest transport.

        Fails closed: no send seam, wrong binding, or a transport error
        aborts provisioning (the guest gets no authority it cannot prove).
        Returns the capability digest for host evidence.
        """
        if self._send_guest_message is None:
            raise ProvisionError("no guest transport configured for capability delivery")
        if (
            capability.attempt_id != handle.attempt_id
            or capability.sandbox_id != handle.sandbox_id
        ):
            raise ProvisionError(
                "run capability does not bind this sandbox/attempt "
                f"({capability.attempt_id}/{capability.sandbox_id} vs "
                f"{handle.attempt_id}/{handle.sandbox_id})"
            )
        handle.host_out_sequence += 1
        frame = frame_message(
            build_guest_message(
                message_id=f"host-capability-{handle.host_out_sequence}",
                attempt_id=handle.attempt_id,
                sandbox_id=handle.sandbox_id,
                sequence_number=handle.host_out_sequence,
                message_type=GuestMessageType.RUN_CAPABILITY_DELIVERED,
                sent_at=utc_now_ms(),
                payload={
                    "capability": capability.model_dump(mode="json"),
                    "capability_digest": capability.digest(),
                },
            )
        )
        try:
            self._send_guest_message(frame)
        except Exception as exc:  # noqa: BLE001 — transport failure aborts provision
            raise ProvisionError(
                f"capability delivery failed: {type(exc).__name__}: {exc}"
            ) from exc
        handle.capability_id = capability.capability_id
        handle.capability_digest = capability.digest()
        handle.capability_expires_at = capability.expires_at
        handle.host_evidence.append(
            {
                "event": "capability_delivered",
                "capability_id": capability.capability_id,
                "capability_digest": handle.capability_digest,
                "expires_at": capability.expires_at,
                "observed_at": utc_now_ms(),
            }
        )
        return handle.capability_digest

    def _await_guest_ready(
        self, handle: SandboxHandle, assignment: SandboxAssignmentV1
    ) -> None:
        import time

        if self._receive_guest_message is None:
            raise ProvisionError(
                "no guest transport configured; refusing to mark the VM ready "
                "without verified supervisor identity"
            )
        # The handle owns the session so the SAME strictly-ordered session
        # continues after ready (heartbeats, evidence manifests) — a fresh
        # session per phase would reject legitimate sequence numbers.
        session = handle.session or GuestProtocolSession(
            attempt_id=assignment.attempt_id, sandbox_id=assignment.sandbox_id
        )
        handle.session = session
        deadline = time.monotonic() + self._guest_ready_timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProvisionError(
                    f"guest did not send guest_ready within "
                    f"{self._guest_ready_timeout}s"
                )
            frame = self._receive_guest_message(timeout=min(remaining, 5.0))
            if frame is None:
                continue
            message = session.receive(frame)
            if message.message_type is GuestMessageType.GUEST_READY:
                handle.host_evidence.append(
                    {
                        "event": "guest_ready_verified",
                        "message_id": message.message_id,
                        "sequence": message.sequence_number,
                        "observed_at": utc_now_ms(),
                    }
                )
                return
            # Any other message before guest_ready is out of protocol.
            raise ProvisionError(
                f"first guest message was {message.message_type.value}, "
                "not guest_ready"
            )

    def receive_guest_frame(self, handle: SandboxHandle, timeout: float):
        """Receive ONE post-ready guest frame on the handle's session.

        Used by the slice runner for heartbeats / evidence manifests.
        Returns the parsed GuestMessageV1, or None on timeout. Protocol
        violations (replay, gap, wrong binding) raise — fail closed.
        """
        if self._receive_guest_message is None:
            raise ProvisionError("no guest transport configured")
        if handle.session is None:
            raise ProvisionError("sandbox has no protocol session")
        frame = self._receive_guest_message(timeout=timeout)
        if frame is None:
            return None
        return handle.session.receive(frame)

    # -- Status / shutdown / terminate ------------------------------------

    def get_sandbox_status(self, handle: SandboxHandle) -> dict:
        return {
            "sandbox_id": handle.sandbox_id,
            "state": handle.state,
            "vmm_running": self._client.is_running(handle.sandbox_id),
            "shutdown_requested_at": handle.shutdown_requested_at,
            "shutdown_deadline": handle.shutdown_deadline,
        }

    def request_graceful_shutdown(self, handle: SandboxHandle, deadline_seconds: int = 30) -> dict:
        """Request (not prove) a graceful stop; the deadline is enforced.

        Sends SHUTDOWN_REQUESTED over the host→guest transport (defect fix:
        the request previously only recorded timestamps — the guest never
        learned). A transport failure is recorded and re-raised: an
        unnotified guest must be force-terminated at the deadline, never
        assumed to have stopped.
        """
        handle.shutdown_requested_at = utc_now_ms()
        from datetime import datetime, timedelta, timezone

        deadline_dt = datetime.now(timezone.utc) + timedelta(seconds=deadline_seconds)
        handle.shutdown_deadline = deadline_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        result = {
            "requested_at": handle.shutdown_requested_at,
            "deadline": handle.shutdown_deadline,
            "guest_notified": False,
        }
        if self._send_guest_message is None:
            handle.host_evidence.append(
                {
                    "event": "shutdown_not_sent",
                    "detail": "no guest transport configured",
                    "observed_at": utc_now_ms(),
                }
            )
            return result
        handle.host_out_sequence += 1
        frame = frame_message(
            build_guest_message(
                message_id=f"host-shutdown-{handle.host_out_sequence}",
                attempt_id=handle.attempt_id,
                sandbox_id=handle.sandbox_id,
                sequence_number=handle.host_out_sequence,
                message_type=GuestMessageType.SHUTDOWN_REQUESTED,
                sent_at=utc_now_ms(),
                payload={"deadline": handle.shutdown_deadline},
            )
        )
        try:
            self._send_guest_message(frame)
        except Exception as exc:  # noqa: BLE001 — recorded, then fail the caller
            handle.host_evidence.append(
                {
                    "event": "shutdown_send_failed",
                    "detail": f"{type(exc).__name__}: {exc}",
                    "observed_at": utc_now_ms(),
                }
            )
            raise
        result["guest_notified"] = True
        handle.host_evidence.append(
            {
                "event": "shutdown_requested_sent",
                "message_id": f"host-shutdown-{handle.host_out_sequence}",
                "deadline": handle.shutdown_deadline,
                "observed_at": utc_now_ms(),
            }
        )
        return result

    def force_terminate(self, handle: SandboxHandle) -> None:
        self._client.stop(handle.sandbox_id)
        handle.state = SandboxState.TERMINATED

    # -- Evidence + teardown ----------------------------------------------

    def collect_host_lifecycle_evidence(self, handle: SandboxHandle) -> list:
        """Trusted host observations (guest events are NOT trusted)."""
        return list(handle.host_evidence) + [
            {
                "event": "host_observation",
                "sandbox_id": handle.sandbox_id,
                "vmm_running": self._client.is_running(handle.sandbox_id),
                "observed_at": utc_now_ms(),
            }
        ]

    def _remove_scratch(self, sandbox_id: str, scratch_path: str) -> None:
        from pathlib import Path

        try:
            Path(scratch_path).unlink()
        except OSError:
            pass

    def verify_resources_removed(self, handle: SandboxHandle) -> TeardownVerificationV1:
        """Independent teardown verification -> the four-outcome record."""
        checks = self._probes.run(handle, self._client)
        all_passed = all(check.passed for check in checks)
        any_performed = any(
            check.detail is None or "unperformable" not in (check.detail or "")
            for check in checks
        )
        if all_passed and any_performed:
            outcome = TrustVerificationStatus.VERIFIED_CLEAN
        elif any_performed:
            outcome = TrustVerificationStatus.VERIFICATION_FAILED
        else:
            outcome = TrustVerificationStatus.UNKNOWN
        verification = TeardownVerificationV1(
            verification_id=f"tdv-{uuid.uuid4().hex[:12]}",
            outcome=outcome,
            verifier=ProducerIdentityV1(
                component=ProducerComponent.HOST_WORKER,
                instance_id=f"host-{self._pinned.jailer_version or 'unknown'}",
                version="0.1.0",
            ),
            checks=tuple(checks),
            observed_at=utc_now_ms(),
        )
        # Persist on the handle so a slice report can surface teardown
        # trust even when the caller that triggered verification failed.
        handle.last_teardown = verification
        return verification

    def destroy_sandbox(self, handle: SandboxHandle) -> TeardownVerificationV1:
        """Terminate, remove managed resources, then verify independently."""
        self._client.stop(handle.sandbox_id)
        handle.state = SandboxState.TERMINATED
        # Close the host transport BEFORE verification: the listen socket
        # file is sandbox-scoped state, and the sockets probe must observe
        # it gone (the runner owns the channel; we own the ordering).
        if self._close_guest_transport is not None:
            try:
                self._close_guest_transport()
            except Exception:  # noqa: BLE001 — close is best effort; probe decides
                pass
        if handle.scratch_disk_path:
            self._remove_scratch(handle.sandbox_id, handle.scratch_disk_path)
        # Egress teardown: the table that gated the run must go with the run.
        if handle.network_applied:
            if self._remove_network is None:
                handle.network_removal = (
                    "applied but no removal transport configured"
                )
            else:
                try:
                    self._remove_network(handle.sandbox_id)
                    handle.network_removal = "removed"
                except Exception as exc:  # noqa: BLE001 — probe fails closed
                    handle.network_removal = (
                        f"removal failed: {type(exc).__name__}: {exc}"
                    )
        else:
            handle.network_removal = "not applied"
        return self.verify_resources_removed(handle)
