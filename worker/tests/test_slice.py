"""End-to-end slice test: real channel, real guest runtime, fake VMM.

This is the slice's flagship integration test. It wires together every
real component except Firecracker itself (no KVM here):

- ``run_slice`` orchestrates provision → capability → ready → workload →
  manifest → shutdown → destroy → report;
- the host channel is a REAL AF_UNIX listener (what Firecracker bridges
  guest AF_VSOCK onto);
- the "guest" is a REAL thread speaking the actual ``guest_runtime``
  over a socket — the same code that runs inside the microVM;
- the VMM client is a fake (records lifecycle; no boot), and network
  apply/remove are recording fakes (no nft in this environment).

What this proves without KVM: the protocol loop, capability gating,
digest-verified manifest → QA derivation, graceful/forced termination
selection, network teardown wiring, teardown verification, and that a
report is always written with three independent status axes.
"""

from __future__ import annotations

import json
import socket
import threading
import time

import pytest
from workflo_schema.contracts.outcomes import TrustVerificationStatus
from workflo_schema.contracts.receipt import TeardownCheckId
from workflo_worker_host.guest_runtime import run_guest_slice
from workflo_worker_host.slice import SliceQaStatus, run_slice
from workflo_worker_host.vsock_channel import (
    HOST_CID,  # noqa: F401 — documented guest-side constant
    VSOCK_SUPERVISOR_PORT,
    recv_frame,
    send_frame,
)


class FakeVmm:
    """Lifecycle-only VMM: no boot, stops on demand (or never)."""

    def __init__(self):
        self.started: list = []
        self.stopped: list = []
        self.running: set = set()
        self._lock = threading.Lock()

    def start(self, sandbox_id, vm_config, argv):
        self.started.append((sandbox_id, vm_config))
        with self._lock:
            self.running.add(sandbox_id)

    def stop(self, sandbox_id):
        self.stopped.append(sandbox_id)
        with self._lock:
            self.running.discard(sandbox_id)

    def is_running(self, sandbox_id):
        with self._lock:
            return sandbox_id in self.running

    def simulate_guest_poweroff(self, sandbox_id):
        """What happens when the guest acts on SHUTDOWN_REQUESTED."""
        with self._lock:
            self.running.discard(sandbox_id)


def _guest_thread(
    listen_path: str,
    *,
    attempt_id: str,
    sandbox_id: str,
    workspace: str,
    ready: threading.Event,
    result: dict,
    on_done=None,
):
    """Simulated guest: connect to the host channel, run the real runtime."""
    try:
        deadline = time.monotonic() + 10.0
        sock = None
        while True:
            try:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.settimeout(1.0)
                sock.connect(listen_path)
                break
            except (FileNotFoundError, ConnectionRefusedError):
                if sock:
                    sock.close()
                if time.monotonic() >= deadline:
                    raise RuntimeError("guest could not reach host channel")
                time.sleep(0.02)

        ready.set()

        class _Transport:
            def send(self, frame: bytes) -> None:
                send_frame(sock, frame)

            def receive(self, *, timeout: float):
                sock.settimeout(timeout)
                return recv_frame(sock, timeout=timeout)

        outcome = run_guest_slice(
            transport=_Transport(),
            cmdline=(
                f"console=ttyS0 reboot=k panic=1 workflo.attempt_id={attempt_id} "
                f"workflo.sandbox_id={sandbox_id}"
            ),
            workspace=workspace,
            capability_timeout_seconds=10.0,
            shutdown_timeout_seconds=10.0,
        )
        result["status"] = outcome.status
        result["detail"] = outcome.detail
        result["workload"] = outcome.workload
    except Exception as exc:  # noqa: BLE001 — surfaced to assertions
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            sock.close()
        except Exception:  # noqa: BLE001
            pass
        # Models the guest acting on shutdown: init exits, kernel reboots
        # (reboot=k panic=1), and the Firecracker VM goes away.
        if on_done is not None:
            on_done()


