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
