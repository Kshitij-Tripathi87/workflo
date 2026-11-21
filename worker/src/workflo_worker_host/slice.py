"""The microVM execution slice — one guest, fixed workload, verified teardown.

Implements the queue's slice definition end to end on the host side:

    provision → capability → ready → workload manifest → shutdown request
    → deadline → destroy → teardown verification → SliceReport

Three independent status axes (never collapsed into one "success"):

- **execution** — did the protocol run complete? ``completed`` /
  ``provision_failed`` / ``guest_failed`` / ``timed_out`` /
  ``protocol_violation``;
- **qa** — did the fixed workload pass its checks? ``pass`` / ``fail`` /
  ``not_run`` (derived host-side from the digest-verified manifest's
  ``workload_result`` — the guest never sets QA);
- **trust** — does teardown verify? the ``TrustVerificationStatus`` from
  independent host probes.

Failures never suppress the report: every path ends with a ``SliceReport``
written to ``output_dir`` so an operator can see exactly which axis broke.
The runner never invents a pass — a missing manifest is ``qa=not_run``,
an unverifiable teardown is ``trust=unknown``/``verification_failed``.
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path

from pydantic import BaseModel, ConfigDict
from workflo_schema.contracts.canonical import digest_matches
from workflo_schema.contracts.common import (
    SCHEMA_VERSION,
    CanonicalTimestamp,
    DigestString,
    IdString,
    utc_now_ms,
)
from workflo_schema.contracts.outcomes import TrustVerificationStatus

from workflo_worker_host.admission import (
    PinnedRuntime,
    SandboxAssignmentV1,
    WorkerCapabilities,
)
from workflo_worker_host.manager import (
    SandboxManager,
    SandboxState,
    vsock_uds_path,
)
from workflo_worker_host.protocol import (
    BindingError,
    GuestMessageType,
    ProtocolError,
    SequenceError,
    UnknownOperationError,
    VersionMismatchError,
)
from workflo_worker_host.vsock_channel import (
    ChannelError,
    HostVsockChannel,
    guest_initiated_listen_path,
)

__all__ = [
    "SliceExecutionStatus",
    "SliceQaStatus",
    "SliceReport",
    "run_slice",
]


class SliceExecutionStatus(str):
    """Execution axis values (plain strings for JSON friendliness)."""

    COMPLETED = "completed"
    PROVISION_FAILED = "provision_failed"
    GUEST_FAILED = "guest_failed"
    TIMED_OUT = "timed_out"
    PROTOCOL_VIOLATION = "protocol_violation"


class SliceQaStatus(str):
    PASS = "pass"
    FAIL = "fail"
    NOT_RUN = "not_run"


class SliceReport(BaseModel):
    """The slice's evidence record — extra=forbid, always written."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    slice_id: IdString
    attempt_id: IdString
    sandbox_id: IdString
    run_id: IdString
    assignment_digest: DigestString | None = None
    capability_digest: DigestString | None = None
    # Three axes — deliberately independent.
    execution_status: str
    qa_status: str
    trust_status: str
    # Supporting evidence (host-observed only; guest claims are labelled).
    workload_result: dict | None = None
    teardown: dict | None = None
    host_evidence: list = []
    termination: str | None = None  # "graceful" | "forced" | None
    error: str | None = None
    started_at: CanonicalTimestamp
    finished_at: CanonicalTimestamp