@pytest.fixture
def slice_env(tmp_path, make_assignment, make_pinned, make_capabilities):
    assignment = make_assignment()
    pinned = make_pinned()
    caps = make_capabilities()

    network_calls = {"applied": [], "removed": []}

    def apply_network(ruleset: str) -> None:
        network_calls["applied"].append(ruleset)

    def remove_network(sandbox_id: str) -> None:
        network_calls["removed"].append(sandbox_id)

    vmm = FakeVmm()
    output_dir = tmp_path / "reports"
    guest_result: dict = {}
    guest_ready = threading.Event()

    listen_path = str(
        tmp_path / "vsock" / f"{assignment.sandbox_id}.sock_{VSOCK_SUPERVISOR_PORT}"
    )

    def start_guest():
        thread = threading.Thread(
            target=_guest_thread,
            kwargs={
                "listen_path": listen_path,
                "attempt_id": assignment.attempt_id,
                "sandbox_id": assignment.sandbox_id,
                "workspace": str(tmp_path / "guest-workspace"),
                "ready": guest_ready,
                "result": guest_result,
                "on_done": lambda: vmm.simulate_guest_poweroff(
                    assignment.sandbox_id
                ),
            },
            daemon=True,
        )
        thread.start()
        return thread

    return {
        "assignment": assignment,
        "pinned": pinned,
        "caps": caps,
        "vmm": vmm,
        "output_dir": output_dir,
        "apply_network": apply_network,
        "remove_network": remove_network,
        "network_calls": network_calls,
        "guest_result": guest_result,
        "start_guest": start_guest,
        "listen_path": listen_path,
        "tmp_path": tmp_path,
    }


def _run(env, **overrides):
    kwargs = dict(
        assignment=env["assignment"],
        client=env["vmm"],
        pinned=env["pinned"],
        capabilities=env["caps"],
        output_dir=env["output_dir"],
        apply_network=env["apply_network"],
        remove_network=env["remove_network"],
        require_signed_assignment=False,
        guest_ready_timeout_seconds=10,
        workload_timeout_seconds=10,
        shutdown_grace_seconds=2,
        scratch_dir=str(env["tmp_path"] / "scratch"),
        vsock_dir=str(env["tmp_path"] / "vsock"),
        uid=1000,
        gid=1000,
    )
    kwargs.update(overrides)
    return run_slice(**kwargs)


def test_full_slice_pass_writes_report_with_three_axes(slice_env):
    env = slice_env
    # The "VM" boots first and dials the host channel — in production the
    # Firecracker guest does this; capability delivery waits on accept.
    guest_thread = env["start_guest"]()

    report = _run(env)

    guest_thread.join(timeout=15.0)
    # The guest ran the REAL runtime: capability → ready → workload →
    # manifest → shutdown, and reported completion.
    assert env["guest_result"].get("status") == "completed", env["guest_result"]
    assert env["guest_result"]["workload"]["ok"] is True

    # Three independent axes, each honest.
    assert report.execution_status == "completed"
    assert report.qa_status == SliceQaStatus.PASS
    assert report.trust_status == TrustVerificationStatus.VERIFIED_CLEAN.value

    # The VMM was started, network applied AND removed, teardown verified.
    assert env["vmm"].started, "VMM must have been started"
    assert env["vmm"].stopped, "VMM must have been stopped"
    assert env["network_calls"]["applied"], "egress policy must be applied"
    assert env["network_calls"]["removed"] == [env["assignment"].sandbox_id]
    assert report.termination in ("graceful", "forced")

    # Workload result travels from the verified manifest, not a claim.
    assert report.workload_result["ok"] is True
    assert any(
        c["name"] == "workspace_marker" for c in report.workload_result["checks"]
    )

    # Report is persisted and reloadable with extra=forbid intact.
    files = list(env["output_dir"].glob("slice-report-*.json"))
    assert len(files) == 1
    on_disk = json.loads(files[0].read_text())
    assert on_disk["execution_status"] == "completed"
    assert on_disk["qa_status"] == "pass"
    assert on_disk["trust_status"] == "verified_clean"
    assert on_disk["slice_id"] == report.slice_id
    # Host evidence includes the capability delivery + ready verification.
    events = {e.get("event") for e in report.host_evidence}
    assert "capability_delivered" in events
    assert "guest_ready_verified" in events


def test_slice_provision_failure_still_writes_report(slice_env):
    env = slice_env
    # No guest thread at all: capability delivery blocks on accept until
    # connect_timeout, then provision fails closed.
    from workflo_worker_host.vsock_channel import HostVsockChannel

    def fast_factory(path):
        return HostVsockChannel(path, connect_timeout=0.3)

    report = _run(env, channel_factory=fast_factory, workload_timeout_seconds=1)

    assert report.execution_status == "provision_failed"
    assert report.qa_status == SliceQaStatus.NOT_RUN
    # Trust reflects teardown of whatever was created (or unknown).
    assert report.trust_status in {
        TrustVerificationStatus.VERIFIED_CLEAN.value,
        TrustVerificationStatus.VERIFICATION_FAILED.value,
        TrustVerificationStatus.UNKNOWN.value,
        TrustVerificationStatus.CLEANUP_INCOMPLETE.value,
    }
    assert report.error
    # A report exists even though the slice failed.
    files = list(env["output_dir"].glob("slice-report-*.json"))
    assert len(files) == 1
    # The failed attempt never left the VMM running.
    assert not env["vmm"].running


