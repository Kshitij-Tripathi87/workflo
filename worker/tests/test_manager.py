"""Sandbox manager tests: fail-closed provisioning + teardown verification."""

from __future__ import annotations

import pytest

from workflo_schema.contracts.outcomes import TrustVerificationStatus
from workflo_schema.contracts.receipt import TeardownCheckId
from workflo_schema.contracts.common import utc_now_ms

from workflo_worker_host.manager import (
    ProvisionError,
    SandboxManager,
    SandboxState,
    build_jailer_argv,
    build_vm_config,
)
from workflo_worker_host.protocol import (
    GuestMessageType,
    build_guest_message,
    frame_message,
)


class FakeFirecrackerClient:
    def __init__(self, *, fail_start: Exception | None = None):
        self.started: list = []
        self.stopped: list = []
        self.running: set = set()
        self.fail_start = fail_start

    def start(self, sandbox_id, vm_config, argv):
        if self.fail_start is not None:
            raise self.fail_start
        self.started.append((sandbox_id, vm_config))
        self.running.add(sandbox_id)

    def stop(self, sandbox_id):
        self.stopped.append(sandbox_id)
        self.running.discard(sandbox_id)

    def is_running(self, sandbox_id):
        return sandbox_id in self.running


def _guest_ready_frames(assignment):
    frames = [
        frame_message(
            build_guest_message(
                message_id="msg-ready",
                attempt_id=assignment.attempt_id,
                sandbox_id=assignment.sandbox_id,
                sequence_number=1,
                message_type=GuestMessageType.GUEST_READY,
                sent_at=utc_now_ms(),
                payload={"supervisor_version": "0.1.0"},
            )
        )
    ]

    def receive(timeout: float = 1.0):
        if frames:
            return frames.pop(0)
        return None

    return receive


def _manager(
    client,
    assignment,
    *,
    make_pinned,
    make_capabilities,
    require_signed=False,
    probes=None,
    apply_network=None,
    receive=None,
    tmp_path=None,
    guest_ready_timeout=5,
):
    from pathlib import Path as _Path

    def fake_create_scratch(path: str, disk_mib: int) -> None:
        # Real creation (fallocate/ext4) is the Linux host's job; tests
        # only need the path to exist so cleanup checks are honest.
        _Path(path).write_bytes(b"")

    return SandboxManager(
        client=client,
        pinned=make_pinned(),
        capabilities=make_capabilities(),
        require_signed_assignment=require_signed,
        guest_ready_timeout_seconds=guest_ready_timeout,
        probes=probes,
        scratch_dir=str(tmp_path / "scratch") if tmp_path else "/tmp/wf-scratch",
        vsock_dir=str(tmp_path / "vsock") if tmp_path else "/tmp/wf-vsock",
        apply_network=apply_network,
        receive_guest_message=receive or _guest_ready_frames(assignment),
        create_scratch_disk=fake_create_scratch,
        uid=1000,
        gid=1000,
    )


def test_signed_assignment_required_in_production(
    make_assignment, make_pinned, make_capabilities, tmp_path
):
    manager = _manager(
        FakeFirecrackerClient(), make_assignment(), make_pinned=make_pinned,
        make_capabilities=make_capabilities, require_signed=True, tmp_path=tmp_path,
    )
    with pytest.raises(ProvisionError, match="unsigned assignment"):
        manager.provision_sandbox(make_assignment())


def test_ineligible_worker_never_starts_the_vmm(
    make_assignment, make_pinned, make_capabilities, tmp_path
):
    client = FakeFirecrackerClient()
    caps = make_capabilities(kvm_available=False, kvm_unavailable_reason="no /dev/kvm")
    manager = SandboxManager(
        client=client,
        pinned=make_pinned(),
        capabilities=caps,
        require_signed_assignment=False,
        scratch_dir=str(tmp_path / "scratch"),
        vsock_dir=str(tmp_path / "vsock"),
        apply_network=lambda ruleset: None,
        receive_guest_message=_guest_ready_frames(make_assignment()),
    )
    with pytest.raises(ProvisionError, match="ineligible"):
        manager.provision_sandbox(make_assignment())
    assert client.started == []


