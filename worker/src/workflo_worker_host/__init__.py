"""Host-side microVM sandbox manager (Phase 3 — brief §7, ADR-0022).

The execution plane's trusted host: typed provisioning, pinned
Firecracker/jailer, narrow guest protocol, default-deny egress, and
independent teardown verification. No fallback backends.
"""

from workflo_worker_host.assignment import (
    AssignmentError,
    ResourceLimitsV1,
    GuestImageV1,
    SandboxAssignmentV1,
    SandboxAssignmentV2,
    constant_time_equals,
)
from workflo_worker_host.admission import (
    HostProbeError,
    PinnedRuntime,
    WorkerCapabilities,
    check_eligibility,
    probe_capabilities,
)
from workflo_worker_host.protocol import (
    MAX_MESSAGE_BYTES,
    MAX_PAYLOAD_BYTES,
    PROTOCOL_VERSION,
    BindingError,
    GuestMessageV1,
    GuestMessageType,
    GuestProtocolSession,
    ProtocolError,
    SequenceError,
    UnknownOperationError,
    VersionMismatchError,
    build_guest_message,
    frame_message,
    parse_frame,
)
from workflo_worker_host.network import (
    ALWAYS_BLOCKED,
    EgressPolicyError,
    EgressVerdict,
    build_nftables_ruleset,
    validate_policy,
)
from workflo_worker_host.manager import (
    FirecrackerClient,
    ProvisionError,
    SandboxHandle,
    SandboxManager,
    SandboxState,
    TeardownProbeSet,
    build_jailer_argv,
    build_vm_config,
)
from workflo_worker_host.guest_supervisor import (
    GuestCapabilityV1,
    GuestIdentityError,
    GuestSupervisor,
    SupervisorState,
)
from workflo_worker_host.network import apply_nftables, remove_nftables
from workflo_worker_host.vsock_channel import (
    HOST_CID,
    VSOCK_SUPERVISOR_PORT,
    ChannelError,
    HostVsockChannel,
    guest_initiated_listen_path,
)
from workflo_worker_host.workload import (
    FIXED_WORKLOAD_ID,
    PINNED_MARKER_SHA256,
    run_fixed_workload,
)
from workflo_worker_host.guest_runtime import (
    parse_boot_identity,
    run_guest_slice,
)
from workflo_worker_host.slice import (
    SliceExecutionStatus,
    SliceQaStatus,
    SliceReport,
    run_slice,
)
from workflo_worker_host.firecracker_client import (
    JailerFirecrackerClient,
    VmmError,
)
from workflo_worker_host.manager import (
    build_run_capability,
    vsock_uds_path,
)

__all__ = [
    # assignment
    "AssignmentError",
    "ResourceLimitsV1",
    "GuestImageV1",
    "SandboxAssignmentV1",
    "SandboxAssignmentV2",
    "constant_time_equals",
    # admission
    "HostProbeError",
    "PinnedRuntime",
    "WorkerCapabilities",
    "check_eligibility",
    "probe_capabilities",
    # protocol
    "PROTOCOL_VERSION",
    "MAX_MESSAGE_BYTES",
    "MAX_PAYLOAD_BYTES",
    "BindingError",
    "GuestMessageV1",
    "GuestMessageType",
    "GuestProtocolSession",
    "ProtocolError",
    "SequenceError",
    "UnknownOperationError",
    "VersionMismatchError",
    "build_guest_message",
    "frame_message",
    "parse_frame",
    # network
    "ALWAYS_BLOCKED",
    "EgressPolicyError",
    "EgressVerdict",
    "build_nftables_ruleset",
    "validate_policy",
    # manager
    "FirecrackerClient",
    "ProvisionError",
    "SandboxHandle",
    "SandboxManager",
    "SandboxState",
    "TeardownProbeSet",
    "build_jailer_argv",
    "build_vm_config",
    # guest supervisor
    "GuestCapabilityV1",
    "GuestIdentityError",
    "GuestSupervisor",
    "SupervisorState",
    # network appliers
    "apply_nftables",
    "remove_nftables",
    # vsock transport
    "HOST_CID",
    "VSOCK_SUPERVISOR_PORT",
    "ChannelError",
    "HostVsockChannel",
    "guest_initiated_listen_path",
    # fixed workload + guest runtime
    "FIXED_WORKLOAD_ID",
    "PINNED_MARKER_SHA256",
    "run_fixed_workload",
    "parse_boot_identity",
    "run_guest_slice",
    # slice runner
    "SliceExecutionStatus",
    "SliceQaStatus",
    "SliceReport",
    "run_slice",
    # real VMM client
    "JailerFirecrackerClient",
    "VmmError",
    # capability + path helpers
    "build_run_capability",
    "vsock_uds_path",
]
