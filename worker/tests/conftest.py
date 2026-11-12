"""Shared builders for the worker-host tests, exposed as fixtures."""

from __future__ import annotations

import uuid

import pytest

from workflo_schema.contracts.common import utc_now_ms
from workflo_schema.contracts.runspec import (
    AllowedDestinationV1,
    CapabilityId,
    NetworkPolicySpecV1,
    NetworkProtocol,
)

from workflo_worker_host.admission import PinnedRuntime, WorkerCapabilities
from workflo_worker_host.assignment import (
    GuestImageV1,
    ResourceLimitsV1,
    SandboxAssignmentV1,
)

D1 = "sha256:" + "ab" * 32
D2 = "sha256:" + "cd" * 32
KERNEL_SHA = "sha256:" + "11" * 32
ROOTFS_SHA = "sha256:" + "22" * 32


def _make_assignment(**overrides) -> SandboxAssignmentV1:
    values = {
        "assignment_id": f"asg-{uuid.uuid4().hex[:8]}",
        "run_id": "run-1",
        "attempt_id": "attempt-1",
        "sandbox_id": f"sbx-{uuid.uuid4().hex[:8]}",
        "policy_digest": D1,
        "runtime_image_digest": D2,
        "guest_image": GuestImageV1(
            kernel_path="/srv/images/vmlinux.bin",
            kernel_sha256=KERNEL_SHA,
            rootfs_path="/srv/images/rootfs.ext4",
            rootfs_sha256=ROOTFS_SHA,
        ),
        "resource_limits": ResourceLimitsV1(
            vcpus=2, memory_mib=2048, disk_mib=10240, wall_clock_seconds=1800
        ),
        "network_policy": NetworkPolicySpecV1(),
        "capabilities": (CapabilityId.TESTS_EXECUTE, CapabilityId.EVIDENCE_SUBMIT),
        "issued_by": "control-plane-1",
        "issued_at": utc_now_ms(),
    }
    values.update(overrides)
    return SandboxAssignmentV1(**values)


def _make_pinned(**overrides) -> PinnedRuntime:
    values = {
        "firecracker_version": "v1.7.0",
        "jailer_version": "v1.7.0",
        "firecracker_path": "/usr/local/bin/firecracker",
        "jailer_path": "/usr/local/bin/jailer",
        "guest_images": {
            KERNEL_SHA: "/srv/images/vmlinux.bin",
            ROOTFS_SHA: "/srv/images/rootfs.ext4",
        },
    }
    values.update(overrides)
    return PinnedRuntime(**values)


def _make_capabilities(**overrides) -> WorkerCapabilities:
    values = {
        "platform": "Linux",
        "machine": "x86_64",
        "kernel_release": "6.8.0",
        "kvm_available": True,
        "kvm_unavailable_reason": None,
        "firecracker_path": "/usr/local/bin/firecracker",
        "firecracker_version": "Firecracker v1.7.0",
        "jailer_path": "/usr/local/bin/jailer",
        "jailer_version": "v1.7.0",
        "guest_images": {
            KERNEL_SHA: "/srv/images/vmlinux.bin",
            ROOTFS_SHA: "/srv/images/rootfs.ext4",
        },
        "available_vcpus": 16,
        "available_memory_mib": 32768,
        "available_disk_mib": 204800,
    }
    values.update(overrides)
    return WorkerCapabilities(**values)


def _allow_destination(host: str = "8.8.8.8", port: int = 53) -> NetworkPolicySpecV1:
    return NetworkPolicySpecV1(
        allowed_destinations=(
            AllowedDestinationV1(host=host, port=port, protocol=NetworkProtocol.UDP),
        )
    )


@pytest.fixture
def make_assignment():
    return _make_assignment


@pytest.fixture
def make_pinned():
    return _make_pinned


@pytest.fixture
def make_capabilities():
    return _make_capabilities


@pytest.fixture
def allow_destination():
    return _allow_destination