def test_slice_manifest_digest_mismatch_is_protocol_violation(slice_env, monkeypatch):
    env = slice_env

    # Intercept manifest submission and corrupt the digest — the host
    # must refuse to derive QA from a manifest whose digest fails
    # re-derivation. Only the bad frame is emitted (no correct original).
    import workflo_worker_host.guest_supervisor as gs
    from workflo_schema.contracts.canonical import digest_of
    from workflo_schema.contracts.common import SCHEMA_VERSION, utc_now_ms
    from workflo_worker_host.protocol import (
        GuestMessageType,
        build_guest_message,
        frame_message,
    )

    def tampered(self, artifacts, *, workload_result=None):
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "attempt_id": self._capability.attempt_id,
            "sandbox_id": self._capability.sandbox_id,
            "capability_digest": self._capability.digest(),
            "policy_digest": self._capability.policy_digest,
            "artifacts": artifacts,
            "built_at": utc_now_ms(),
        }
        if workload_result is not None:
            manifest["workload_result"] = workload_result
        entry = {
            "manifest": manifest,
            "manifest_digest": digest_of(manifest),
        }
        self.evidence_manifests.append(entry)
        self._sequence += 1
        message = build_guest_message(
            message_id=f"guest-{self._sequence:08d}",
            attempt_id=self._capability.attempt_id,
            sandbox_id=self._capability.sandbox_id,
            sequence_number=self._sequence,
            message_type=GuestMessageType.EVIDENCE_MANIFEST_SUBMITTED,
            sent_at=utc_now_ms(),
            payload={
                "manifest_digest": "sha256:" + "00" * 32,  # wrong on purpose
                "manifest": manifest,
            },
        )
        self._send(frame_message(message))
        return entry

    monkeypatch.setattr(gs.GuestSupervisor, "build_evidence_manifest", tampered)

    guest_thread = env["start_guest"]()
    report = _run(env)
    guest_thread.join(timeout=15.0)

    assert report.execution_status == "protocol_violation"
    assert report.qa_status == SliceQaStatus.NOT_RUN
    assert report.error and "digest" in report.error
    # VMM still torn down despite the violation.
    assert not env["vmm"].running


def test_slice_guest_failure_axis_is_independent(slice_env, monkeypatch):
    env = slice_env

    # Make the workload fail → qa=fail but execution still completes.
    import workflo_worker_host.guest_runtime as gr

    def failing_workload(workspace):
        return {
            "workload_id": "workflo-slice-workload-v1",
            "checks": [{"name": "workspace_marker", "ok": False, "detail": "boom"}],
            "ok": False,
            "completed_at": "2026-01-01T00:00:00.000Z",
        }

    monkeypatch.setattr(gr, "run_fixed_workload", failing_workload)

    guest_thread = env["start_guest"]()
    report = _run(env)
    guest_thread.join(timeout=15.0)

    # Execution completed (protocol loop fine) but QA failed — the axes
    # must not be collapsed into one status.
    assert report.execution_status == "completed"
    assert report.qa_status == SliceQaStatus.FAIL
    assert report.workload_result["ok"] is False
    assert report.trust_status == TrustVerificationStatus.VERIFIED_CLEAN.value


def test_slice_teardown_failure_is_visible_in_trust(slice_env):
    env = slice_env

    # Break network removal: applied but removal raises → netns probe fails.
    def broken_remove(sandbox_id):
        raise RuntimeError("nft delete failed")

    guest_thread = env["start_guest"]()
    report = _run(env, remove_network=broken_remove)
    guest_thread.join(timeout=15.0)

    assert report.execution_status == "completed"
    assert report.qa_status == SliceQaStatus.PASS
    # Execution and QA passed; trust alone reports the cleanup failure.
    assert report.trust_status == TrustVerificationStatus.VERIFICATION_FAILED.value
    checks = {c["check_id"]: c for c in report.teardown["checks"]}
    assert checks[TeardownCheckId.NETNS_REMOVED]["passed"] is False


def test_slice_forces_termination_when_vmm_ignores_shutdown(slice_env):
    env = slice_env

    # The VMM never exits on its own (guest ignores shutdown) → the
    # runner must force termination at the deadline and label it.
    class NeverExits(FakeVmm):
        def simulate_guest_poweroff(self, sandbox_id):  # never called
            pass

    # Use a VMM that stays running: replace after construction.
    env["vmm"] = NeverExits()

    guest_thread = env["start_guest"]()
    report = _run(env, shutdown_grace_seconds=1)
    guest_thread.join(timeout=15.0)

    # The guest completed its workload before the forced stop.
    assert env["guest_result"].get("status") in {"completed", "failed"}
    assert report.termination == "forced"
    assert not env["vmm"].running
    assert env["vmm"].stopped, "force_terminate must stop the VMM"
