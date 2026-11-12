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

__all__ = [
    # assignment
    "AssignmentError",
    "ResourceLimitsV1",
    "GuestImageV1",
    "SandboxAssignmentV1",
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
]
