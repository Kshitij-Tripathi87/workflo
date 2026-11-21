"""Gate B integration (Linux/KVM only) — real microVM proof.

These tests are the seed of Gate B (brief §18): boot a pinned Firecracker
microVM on real KVM, prove forbidden host access fails, enforce resources,
verify teardown. They are SKIPPED — with an explicit reason — on any host
without Linux+KVM; a skip is a documented non-proof, never a pass.

Full boot evidence requires the pinned release artifacts (Firecracker/
jailer binaries, guest kernel, rootfs) supplied by the release pipeline;
until those exist, this file documents and probes what CAN be probed
honestly on the current host.
"""

from __future__ import annotations

import platform

import pytest

from workflo_worker_host.admission import probe_capabilities

pytestmark = [
    pytest.mark.skipif(
        platform.system() != "Linux",
        reason="secure execution hosts are Linux/KVM only (ADR-0022); "
        "this skip is a documented non-proof, never a pass",
    ),
]


def _require_kvm():
    from pathlib import Path

    if not Path("/dev/kvm").exists():
        pytest.skip("/dev/kvm not present on this host (documented non-proof)")


def test_probe_reports_kvm_honestly():
    _require_kvm()
    caps = probe_capabilities()
    assert caps.kvm_available is True
    assert caps.kvm_unavailable_reason is None


def test_probe_reports_pinned_toolchain_when_present():
    _require_kvm()
    caps = probe_capabilities()
    # The probe must never fabricate versions: absent binaries are None.
    if caps.firecracker_path is None:
        pytest.skip("Firecracker binary not installed on this host")
    assert caps.firecracker_version is not None
    assert caps.jailer_version is not None


# ---------------------------------------------------------------------------
# Full slice e2e: one real guest, fixed workload, host evidence, verified
# termination. Requires the complete KVM toolchain + prepared artifacts —
# every missing piece is an explicit skip (documented non-proof).
# ---------------------------------------------------------------------------


def _require_slice_env():
    """Return (kernel_path, rootfs_path) or skip with the missing piece."""
    import os
    import shutil
    from pathlib import Path

    if not Path("/dev/kvm").exists():
        pytest.skip("/dev/kvm not present (documented non-proof)")
    if shutil.which("nft") is None:
        pytest.skip("nft not installed — egress cannot be enforced (non-proof)")
    if os.geteuid() != 0:
        pytest.skip("slice e2e needs root (jailer chroot + nftables)")
    kernel = os.environ.get("WORKFLO_SLICE_KERNEL")
    rootfs = os.environ.get("WORKFLO_SLICE_ROOTFS")
    if not kernel or not rootfs:
        pytest.skip(
            "WORKFLO_SLICE_KERNEL/WORKFLO_SLICE_ROOTFS not set — pinned "
            "guest images required (documented non-proof)"
        )
    for path in (kernel, rootfs):
        if not Path(path).exists():
            pytest.skip(f"guest image missing: {path} (documented non-proof)")
    # The rootfs must contain the guest runtime (python + workflo_worker_host).
    # The provision script builds it; without it the guest cannot dial in.
    if os.environ.get("WORKFLO_SLICE_ROOTFS_READY") != "1":
        pytest.skip(
            "rootfs not confirmed to contain the guest runtime "
            "(set WORKFLO_SLICE_ROOTFS_READY=1 after provisioning)"
        )
    return kernel, rootfs


