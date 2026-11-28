# Workflo Delivery Roadmap — M1 First, Dependency-Gated Expansion

**Current priority:** M1 native CLI → real Firecracker/KVM → independently verified receipt  
**M1 target:** 23 December 2026 (25-day programme beginning 29 November)  
**Release posture:** quality gates outrank calendar; no mock or waiver can substitute for real KVM and offline verification.

## 1. Roadmap hierarchy

The delivery plan is split into three scopes. The 25-day target applies to **M1 only**. It does not silently promise the entire beta platform in 25 days.

| Scope | Target | Release outcome |
|---|---|---|
| **M1 — trusted vertical slice** | 25 days, target 23 Dec 2026 | Native Go CLI submits one exact GitHub commit; current FastAPI admits it; customer Linux/KVM runner uses existing Firecracker host; one pinned pytest profile runs in a fresh microVM; independent teardown; signed receipt; offline verifier |
| **M1.1 — client/runner parity and usability** | After M1 acceptance | Incremental Go customer-runner parity; local source connector; native packaging/upgrade; additional profiles; better operational recovery |
| **M2 — product beta expansion** | Re-estimate after M1 evidence | Team/org roles, 4 language profiles, deep AI/BYOK, security mode productization, dashboard, 15-user/45-submission admission test, GitHub PR checks and operator UX |

No phase advances because the calendar date arrived. Each phase requires the stated evidence.

## 2. Binding M1 architecture

- **Go CLI:** new native executable, no Python, Node or model runtime dependency.
- **Control plane:** keep FastAPI/Python; add versioned M1 endpoints and preserve V1.
- **Runner:** use the current Python Firecracker host under `worker/` as the M1 reference through a narrow adapter. ADR-0024 makes Go runner migration incremental; do not create a second Firecracker manager.
- **Guest:** keep existing guest engine and canonical schema; one pinned pytest profile only.
- **Isolation:** fresh Firecracker/KVM microVM per attempt. No Docker, bwrap, namespace-only or host-execution fallback.
- **Identity:** existing human device-flow identity and server-resolved project scope; separate runner identity.
- **Evidence:** existing canonical receipt and MicroVM teardown semantics; no new receipt format.
- **AI and dashboard:** no inference in the M1 critical path; Gemini design prep only until M1 acceptance.

The authoritative details are in [M1 25-day execution plan](M1-25-DAY-EXECUTION-PLAN.md), [M1 interface registry](M1-INTERFACE-REGISTRY.md), [M1 milestone specification](MILESTONE-01-NATIVE-CLI-FIRECRACKER-RECEIPT.md), [ADR-0024](../adr/ADR-0024-native-go-cli-and-runner.md) and the [API contract freeze](API-CONTRACT-FREEZE-M1.md).

## 3. M1 critical dependency chain

1. Audit baseline, calibrate agents and confirm actual KVM/signing/GitHub test environment.
2. Freeze semantic interfaces and publish generated OpenAPI/client fixtures.
3. Build native Go CLI core and command contract.
4. Implement additive FastAPI run admission, runner enrollment/claim/lease/state and artifact metadata.
5. Bridge strict dispatch to the existing Firecracker host adapter, not the legacy `SandboxExecutor`.
6. Pin exact GitHub source, guest image, Firecracker/jailer and Python pytest profile.
7. Prove guest/host protocol, resource/network enforcement and evidence collection.
8. Independently verify all eight MicroVM teardown checks.
9. Sign canonical receipt; verify offline on a clean disconnected machine.
10. Complete negative tests, evidence packet and human acceptance.

The calendar and daily exit evidence live in the 25-day plan. No independent agent may reorder steps or substitute a mock for a dependency.

## 4. Post-M1 work packages

### M1.1 — Go runner migration

**Owner:** DeepSeek; **review:** MiniMax + human security owner; **API compatibility:** Luna.

- Add Go runner implementation beside the Python host.
- Reuse the approved assignment, guest protocol, policy, evidence and receipt contracts.
- Run the same positive/negative fixtures against both implementations.
- Prove real KVM parity, teardown and offline receipt verification.
- Cut over only after parity evidence and rollback are approved.
- Keep Python as fallback/reference until the Go path is accepted; never run two authorities for one attempt.

### M1.1 — Client completion and distribution

**Owner:** GLM; **review:** DeepSeek + Luna.

- Local source connector and clean/dirty worktree semantics.
- Complete supported Python/Node/Go/Java profiles as separate pinned profile releases.
- npm/pnpm/Bun wrappers carrying native platform binaries; no Python virtualenv bootstrap.
- Signed/checksummed archives, provenance, upgrade/rollback and clean-machine tests.
- No package is publicly published until owner approves name, versioning and supply-chain release workflow.

### M2 — Backend/platform expansion

**Owner:** GPT-6 Luna; **review:** MiniMax + DeepSeek + human owner.

- Organization membership, invitations, Owner/Admin/Developer/Viewer and project role matrix.
- Broader RLS/tenant model after data-model review.
- GitHub App installation/webhooks and commit/PR checks.
- BYOK provider profile, consent, metadata-only gateway and usage budgets.
- Capacity/fair scheduling, observability and 15-user/45-submission admission test.
- Backup/restore, operations, retention and incident response hardening.

### M2 — Dashboard

**Owner:** Gemini; **API:** Luna; **UX/CLI parity:** GLM.

- Start production UI only after signed M1 acceptance.
- Build in slices against generated API types and actual backend states.
- Begin with read-only Runs list/detail, lifecycle and evidence/receipt.
- Then projects/repositories, runner management, integrations, team, policy/privacy and audit.
- Never use fake operational metrics or frontend-only authorization.

### M2 — Deep AI and security modes

**Owners:** MiniMax (security/policy tests), Luna (API/business logic), DeepSeek (runner integration), GLM (CLI UX).

- Explicit per-run consent and data categories.
- Allowlisted metadata only for hosted requests in metadata-only mode.
- BYOK secrets write-only and never present in the guest.
- ToolGateway deterministic authorization and per-call capability checks.
- Core test mode remains independent of model credentials.
- No hosted provider call if consent/policy is absent; no direct fallback on provider failure.

## 5. Scope guardrails

Not M1: local-folder connector, multiple VCS, all four language profiles, deep AI, hosted inference, customer BYOK, organization/team membership, GitHub PR checks, dashboard implementation, npm publishing, native installer release, hosted fleet, marketplace, billing, autonomous patch/merge/deploy or 15-user concurrency claim.

Every deferred item must receive an owner, acceptance criteria and dependency after M1. Do not let future scope enter a critical-path PR without an owner-approved change.

## 6. Phase review record

At each gate record:

- exact base and integration commit;
- code paths and contracts changed;
- test commands and pass/fail/skip counts;
- UNIT / MOCKED-INTEGRATION / LOCAL-INTEGRATION / REAL-KVM / OFFLINE-VERIFICATION classification;
- artifacts and SHA-256 digests;
- security/privacy findings and owners;
- compatibility and rollback evidence;
- scope changes and human decision.

The main programme index is [Agent Workspace README](README.md).