def run_slice(
    *,
    assignment: SandboxAssignmentV1,
    client,
    pinned: PinnedRuntime,
    capabilities: WorkerCapabilities,
    output_dir: str | Path,
    apply_network=None,
    remove_network=None,
    require_signed_assignment: bool = False,
    guest_ready_timeout_seconds: int = 30,
    workload_timeout_seconds: int = 60,
    shutdown_grace_seconds: int = 10,
    scratch_dir: str = "/var/lib/workflo/scratch",
    vsock_dir: str = "/run/workflo/vsock",
    uid: int = 0,
    gid: int = 0,
    probes: dict | None = None,
    channel_factory=HostVsockChannel,
) -> SliceReport:
    """Run one slice to completion (or honest failure) and write the report.

    The channel is built on the host-visible view of the guest-initiated
    vsock path (chroot-aware when the client exposes ``host_view_path``),
    bound BEFORE the VM boots so the guest's first connect lands on a live
    listener.
    """
    started_at = utc_now_ms()
    slice_id = f"slice-{uuid.uuid4().hex[:16]}"
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    sandbox_id = assignment.sandbox_id
    attempt_id = assignment.attempt_id

    # Host-visible listen path: inside the jail the guest/Firecracker see
    # `<uds>_<PORT>`; on the host that file lives under the chroot root.
    raw_listen_path = guest_initiated_listen_path(
        vsock_uds_path(vsock_dir, sandbox_id)
    )
    host_view = getattr(client, "host_view_path", None)
    listen_path = (
        host_view(sandbox_id, raw_listen_path) if host_view else raw_listen_path
    )

    channel = channel_factory(listen_path)
    manager = SandboxManager(
        client=client,
        pinned=pinned,
        capabilities=capabilities,
        require_signed_assignment=require_signed_assignment,
        guest_ready_timeout_seconds=guest_ready_timeout_seconds,
        probes=probes,
        scratch_dir=scratch_dir,
        vsock_dir=vsock_dir,
        apply_network=apply_network,
        remove_network=remove_network,
        receive_guest_message=channel.receive,
        send_guest_message=channel.send,
        close_guest_transport=channel.close,
        uid=uid,
        gid=gid,
    )

    execution = SliceExecutionStatus.PROVISION_FAILED
    qa = SliceQaStatus.NOT_RUN
    trust = TrustVerificationStatus.UNKNOWN.value
    workload_result: dict | None = None
    teardown: dict | None = None
    termination: str | None = None
    error: str | None = None
    host_evidence: list = []
    capability_digest: str | None = None
    assignment_digest: str | None = None
    handle = None

    try:
        assignment_digest = assignment.digest()
    except Exception:  # noqa: BLE001 — digest is evidence, not a gate
        assignment_digest = None

    try:
        channel.listen()
        # -- provision: network → scratch → boot → capability → ready ------
        try:
            handle = manager.provision_sandbox(assignment)
            capability_digest = handle.capability_digest
            execution = SliceExecutionStatus.PROVISION_FAILED  # until workload
        except Exception as exc:  # noqa: BLE001 — any provision failure
            error = f"provision failed: {type(exc).__name__}: {exc}"
            execution = SliceExecutionStatus.PROVISION_FAILED
            handle = manager.sandbox_handle(sandbox_id)
            if handle is not None:
                host_evidence = manager.collect_host_lifecycle_evidence(handle)
                if handle.last_teardown is not None:
                    teardown = handle.last_teardown.model_dump(mode="json")
                    trust = handle.last_teardown.outcome.value

        if handle is not None and handle.state == SandboxState.READY:
            # -- workload phase: read frames until manifest/failure/timeout -
            manifest_frame_deadline = time.monotonic() + workload_timeout_seconds
            got_manifest = False
            while not got_manifest:
                remaining = manifest_frame_deadline - time.monotonic()
                if remaining <= 0:
                    execution = SliceExecutionStatus.TIMED_OUT
                    error = (
                        error
                        or f"no evidence manifest within {workload_timeout_seconds}s"
                    )
                    break
                try:
                    message = manager.receive_guest_frame(
                        handle, timeout=min(remaining, 5.0)
                    )
                except (ProtocolError, SequenceError, BindingError,
                        VersionMismatchError, UnknownOperationError) as exc:
                    execution = SliceExecutionStatus.PROTOCOL_VIOLATION
                    error = f"protocol violation: {type(exc).__name__}: {exc}"
                    break
                except ChannelError as exc:
                    execution = SliceExecutionStatus.GUEST_FAILED
                    error = f"guest transport failed: {exc}"
                    break
                if message is None:
                    continue
                if message.message_type is GuestMessageType.EVIDENCE_MANIFEST_SUBMITTED:
                    payload = message.payload
                    manifest = payload.get("manifest")
                    claimed = payload.get("manifest_digest")
                    if not isinstance(manifest, dict) or not isinstance(claimed, str):
                        execution = SliceExecutionStatus.PROTOCOL_VIOLATION
                        error = "manifest frame missing manifest/digest"
                        break
                    if not digest_matches(claimed, manifest):
                        execution = SliceExecutionStatus.PROTOCOL_VIOLATION
                        error = "manifest digest does not match manifest payload"
                        break
                    # QA comes from the workload result inside the verified
                    # manifest — never from an unverified claim.
                    result = manifest.get("workload_result")
                    if isinstance(result, dict) and "ok" in result:
                        workload_result = result
                        qa = (
                            SliceQaStatus.PASS
                            if result["ok"]
                            else SliceQaStatus.FAIL
                        )
                    else:
                        qa = SliceQaStatus.NOT_RUN
                        error = (
                            error
                            or "manifest carried no workload_result; qa=not_run"
                        )
                    execution = SliceExecutionStatus.COMPLETED
                    got_manifest = True
                elif message.message_type is GuestMessageType.GUEST_FAILURE_REPORTED:
                    execution = SliceExecutionStatus.GUEST_FAILED
                    detail = message.payload.get("detail", "")
                    error = f"guest reported failure: {detail}"
                    got_manifest = True
                elif message.message_type is GuestMessageType.LIFECYCLE_HEARTBEAT:
                    host_evidence.append(
                        {
                            "event": "guest_heartbeat_observed",
                            "sequence": message.sequence_number,
                            "observed_at": utc_now_ms(),
                        }
                    )
                else:
                    # Anything else pre-manifest is out of protocol.
                    execution = SliceExecutionStatus.PROTOCOL_VIOLATION
                    error = (
                        f"unexpected message before manifest: "
                        f"{message.message_type.value}"
                    )
                    got_manifest = True

            # -- shutdown: request, wait to deadline, else force ------------
            if handle.state == SandboxState.READY:
                try:
                    manager.request_graceful_shutdown(
                        handle, deadline_seconds=shutdown_grace_seconds
                    )
                except Exception as exc:  # noqa: BLE001 — recorded, not fatal
                    host_evidence.append(
                        {
                            "event": "shutdown_request_failed",
                            "detail": f"{type(exc).__name__}: {exc}",
                            "observed_at": utc_now_ms(),
                        }
                    )
                # Wait for the VMM to exit on its own up to the deadline.
                grace_deadline = time.monotonic() + shutdown_grace_seconds
                while client.is_running(sandbox_id):
                    if time.monotonic() >= grace_deadline:
                        manager.force_terminate(handle)
                        termination = "forced"
                        break
                    time.sleep(0.05)
                else:
                    termination = "graceful"
                if termination is None:
                    termination = "graceful"

            # -- destroy + independent teardown verification ----------------
            try:
                verification = manager.destroy_sandbox(handle)
                teardown = verification.model_dump(mode="json")
                trust = verification.outcome.value
            except Exception as exc:  # noqa: BLE001 — teardown must record
                error = f"{error}; teardown failed: {type(exc).__name__}: {exc}"
                trust = TrustVerificationStatus.CLEANUP_INCOMPLETE.value
            host_evidence = manager.collect_host_lifecycle_evidence(handle)
            lifecycle = getattr(client, "lifecycle_record", None)
            if callable(lifecycle):
                try:
                    record = lifecycle(sandbox_id)
                    if record:
                        host_evidence.append(record)
                except Exception:  # noqa: BLE001 — evidence is best effort
                    pass
    except Exception as exc:  # noqa: BLE001 — last resort: never lose the report
        if error is None:
            error = f"slice aborted: {type(exc).__name__}: {exc}"
    finally:
        channel.close()

    report = SliceReport(
        slice_id=slice_id,
        attempt_id=attempt_id,
        sandbox_id=sandbox_id,
        run_id=assignment.run_id,
        assignment_digest=assignment_digest,
        capability_digest=capability_digest,
        execution_status=execution,
        qa_status=qa,
        trust_status=trust,
        workload_result=workload_result,
        teardown=teardown,
        host_evidence=host_evidence,
        termination=termination,
        error=error,
        started_at=started_at,
        finished_at=utc_now_ms(),
    )
    report_path = output_path / f"slice-report-{slice_id}.json"
    report_path.write_text(report.model_dump_json(indent=2))
    return report
