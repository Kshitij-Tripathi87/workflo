# Agent 02 — DeepSeek V4.1 Flash-1017: Control Plane and Execution Platform

**Role:** Core platform/runtime implementation engineer  
**Branch:** `agent/deepseek-execution`  
**Primary owner:** DeepSeek V4.1 Flash-1017  
**Reviewers:** MiniMax (security findings only), GPT-6 Luna (integration tests), human owner (release gate)

## 1. Why this model owns this work

The DeepSeek V4.1 Flash-1017 model card reports:

- DeepSWE v1.1: **77.0**
- Automation-Bench v1.0.6: **60.5**
- Terminal-Bench 4.0: **42.3**
- NL2Repo-Bench: **68.2**

In that published table, 77.0 is the strongest DeepSWE v1.1 result among the listed comparison models. DeepSeek states that DeepSWE used the Mini-SWE-V2 harness and Terminal-Bench used Claude Code. These are vendor-reported results; they do not prove Workflo-specific reliability.

Source: https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash-1017

## 2. Owned paths

Primary:

- `worker/` — Firecracker/jailer host lifecycle and guest supervisor protocol.
- `apps/control-plane/` — run admission/dispatch/runner claims/leases, excluding inference files owned by MiniMax.
- `apps/worker-engine/` — guest workload packaging and deterministic execution lifecycle.
- Focused integration tests for these components.

Do not create another Firecracker implementation under `apps/sandbox-executor/`. Do not promote Docker or `packages/sandbox-runtime/` into strict execution.

## 3. Mission

Close the real gap between durable run admission and a real customer-controlled Firecracker/KVM execution. Deliver a complete deterministic run lifecycle with independently observed teardown and evidence handoff.

This is the highest-risk and schedule-critical workstream.

## 4. Work packages

### DS-01 — Reconcile the actual baseline (Days 1–2)

- Read ADR-0022, worker code, admission and assignment models, KVM integration suite, control-plane dispatch service, outbox/lease code and current CI.
- Identify the exact current commit and all missing real-KVM prerequisites.
- Separate real code, mock-tested code, capability probes and unproven paths.
- Identify the single canonical host implementation and guest workload entrypoint.

**Acceptance:** a file-level execution graph and gap list; no parallel Firecracker host is created.

### DS-02 — Freeze the assignment boundary (Days 2–4)

Coordinate with the contract owner. Confirm versioned assignment fields for run ID, attempt ID, sandbox ID, policy digest, runtime image digest, guest kernel/rootfs identity, resource limits, network policy, capabilities, expiry and nonce.

- Validate assignment authentication before VMM start.
- Reject unknown fields/operations where protocol policy requires strict schemas.
- Bind every request and response to the same run/attempt.
- Enforce size limits, sequence numbers and replay detection.

**Acceptance:** canonical contract tests and producer/consumer parity; no unreviewed schema change.

### DS-03 — Complete durable runner claims (Days 3–7)

- Connect transactional outbox dispatch to customer runner claim.
- Use runner enrollment identity and short-lived scoped credentials.
- Implement claim lease, heartbeat, expiry, retry and attempt fencing.
- Make state transitions idempotent.
- Recover dispatch after API and worker restart.
- Ensure cancellation races resolve to one valid canonical terminal state.
- Enforce PostgreSQL RLS using a non-owner, non-superuser application role without BYPASSRLS.

**Acceptance:** restart/replay/lease-expiry/concurrent-claim tests and a non-skipping real PostgreSQL RLS gate.

### DS-04 — Real Firecracker boot and guest readiness (Days 5–12)

- Pin Firecracker and jailer versions and binary hashes.
- Validate KVM availability and permissions.
- Pin guest kernel/rootfs digests; never accept mutable image tags as identity.
- Create fresh per-attempt disk state and isolated work directories.
- Use jailer, cgroups, namespaces and seccomp configuration required by ADR-0022.
- Do not mount host filesystem, Docker socket or host credentials into the guest.
- Complete guest supervisor startup and authenticated vsock handshake.
- Execute a fixed deterministic guest workload first; only then wire Workflo worker behavior.

**Acceptance:** real KVM boot on a provisioned host; guest identity matches assigned digests; failed boot is infrastructure failure, not success.

### DS-05 — Resource and network enforcement (Days 8–14)

- Enforce vCPU, memory, disk, PID/process, output and wall-clock ceilings.
- Deny outbound egress by default.
- Block host network, cloud metadata and private address access unless a narrowly scoped route is explicitly part of the run assignment.
- Keep source/dependency preparation outside the sealed execution phase.
- Ensure only explicit internal app endpoints are reachable where required.
- Test two concurrent VMs for cross-VM isolation.

