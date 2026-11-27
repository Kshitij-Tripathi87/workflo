# 08 — Open Decisions and ADR Alignment

**Parent:** [Implementation Blueprint](00-master-implementation-plan.md)

## 1. Decisions already resolved for this plan

| Decision | Selection | Consequence |
|---|---|---|
| Desktop OS support | Linux + Windows + macOS | Portable CLI/web; per-OS native VM backend and independent gate |
| Primary stack | Python CLI, worker and control plane are canonical; TypeScript is the web/UI layer and a validated contract mirror | Extend the maintained Python lineage; do not rewrite the execution stack or create a second contract authority |
| Untrusted boundary | Entire repo, dependencies, scripts, processes, agent actions and subprocesses | Every workload input and model output is untrusted; guest is disposable |
| Isolation | filesystem, process/privilege, resource/time, network, credentials, agent permissions, cleanup, evidence | Admission must verify actual enforcement; no claim based on config alone |
| Model provider | User-selected local or cloud provider from settings | Provider adapter registry and profile schema required |
| Cloud privacy | No source code to hosted model | All cloud providers use metadata-only Workflo gateway |
| Agent capabilities | All nine requested; repair advisory only | Common capability/tool policy and activity evidence |
| Web application | Include web app and CLI install via website | `apps/dashboard` is Workflo web surface; `website/` stays marketing/download |
| CI | After local workflow | Same RunSpec/receipt/evidence contract must support later CI |

## 2. Existing proposed ADR family — ratify or supersede as a unit

The repository already contains seven load-bearing proposed ADRs. They are the decision source for the following blueprint areas; this package must not create parallel drafts that restate them. Before broad implementation, the project owner must explicitly **ratify, amend, or supersede each ADR-0015 through ADR-0021**. Record the decision in the existing ADR file and update dependent specifications in the same change.

| Existing ADR | Existing decision surface | Blueprint dependency / required owner action |
|---|---|---|
| [ADR-0015](../adr/ADR-0015-canonical-contracts-home.md) | Canonical contracts home and stack ownership | Ratify Python Pydantic authority; TypeScript/Zod is a checked mirror only. |
| [ADR-0016](../adr/ADR-0016-canonical-json-and-evidence-chain.md) | Canonical JSON and evidence-chain format | Ratify the canonical serialization profile, digest constraints, chain versioning and cross-language golden vectors. |
| [ADR-0017](../adr/ADR-0017-run-lifecycle-and-outcomes.md) | Run lifecycle and three independent outcomes | Ratify the exact lifecycle enum, legal transitions, transition authorities and execution/QA/trust separation. |
| [ADR-0018](../adr/ADR-0018-receipt-v5.md) | Receipt v5, isolated signer and DSSE envelope | Ratify v5 as the canonical new-receipt format; preserve byte-compatible v1–v4 verification and the development-only signer restriction. |
| [ADR-0019](../adr/ADR-0019-policy-admission.md) | Execution policy bundle and admission | Ratify immutable per-run policy bundle, component digests and fail-before-provisioning admission. |
| [ADR-0020](../adr/ADR-0020-event-finding-evidence-contracts.md) | Event, finding and evidence contracts | Ratify producer trust classes, no-CoT event schema, evidence scope validation and deterministic-vs-model finding authority. |
| [ADR-0021](../adr/ADR-0021-patch-protocol.md) | Patch proposal and approval binding | Ratify advisory-first behavior and exact-byte/base-revision-bound approval before any apply capability is considered. |

`ADR-0022` (Firecracker/KVM as the only production boundary) is already **Accepted** and is a baseline constraint, not part of the proposed-ADR ratification checklist. Do not weaken it through this blueprint.

### 2.1 New ADRs to create (do not duplicate ADR-0015…0022)

The following are genuinely new decisions not currently captured by the existing ADR family. Create these with the next available repository ADR numbers (expected ADR-0023 onward; verify numbering on the branch before creating files):

#### Cross-platform runtime backend strategy

**Decision proposal:** define a shared Python `SandboxBackend` protocol with Firecracker/KVM in `worker/` as the first strict backend. Use native Swift/Virtualization.framework and C#/.NET/Hyper-V helpers for macOS and Windows. Helpers communicate through narrow, versioned IPC; no host shell API.

**Reason:** Firecracker is Linux/KVM technology and is not a valid shared binary for macOS/Windows. Each platform requires its own runtime and independent security gate. A certified remote Linux runner is an alternative execution location, never a downgrade to a weaker local backend.

#### Cloud inference data policy

**Decision proposal:** all hosted models are called through Workflo's metadata-only gateway. Gateway requests use positive allow-list schemas and cannot accept source/body/raw-log data. Direct-to-cloud paths are disabled. Local inference may receive source only under an explicit local-source profile; there is no automatic local/cloud fallback.

**Reason:** the repository reconciliation identifies direct planner inference as a privacy bypass. Free-form observation fields also need stronger controls than key-name screening or regex source detection.

**Consequence:** cloud mode is for approved metadata/black-box observations; local mode may offer source-aware analysis. The product must state the distinction before a run.