def test_network_enforcement_failure_blocks_the_vm(
    make_assignment, make_pinned, make_capabilities, tmp_path
):
    client = FakeFirecrackerClient()

    def broken_apply(ruleset):
        raise RuntimeError("nftables unavailable")

    manager = _manager(
        client, make_assignment(), make_pinned=make_pinned,
        make_capabilities=make_capabilities, apply_network=broken_apply,
        tmp_path=tmp_path,
    )
    with pytest.raises(ProvisionError, match="egress policy could not be enforced"):
        manager.provision_sandbox(make_assignment())
    assert client.started == []


def test_boot_failure_cleans_the_scratch_disk(
    make_assignment, make_pinned, make_capabilities, tmp_path
):
    client = FakeFirecrackerClient(fail_start=OSError("kvm run failed"))
    manager = _manager(
        client, make_assignment(), make_pinned=make_pinned,
        make_capabilities=make_capabilities, tmp_path=tmp_path,
    )
    with pytest.raises(ProvisionError, match="VMM failed to start"):
        manager.provision_sandbox(make_assignment())
    leftovers = list((tmp_path / "scratch").glob("*.img"))
    assert leftovers == []


def test_guest_ready_timeout_terminates_and_verifies(
    make_assignment, make_pinned, make_capabilities, tmp_path
):
    client = FakeFirecrackerClient()

    def silent(timeout: float = 1.0):
        return None

    manager = _manager(
        client, make_assignment(), make_pinned=make_pinned,
        make_capabilities=make_capabilities, receive=silent, tmp_path=tmp_path,
        guest_ready_timeout=1,
    )
    with pytest.raises(ProvisionError, match="guest_ready"):
        manager.provision_sandbox(make_assignment())
    # Fail-closed: the unproven VM was torn down and cleanup verified.
    assert client.stopped, "a VM that never proved identity must be terminated"


def test_happy_path_provision_marks_ready_and_binds_config(
    make_assignment, make_pinned, make_capabilities, tmp_path
):
    client = FakeFirecrackerClient()
    assignment = make_assignment()
    manager = _manager(
        client, assignment, make_pinned=make_pinned,
        make_capabilities=make_capabilities, tmp_path=tmp_path,
    )
    handle = manager.provision_sandbox(assignment)
    assert handle.state == SandboxState.READY
    assert client.started, "VMM must have been started"
    vm_config = client.started[0][1]
    assert vm_config["machine-config"]["vcpu_count"] == 2
    assert vm_config["machine-config"]["mem_size_mib"] == 2048
    assert vm_config["drives"][0]["is_read_only"] is True
    assert vm_config["drives"][1]["is_read_only"] is False
    assert vm_config["vsock"]["guest_cid"] >= 3
    evidence = manager.collect_host_lifecycle_evidence(handle)
    assert any(e.get("event") == "guest_ready_verified" for e in evidence)


def test_jailer_argv_uses_pinned_paths(make_pinned):
    argv = build_jailer_argv(
        make_pinned(),
        sandbox_id="sbx-1",
        config_path="/run/cfg.json",
        uid=1000,
        gid=1000,
    )
    assert argv[0] == "/usr/local/bin/jailer"
    assert "--exec-file" in argv and "/usr/local/bin/firecracker" in argv
    assert "--uid" in argv and "--gid" in argv
    assert argv[-2:] == ["--config-file", "/run/cfg.json"]


def test_graceful_shutdown_is_a_request_with_deadline(
    make_assignment, make_pinned, make_capabilities, tmp_path
):
    client = FakeFirecrackerClient()
    assignment = make_assignment()
    manager = _manager(
        client, assignment, make_pinned=make_pinned,
        make_capabilities=make_capabilities, tmp_path=tmp_path,
    )
    handle = manager.provision_sandbox(assignment)
    result = manager.request_graceful_shutdown(handle, deadline_seconds=30)
    assert result["deadline"] > result["requested_at"]
    # A request is not proof of termination (brief §5).
    assert client.is_running(handle.sandbox_id)