**Acceptance:** positive/negative network and resource tests against real KVM; no skipped controls represented as proof.

### DS-06 — Typed host/guest operations (Days 10–16)

Implement only the approved narrow operations in ADR-0022:

- ProvisionSandbox
- GetSandboxStatus
- DeliverRunCapability
- RequestGracefulShutdown
- ForceTerminate
- CollectHostLifecycleEvidence
- VerifyResourcesRemoved

No generic host shell, `execute_command`, Docker socket, arbitrary host filesystem operation or guest-selected host path.

**Acceptance:** unknown operation, wrong attempt, expired capability, replay, oversized message and invalid sequence are rejected.

### DS-07 — Guest workload and deterministic checks (Days 12–18)

- Package the actual approved deterministic workload in the guest image.
- Bind source revision and policy before execution.
- Ensure test command/argv is policy-derived and never a shell-concatenated user string.
- Bound runtime, output, file count, source size and artifact size.
- Keep result parsing outside guest claims where possible; validate reports on trusted host.
- Preserve verified test failure as QA failure, not infrastructure failure, if execution and teardown are sound.

**Acceptance:** exact commit is executed; test results are complete and bound to run/attempt; malformed/missing/partial reports fail closed.

### DS-08 — Independent teardown and evidence (Days 15–21)

- Observe VMM and jailer processes, cgroups, namespace/network resources, vsock/listeners and ephemeral disk/workspace lifecycle from the host.
- Verify resource removal independently of guest shutdown claims.
- Distinguish `VERIFIED_CLEAN`, `VERIFICATION_FAILED`, `CLEANUP_INCOMPLETE` and `UNKNOWN`.
- Deliver host evidence and guest evidence separately to receipt/evidence verifier.
- Sign only after the independent verifier accepts the evidence.
- Ensure host crash and force termination preserve partial diagnostic evidence without false completion.

**Acceptance:** deliberate teardown failure produces an untrusted outcome and no false successful receipt.

### DS-09 — Control-plane end-to-end integration (Days 18–24)

- Connect admitted RunAttempt to runner claim, VM provisioning, execution, status heartbeat and terminal result.
- Persist lifecycle transitions and outbox messages transactionally.
- Ensure retries never duplicate a running VM for the same attempt.
- Implement cancellation, timeout and infrastructure recovery.
- Make partial evidence visible as incomplete.

**Acceptance:** one real end-to-end deterministic run from control-plane admission to receipt verification.

### DS-10 — Hardening and handoff (Days 24–30)

- Run real-KVM adversarial matrix and crash/restart suite.
- Fix P0/P1 findings.
- Produce pinned artifact inventory, host setup, operator runbook, failure taxonomy, metrics and rollback process.
- Submit Gate B evidence for independent review.

## 5. Required negative tests

- No `/dev/kvm` or insufficient permissions.
- Unpinned/unsupported Firecracker or jailer.
- Missing or hash-mismatched kernel/rootfs.
- Assignment signature/expiry/nonce invalid.
- Replayed or cross-attempt guest message.
- Host filesystem/Docker socket/metadata access.
- Egress and DNS attempts.
- Cross-VM probing.
- Resource exhaustion and wall-clock timeout.
- Guest crash, VMM crash, host supervisor crash.
- Outbox replay and duplicate runner claim.
- Lease expiry during execution.
- Cancellation racing with completion.
- Disk full and evidence upload interruption.
- Teardown resource remains present.
- Malformed test result and evidence mismatch.

## 6. Reliability invariants

1. A run cannot enter execution before admission and assignment validation.
2. One run attempt has at most one active VM.
3. Strict mode never downgrades to development isolation.
4. The guest cannot instruct the host to execute arbitrary commands.
5. The guest cannot decide whether teardown is clean.
6. No receipt claims verified trust until the host verifier confirms the required evidence.
7. A test failure can be a valid QA outcome; incomplete execution and unverified teardown cannot be a passing trust outcome.
8. Every resource has an owner, deadline and cleanup path.

## 7. Stop conditions

Stop and escalate if hardware/KVM host is unavailable, approved guest artifacts are missing, real egress controls cannot be enforced, host/guest protocol requires a general shell, durable dispatch cannot be fenced, or teardown evidence is incomplete.

Mocks and capability probes are useful development tests. They do not pass Gate B. The actual KVM workflow must run on the pinned release candidate and retain evidence.