#### Local model execution location

**Decision proposal:** the first implementation uses a runner-hosted local inference broker. The guest sends typed context requests; the runner reads permitted source from the immutable snapshot and calls the selected local endpoint. Provider credentials stay on the runner and never enter the guest. A model-inside-guest mode is a separate future ADR, not an implicit variant.

**Risk:** the broker becomes a small trusted host component. It may expose only constrained `ReadSourceForLocalInference` operations with strict path/size/profile policy, never a general host-file API.

**Acceptance:** guest cannot request arbitrary host files; source is read only under a local-source profile; request content is not logged or uploaded; the broker cannot route to a cloud provider.

#### Web runner topology

**Decision proposal:** the browser app submits run intent; a customer runner daemon establishes an outbound authenticated connection and executes source locally. Raw source is not uploaded through the browser. A remote certified Linux runner is supported when the user's desktop OS cannot provide a strict local backend.

**Consequence:** web execution depends on runner enrollment, heartbeat, leases, assignments, events and artifact APIs; it is not a serverless Next.js execution path.

#### Development versus strict runtime labels

**Decision proposal:** Docker and namespace/bwrap runtimes remain development/CI only. Strict runs require an approved per-platform VM backend and its passing security gate. No automatic fallback is permitted.

**Consequence:** CLI, dashboard, report and receipt expose the actual runtime and assurance profile. A development run must never be displayed as a strict run.

## 3. Specific repository risks to resolve

1. **The current Firecracker manager does not establish all claimed resource boundaries.** Current `manager.py` teardown code documents that manager itself does not create a cgroup or network namespace and checks for absence of managed paths. Actual per-run cgroup attachment/limit enforcement and firewall/network policy must be implemented and proven.
2. **The latest guest slice runs a fixed workload.** It must be extended to full source snapshot, checks, app lifecycle, agent and evidence workflow.
3. **The current inference design still contains a direct mode.** Supported cloud mode must not be able to bypass privacy gateway.
4. **The current gateway's arbitrary text fields are not a sufficient privacy boundary.** Move to positive typed observation objects; free-form strings can leak source even when keys are screened.
5. **The current dashboard is a placeholder branded Tenant Shield.** Use it, but treat it as UI shell rather than implemented Workflo product.
6. **The `workflo-ai-integration` directory has model router/safety gate scaffolding.** Consolidate only after tests and dataflow review; don't leave two provider routers active.
7. **P4 acceptance is dated 2026-10-11.** Real GGUF/image and protected staging gates recorded there need fresh evidence on current main before release; do not blindly repeat older status.
8. **Multi-OS is a product requirement, not a currently proven security capability.** Every OS adapter needs real-hardware tests and distinct security gate.
9. **ADR-0015 is proposed, not accepted.** Ratify canonical ownership before broad implementation.
10. **Root repository test scripts include legacy product surfaces.** Keep active CI meaningful; do not assume root-wide green means Trust MVP all green.

## 4. Required technical spikes before locking interfaces

### SP-01 — macOS guest transport and cleanup

Deliver a real minimal Linux VM via Virtualization.framework; demonstrate guest-to-host socket protocol, host termination, disk disposal and network deny. Record any Apple entitlement/signing limitation. Do not design all macOS details from assumption.

### SP-02 — Windows Hyper-V guest transport

Deliver a minimal Linux VM on supported Windows host, connect typed protocol over Hyper-V socket/VMBus, prove isolated network and force stop/disk teardown. Verify edition availability (including Home behavior).

### SP-03 — Host-brokered local model request

Prove agent in guest can request a bounded local model plan without receiving host key, accessing arbitrary host files or causing cloud egress. The host must validate file paths and source policy.

### SP-04 — Cloud privacy proof

Seed unique canary source/secret markers across source/log/browser/test environment; capture exact provider-bound bytes; assert no marker or unapproved free-form data leaves the runner. Verify all provider adapters share same sanitizer.

### SP-05 — End-to-end receipt v5 writer

Trace the current `run-dev` receipt v5 flow, connect actual worker-produced evidence and host teardown to canonical writer, verify in a separate process with trusted public key.

## 5. Ratification checklist

Before the first broad implementation PR, the project owner should:

- [ ] Ratify, amend or supersede the complete proposed ADR family `ADR-0015` through `ADR-0021`; record one disposition per existing file.
- [ ] Confirm `ADR-0022` remains accepted and unchanged as the production isolation boundary.
- [ ] Create and approve the new cross-platform runtime-backend ADR (next available number after `ADR-0022`).
- [ ] Create and approve the new cloud inference privacy ADR.
- [ ] Create and approve the new local inference broker ADR.
- [ ] Create and approve the new web/customer-runner topology ADR.
- [ ] Create and approve the new development-vs-strict runtime-labeling ADR.
- [ ] Ensure no new ADR restates or conflicts with the existing canonical JSON/evidence, lifecycle, receipt, policy-admission, event/finding/evidence or patch-protocol ADRs.

User product requirements are reflected in the blueprint; all architecture decisions must be recorded in the repository's existing ADR series, with status and supersession links maintained there.