def test_destroy_produces_verified_clean_with_full_probes(
    make_assignment, make_pinned, make_capabilities, tmp_path
):
    client = FakeFirecrackerClient()
    assignment = make_assignment()
    # The manager's default probes cover VMM/disk/process scope; the
    # cgroups/netns/sockets/capabilities probes belong to the Linux host
    # integration — represented here by passing fakes so the full 8-check
    # contract is exercised. The real ones land with the host integration.
    from workflo_worker_host.manager import default_teardown_probes

    host_probes = {
        **default_teardown_probes(),
        TeardownCheckId.CGROUPS_REMOVED: (lambda handle, cl: (True, None)),
        TeardownCheckId.NETNS_REMOVED: (lambda handle, cl: (True, None)),
        TeardownCheckId.SOCKETS_CLOSED: (lambda handle, cl: (True, None)),
        TeardownCheckId.CAPABILITIES_EXPIRED: (lambda handle, cl: (True, None)),
    }
    manager = _manager(
        client, assignment, make_pinned=make_pinned,
        make_capabilities=make_capabilities, probes=host_probes, tmp_path=tmp_path,
    )
    handle = manager.provision_sandbox(assignment)
    verification = manager.destroy_sandbox(handle)
    assert verification.outcome is TrustVerificationStatus.VERIFIED_CLEAN
    assert all(check.passed for check in verification.checks)
    assert {c.check_id for c in verification.checks} == set(TeardownCheckId)


def test_failing_probe_produces_verification_failed(
    make_assignment, make_pinned, make_capabilities, tmp_path
):
    client = FakeFirecrackerClient()
    assignment = make_assignment()
    probes = {
        TeardownCheckId.VMM_EXITED: (lambda handle, cl: (True, None)),
        TeardownCheckId.VM_STOPPED: (lambda handle, cl: (True, None)),
        TeardownCheckId.CGROUPS_REMOVED: (lambda handle, cl: (False, "cgroup still present")),
        TeardownCheckId.NETNS_REMOVED: (lambda handle, cl: (True, None)),
        TeardownCheckId.DISK_DESTROYED: (lambda handle, cl: (True, None)),
        TeardownCheckId.SOCKETS_CLOSED: (lambda handle, cl: (True, None)),
        TeardownCheckId.CAPABILITIES_EXPIRED: (lambda handle, cl: (True, None)),
        TeardownCheckId.PROCESS_SCOPE_EMPTY: (lambda handle, cl: (True, None)),
    }
    manager = _manager(
        client, assignment, make_pinned=make_pinned,
        make_capabilities=make_capabilities, probes=probes, tmp_path=tmp_path,
    )
    handle = manager.provision_sandbox(assignment)
    verification = manager.destroy_sandbox(handle)
    assert verification.outcome is TrustVerificationStatus.VERIFICATION_FAILED


def test_raising_probe_fails_closed(
    make_assignment, make_pinned, make_capabilities, tmp_path
):
    client = FakeFirecrackerClient()
    assignment = make_assignment()

    def broken(handle, cl):
        raise RuntimeError("probe crashed")

    probes = {TeardownCheckId.VMM_EXITED: broken}
    manager = _manager(
        client, assignment, make_pinned=make_pinned,
        make_capabilities=make_capabilities, probes=probes, tmp_path=tmp_path,
    )
    handle = manager.provision_sandbox(assignment)
    verification = manager.destroy_sandbox(handle)
    assert verification.outcome is TrustVerificationStatus.VERIFICATION_FAILED
    vmm_check = next(c for c in verification.checks if c.check_id is TeardownCheckId.VMM_EXITED)
    assert vmm_check.passed is False
    assert "probe crashed" in (vmm_check.detail or "")


def test_no_probes_at_all_is_unknown_not_clean(
    make_assignment, make_pinned, make_capabilities, tmp_path
):
    client = FakeFirecrackerClient()
    assignment = make_assignment()
    manager = _manager(
        client, assignment, make_pinned=make_pinned,
        make_capabilities=make_capabilities, probes={}, tmp_path=tmp_path,
    )
    handle = manager.provision_sandbox(assignment)
    verification = manager.destroy_sandbox(handle)
    assert verification.outcome is TrustVerificationStatus.UNKNOWN
