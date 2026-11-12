"""Worker admission: host eligibility probing (brief §8.4, §3.8).

A worker that lacks KVM, runs an unpinned Firecracker/jailer, lacks the
approved guest image, or cannot satisfy the assignment's resource limits is
INELIGIBLE. The run stays pending or fails with an explicit infrastructure
reason. There is no fallback: Docker and bwrap never substitute for the
microVM boundary (ADR-0022), and a failed admission check is never silent.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from workflo_schema.contracts.common import DigestString

from workflo_worker_host.assignment import SandboxAssignmentV1

__all__ = [
    "WorkerCapabilities",
    "PinnedRuntime",
    "HostProbeError",
    "probe_capabilities",
    "check_eligibility",
    "ELIGIBILITY_BLOCKERS",
]


@dataclass(frozen=True)
class PinnedRuntime:
    """The ONLY versions this worker may run (release-pinned)."""

    firecracker_version: str
    jailer_version: str
    firecracker_path: str
    jailer_path: str
    # Guest image allowlist: digest -> artifact path.
    guest_images: dict = field(default_factory=dict)


@dataclass
class WorkerCapabilities:
    """What this host honestly reports about itself."""

    platform: str
    machine: str
    kernel_release: str
    kvm_available: bool
    kvm_unavailable_reason: str | None
    firecracker_path: str | None
    firecracker_version: str | None
    jailer_path: str | None
    jailer_version: str | None
    guest_images: dict
    available_vcpus: int
    available_memory_mib: int
    available_disk_mib: int
    healthy: bool = True
    notes: list = field(default_factory=list)


class HostProbeError(RuntimeError):
    """The host could not be probed honestly; treat as ineligible."""


def _run_version(command: list) -> str | None:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or result.stderr.strip() or None


def _kvm_available() -> tuple:
    """Probe /dev/kvm honestly. Never assumes; a missing device is a fact."""
    kvm = Path("/dev/kvm")
    if not kvm.exists():
        return False, "/dev/kvm does not exist"
    if not kvm.is_device():
        return False, "/dev/kvm is not a character device"
    import os

    if not os.access(kvm, os.R_OK | os.W_OK):
        return False, "/dev/kvm is not rw-accessible to this service identity"
    return True, None


def probe_capabilities(
    *,
    reserved_vcpus: int = 0,
    reserved_memory_mib: int = 0,
    reserved_disk_mib: int = 0,
    total_memory_mib: int | None = None,
    total_disk_mib: int | None = None,
) -> WorkerCapabilities:
    """Probe the host for real. No value is ever assumed available."""
    system = platform.system()
    kvm_ok, kvm_reason = (
        _kvm_available() if system == "Linux" else (False, f"platform {system} is not a secure execution host (ADR-0022)")
    )

    fc_path = shutil.which("firecracker")
    jailer_path = shutil.which("jailer")
    fc_version = (
        _run_version([fc_path, "--version"]) if fc_path and system == "Linux" else None
    )
    jailer_version = (
        _run_version([jailer_path, "--version"])
        if jailer_path and system == "Linux"
        else None
    )

    try:
        import os

        cpu_count = os.cpu_count() or 1
        available_vcpus = max(0, cpu_count - reserved_vcpus)
        mem_mib = total_memory_mib
        if mem_mib is None:
            try:
                with open("/proc/meminfo", encoding="ascii") as handle:
                    for line in handle:
                        if line.startswith("MemTotal:"):
                            mem_mib = int(line.split()[1]) // 1024
                            break
            except OSError:
                mem_mib = 0
        disk_mib = total_disk_mib or 0
    except Exception as exc:  # noqa: BLE001 — probe failure is a fact
        raise HostProbeError(f"host probe failed: {type(exc).__name__}: {exc}") from exc

    return WorkerCapabilities(
        platform=system,
        machine=platform.machine(),
        kernel_release=platform.release(),
        kvm_available=kvm_ok,
        kvm_unavailable_reason=kvm_reason,
        firecracker_path=fc_path,
        firecracker_version=fc_version,
        jailer_path=jailer_path,
        jailer_version=jailer_version,
        guest_images={},
        available_vcpus=available_vcpus,
        available_memory_mib=max(0, (mem_mib or 0) - reserved_memory_mib),
        available_disk_mib=max(0, disk_mib - reserved_disk_mib),
    )


def _pin_version_matches(reported: str | None, pinned: str) -> bool:
    if not reported:
        return False
    # Firecracker prints e.g. "Firecracker v1.7.0"; jailer similar.
    return pinned in reported


def check_eligibility(
    caps: WorkerCapabilities,
    assignment: SandboxAssignmentV1,
    pinned: PinnedRuntime,
) -> list:
    """Return the list of blockers; EMPTY means eligible. Fail closed."""
    blockers: list = []
    if caps.platform != "Linux":
        blockers.append(
            f"platform {caps.platform} is not a supported secure execution host"
        )
    if not caps.kvm_available:
        blockers.append(
            f"KVM unavailable ({caps.kvm_unavailable_reason}); "
            "no fallback backend is permitted (ADR-0022)"
        )
    if not _pin_version_matches(caps.firecracker_version, pinned.firecracker_version):
        blockers.append(
            f"Firecracker version mismatch: reported {caps.firecracker_version!r}, "
            f"pinned {pinned.firecracker_version!r}"
        )
    if not _pin_version_matches(caps.jailer_version, pinned.jailer_version):
        blockers.append(
            f"jailer version mismatch: reported {caps.jailer_version!r}, "
            f"pinned {pinned.jailer_version!r}"
        )
    if not caps.healthy:
        blockers.append("host health check failed")

    limits = assignment.resource_limits
    if caps.available_vcpus < limits.vcpus:
        blockers.append(
            f"insufficient vCPUs: need {limits.vcpus}, have {caps.available_vcpus}"
        )
    if caps.available_memory_mib < limits.memory_mib:
        blockers.append(
            f"insufficient memory: need {limits.memory_mib} MiB, "
            f"have {caps.available_memory_mib} MiB"
        )
    if caps.available_disk_mib < limits.disk_mib:
        blockers.append(
            f"insufficient disk: need {limits.disk_mib} MiB, "
            f"have {caps.available_disk_mib} MiB"
        )

    kernel_digest_ok = assignment.guest_image.kernel_sha256 in caps.guest_images
    rootfs_digest_ok = assignment.guest_image.rootfs_sha256 in caps.guest_images
    if not kernel_digest_ok:
        blockers.append(
            f"guest kernel {assignment.guest_image.kernel_sha256} is not in the "
            "approved image allowlist"
        )
    if not rootfs_digest_ok:
        blockers.append(
            f"guest rootfs {assignment.guest_image.rootfs_sha256} is not in the "
            "approved image allowlist"
        )
    return blockers


# The blockers that gate release (manual §3.8): a worker missing ANY of
# these must not receive customer work. Exported for the doctor/gate tooling.
ELIGIBILITY_BLOCKERS: frozenset = frozenset(
    {
        "platform",
        "kvm",
        "firecracker_version",
        "jailer_version",
        "capacity",
        "guest_image",
        "health",
    }
)
