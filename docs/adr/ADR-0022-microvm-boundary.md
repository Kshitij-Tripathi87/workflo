# ADR-0022 — Firecracker/KVM microVM is the only production execution boundary

**Status:** Accepted (mirrors brief ADR-001/ADR-002) · 2026-11-11

## Context

At the time of this decision the tree contained no microVM code. Existing boundaries were Docker (`apps/sandbox-executor`) and bwrap + namespaces (`packages/sandbox-runtime`). Neither meets the production boundary the brief mandates. The brief forbids relabeling either as equivalent or silently falling back when the secure backend is unavailable.

The host and guest-supervisor foundation now lives in [`worker/`](../../worker/). The existing control-plane dispatcher is not wired to it. The KVM integration file probes capabilities; it does not yet establish the real boot and teardown evidence required by Gate B.

## Decision

1. **Production customer runs execute only inside a dedicated Firecracker microVM per run attempt** (KVM boundary; pinned Firecracker + jailer; seccomp/cgroups/namespaces on the host side; fresh writable disk; no host mount of guest state). ADR-001 applies.

2. **No fallback.** A worker without KVM, an unpinned/unsupported Firecracker or jailer version, a missing approved guest image, or a failed security check is **ineligible**; the run remains pending or fails with an explicit infrastructure reason. Docker and bwrap never serve as the production boundary, and no result may be reported as "isolated" from them.

3. **Interim status of existing runtimes:** Docker and namespace runtimes remain supported for **local development, CLI dev mode, and CI regression testing**, clearly labeled in receipts/verification as non-microVM (`runtime_type`). Receipts produced in those modes must remain marked accordingly and must not be presented as satisfying Gate B.

4. **Host API surface is typed and narrow** (brief §3.3): `ProvisionSandbox`, `GetSandboxStatus`, `DeliverRunCapability`, `RequestGracefulShutdown`, `ForceTerminate`, `CollectHostLifecycleEvidence`, `VerifyResourcesRemoved`. No `execute_command`, no host shell, no Docker socket, no host filesystem to the guest. Guest↔host communication is a narrow typed protocol (vsock target) with attempt binding, sequence numbers, size limits, and rejection of unknown operations.

5. **Teardown verification is independent** and produces the four-outcome record (`VERIFIED_CLEAN | VERIFICATION_FAILED | CLEANUP_INCOMPLETE | UNKNOWN`) that feeds the trust outcome and receipt v5.

6. **Gate B is the admission test for this boundary**: pinned microVM boots, safe fixture executes, forbidden host access fails, cross-VM separation holds, resource limits enforce, egress defaults deny, gateway outage fails closed, crash handling and teardown pass on real KVM — with retained evidence. Mocks do not satisfy it.

## Consequences

- The critical path is: microVM worker (Phase 3) → negative test matrix → Gate B evidence.
- `packages/sandbox` (TS) and `apps/sandbox-executor` (Docker) stop receiving capability investment; `packages/sandbox-runtime` remains the dev/CI isolation runtime while the microVM path is built.
- Sandbox assignment schema (policy digest, runtime image digest, resource limits, network policy, capabilities) is versioned and authenticated; worker admission checks it before the VMM starts.