def test_slice_end_to_end_on_kvm(tmp_path):
    """Real Firecracker boot + fixed workload + verified teardown.

    This is the Gate B slice proof: it runs ONLY on a provisioned KVM host
    with pinned artifacts. On any lesser host it skips — a skip is a
    documented non-proof, never a pass (ADR-0022: mocks do not satisfy
    Gate B).
    """
    from workflo_worker_host.admission import WorkerCapabilities, probe_capabilities
    from workflo_worker_host.assignment import (
        GuestImageV1,
        ResourceLimitsV1,
        SandboxAssignmentV1,
    )
    from workflo_worker_host.firecracker_client import JailerFirecrackerClient
    from workflo_worker_host.network import apply_nftables, remove_nftables
    from workflo_worker_host.slice import run_slice
    from workflo_schema.contracts.canonical import sha256_hex
    from workflo_schema.contracts.common import utc_now_ms
    from workflo_schema.contracts.runspec import NetworkPolicySpecV1
    from workflo_schema.contracts.outcomes import TrustVerificationStatus

    kernel_path, rootfs_path = _require_slice_env()

    caps = probe_capabilities()
    assert caps.kvm_available is True
    assert caps.firecracker_path and caps.jailer_path

    # Pin the images this run will use (digest allowlist — defect (e) fix:
    # the slice supplies guest_images; probe_capabilities alone returns {}).
    kernel_digest = "sha256:" + sha256_hex(open(kernel_path, "rb").read())
    rootfs_digest = "sha256:" + sha256_hex(open(rootfs_path, "rb").read())
    caps = WorkerCapabilities(**{**caps.__dict__})
    caps.guest_images = {
        kernel_digest.removeprefix("sha256:"): kernel_path,
        rootfs_digest.removeprefix("sha256:"): rootfs_path,
    }

    from workflo_worker_host.admission import PinnedRuntime

    pinned = PinnedRuntime(
        firecracker_version=caps.firecracker_version,
        jailer_version=caps.jailer_version,
        firecracker_path=caps.firecracker_path,
        jailer_path=caps.jailer_path,
        guest_images=dict(caps.guest_images),
    )

    sandbox_id = "sbx-e2e-slice"
    attempt_id = "attempt-e2e-slice"
    run_id = "run-e2e-slice"
    assignment = SandboxAssignmentV1(
        assignment_id="asg-e2e-slice",
        run_id=run_id,
        attempt_id=attempt_id,
        sandbox_id=sandbox_id,
        policy_digest="sha256:" + "ab" * 32,
        runtime_image_digest="sha256:" + "cd" * 32,
        guest_image=GuestImageV1(
            kernel_path=kernel_path,
            kernel_sha256=kernel_digest,
            rootfs_path=rootfs_path,
            rootfs_sha256=rootfs_digest,
        ),
        resource_limits=ResourceLimitsV1(
            vcpus=2, memory_mib=1024, disk_mib=512, wall_clock_seconds=120
        ),
        network_policy=NetworkPolicySpecV1(),
        capabilities=("tests.execute", "evidence.submit"),
        issued_by="e2e",
        issued_at=utc_now_ms(),
        signature="e2e-unsigned-allowed-by-flag",
    )

    client = JailerFirecrackerClient(
        pinned=pinned,
        chroot_base=str(tmp_path / "jailer"),
        work_dir=str(tmp_path / "vmm"),
        uid=0,
        gid=0,
        stop_grace_seconds=10.0,
    )

    # The guest image's init must run the guest runtime (main()); until the
    # rootfs is confirmed to contain it, this test skips above.
    report = run_slice(
        assignment=assignment,
        client=client,
        pinned=pinned,
        capabilities=caps,
        output_dir=tmp_path / "reports",
        apply_network=apply_nftables,
        remove_network=remove_nftables,
        require_signed_assignment=False,
        guest_ready_timeout_seconds=60,
        workload_timeout_seconds=60,
        shutdown_grace_seconds=15,
        scratch_dir=str(tmp_path / "scratch"),
        vsock_dir=str(tmp_path / "vsock"),
        uid=0,
        gid=0,
    )

    # The three axes must each be honest on real hardware.
    assert report.execution_status == "completed", report.error
    assert report.qa_status == "pass", report.workload_result
    assert report.trust_status == TrustVerificationStatus.VERIFIED_CLEAN.value
    assert report.termination in ("graceful", "forced")
    assert report.workload_result["ok"] is True
    # Serial log captured as host evidence.
    serial_entries = [
        e for e in report.host_evidence if e.get("event") == "vmm_lifecycle"
    ]
    assert serial_entries and serial_entries[0]["serial_log_sha256"]
    # Nothing left running.
    assert not client.is_running(sandbox_id)
