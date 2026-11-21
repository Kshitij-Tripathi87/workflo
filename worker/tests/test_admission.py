"""Worker admission / eligibility tests — fail-closed, no fallback."""

from __future__ import annotations

from workflo_worker_host.admission import check_eligibility


def test_fully_qualified_host_is_eligible(make_assignment, make_pinned, make_capabilities):
    blockers = check_eligibility(
        make_capabilities(), make_assignment(), make_pinned()
    )
    assert blockers == []


def test_non_linux_platform_blocks(make_assignment, make_pinned, make_capabilities):
    caps = make_capabilities(platform="Windows", kvm_available=False,
                             kvm_unavailable_reason="not linux")
    blockers = check_eligibility(caps, make_assignment(), make_pinned())
    assert any("not a supported secure execution host" in b for b in blockers)
    assert any("KVM unavailable" in b for b in blockers)


def test_missing_kvm_blocks_and_names_no_fallback(make_assignment, make_pinned, make_capabilities):
    caps = make_capabilities(
        kvm_available=False, kvm_unavailable_reason="/dev/kvm does not exist"
    )
    blockers = check_eligibility(caps, make_assignment(), make_pinned())
    assert any("no fallback backend is permitted" in b for b in blockers)


def test_firecracker_version_mismatch_blocks(make_assignment, make_pinned, make_capabilities):
    caps = make_capabilities(firecracker_version="Firecracker v1.6.0")
    blockers = check_eligibility(caps, make_assignment(), make_pinned())
    assert any("Firecracker version mismatch" in b for b in blockers)


def test_jailer_version_mismatch_blocks(make_assignment, make_pinned, make_capabilities):
    caps = make_capabilities(jailer_version="v1.5.0")
    blockers = check_eligibility(caps, make_assignment(), make_pinned())
    assert any("jailer version mismatch" in b for b in blockers)


def test_missing_firecracker_binary_blocks(make_assignment, make_pinned, make_capabilities):
    caps = make_capabilities(firecracker_version=None)
    blockers = check_eligibility(caps, make_assignment(), make_pinned())
    assert any("Firecracker version mismatch" in b for b in blockers)


def test_capacity_shortage_blocks_each_resource(make_assignment, make_pinned, make_capabilities):
    caps = make_capabilities(available_vcpus=1, available_memory_mib=512, available_disk_mib=1024)
    blockers = check_eligibility(caps, make_assignment(), make_pinned())
    assert any("insufficient vCPUs" in b for b in blockers)
    assert any("insufficient memory" in b for b in blockers)
    assert any("insufficient disk" in b for b in blockers)


def test_unapproved_guest_image_blocks(make_assignment, make_pinned, make_capabilities):
    caps = make_capabilities(guest_images={})
    blockers = check_eligibility(caps, make_assignment(), make_pinned())
    assert any("guest kernel" in b for b in blockers)
    assert any("guest rootfs" in b for b in blockers)


def test_unhealthy_host_blocks(make_assignment, make_pinned, make_capabilities):
    caps = make_capabilities(healthy=False)
    blockers = check_eligibility(caps, make_assignment(), make_pinned())
    assert any("health check failed" in b for b in blockers)


def test_kvm_probe_device_branch_never_raises(monkeypatch):
    """Regression: _kvm_available() called PosixPath.is_device() — no such
    pathlib API — and crashed with AttributeError on ANY host where
    /dev/kvm exists (e.g. CI runners). The device branch must return an
    honest verdict instead of raising."""
    from pathlib import Path

    from workflo_worker_host.admission import _kvm_available

    # Force the device-exists branch; stat still fails (device absent in
    # this environment) -> is_char_device() must degrade to False.
    monkeypatch.setattr(Path, "exists", lambda self: True)
    ok, reason = _kvm_available()
    assert ok is False
    assert isinstance(reason, str) and reason


def test_kvm_probe_absent_device_is_honest():
    from pathlib import Path

    from workflo_worker_host.admission import _kvm_available

    if Path("/dev/kvm").exists():
        import os

        ok, reason = _kvm_available()
        assert ok in (True, False)
        assert (reason is None) is ok
    else:
        ok, reason = _kvm_available()
        assert ok is False
        assert "does not exist" in reason


def test_full_probe_never_raises():
    from workflo_worker_host.admission import probe_capabilities

    caps = probe_capabilities()
    assert caps.kvm_available in (True, False)
    assert (caps.kvm_unavailable_reason is None) is caps.kvm_available
