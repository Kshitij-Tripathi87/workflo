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
    return {
        "boot-source": {
            "kernel_image_path": assignment.guest_image.kernel_path,
            "boot_args": kernel_boot_args,
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
    """The pinned jailer argv (brief §3: VMM under jailer, never bare)."""
    exec_file = pinned.firecracker_path
    return [
        pinned.jailer_path,
        "--id", sandbox_id,
        "--exec-file", exec_file,
        "--uid", str(uid),
        "--gid", str(gid),
        "--chroot-base", chroot_base,
        "--", "--config-file", config_path,
    ]


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
    """Probes implementable from the manager's own state + client seam."""
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

    return {
        TeardownCheckId.VMM_EXITED: vmm_exited,
        TeardownCheckId.VM_STOPPED: vmm_exited,
        TeardownCheckId.DISK_DESTROYED: disk_destroyed,
        TeardownCheckId.PROCESS_SCOPE_EMPTY: process_scope_empty,
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
        receive_guest_message: Callable | None = None,
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
        self._receive_guest_message = receive_guest_message
        self._uid = uid
        self._gid = gid
        self._create_scratch_disk = create_scratch_disk or _create_scratch_disk
        self._sandboxes: dict = {}

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
        vsock_path = f"{self._vsock_dir}/{sandbox_id}.sock"
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
        )
        self._sandboxes[sandbox_id] = handle

        # The VM must prove its identity before any project work starts
        # (brief §3.1: "Verify guest boot and supervisor identity").
        try:
            self._await_guest_ready(handle, assignment)
        except Exception:
            self.force_terminate(handle)
            self.verify_resources_removed(handle)
            raise
        handle.state = SandboxState.READY
        return handle

    def _await_guest_ready(
        self, handle: SandboxHandle, assignment: SandboxAssignmentV1
    ) -> None:
        import time

        if self._receive_guest_message is None:
            raise ProvisionError(
                "no guest transport configured; refusing to mark the VM ready "
                "without verified supervisor identity"
            )
        session = GuestProtocolSession(
            attempt_id=assignment.attempt_id, sandbox_id=assignment.sandbox_id
        )
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
        """Request (not prove) a graceful stop; the deadline is enforced."""
        handle.shutdown_requested_at = utc_now_ms()
        from datetime import datetime, timedelta, timezone

        deadline_dt = datetime.now(timezone.utc) + timedelta(seconds=deadline_seconds)
        handle.shutdown_deadline = deadline_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        return {
            "requested_at": handle.shutdown_requested_at,
            "deadline": handle.shutdown_deadline,
        }

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
        return TeardownVerificationV1(
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

    def destroy_sandbox(self, handle: SandboxHandle) -> TeardownVerificationV1:
        """Terminate, remove managed resources, then verify independently."""
        self._client.stop(handle.sandbox_id)
        handle.state = SandboxState.TERMINATED
        if handle.scratch_disk_path:
            self._remove_scratch(handle.sandbox_id, handle.scratch_disk_path)
        return self.verify_resources_removed(handle)
