# Milestone 1 — Native CLI → Firecracker/KVM → Independently Verified Receipt

**Priority:** P0  
**Target:** Day 25 — 23 December 2026  
**Status:** Acceptance specification; implementation and KVM evidence are not claimed by this document  
**Implementation owner:** DeepSeek  
**Backend/API owner:** GPT-6 Luna  
**CLI contract/connector owner:** GLM  
**Independent security test owner:** MiniMax  
**Frontend preparation owner:** Gemini (design only)  
**Final authority:** human product owner

## 1. Exact exit outcome

A user submits one exact GitHub commit with the native Go `workflo` CLI. The user authenticates using the existing device authorization flow and the control plane resolves the user's existing project scope. The FastAPI control plane atomically creates a run, attempt and outbox intent with an idempotency key. A separately enrolled customer-controlled Linux x86_64 KVM runner claims a fenced attempt. The current Python Firecracker host under `worker/` is connected through a narrow M1 adapter and provisions a fresh Firecracker microVM. The host acquires the exact GitHub commit, verifies the source snapshot digest, runs one pinned Python/pytest profile in the guest, captures bounded evidence, independently verifies teardown, signs the canonical receipt and returns evidence metadata. The CLI verifies the receipt offline on a clean network-disconnected machine.

The three outcome axes remain independent:

- **Execution:** whether infrastructure lifecycle completed.
- **QA:** whether pytest passed, failed or was not run.
- **Trust:** whether source, evidence, signature and host teardown are verified.

A failing test can produce a valid receipt. A test pass cannot override a trust failure.

## 2. M1 architecture decisions — no ambiguity

1. **Go CLI is required.** It must run `--help`, `--version`, `doctor`, `run`, `status`, `cancel` and `verify` without Python or Node being installed.
2. **FastAPI remains.** Luna adds a separately versioned M1 API. Existing V1 routes/auth behavior remain compatible.
3. **Existing Python Firecracker host is the M1 host implementation.** This follows ADR-0024's incremental runner migration. DeepSeek connects and hardens the existing implementation; no second Firecracker manager and no mandatory Go host rewrite in this 25-day critical path.
4. **Go runner migration is staged after M1.** A Go runner implementation must later pass the identical contract suite and real KVM Gate B before replacement. It must not be represented as complete during M1.
5. **One existing personal project scope.** Luna adapts the current OAuth principal/project relationship; no org membership, invitations or team-role schema is required for this slice.
6. **One GitHub source and one pytest profile.** Full SHA, source manifest and digest are mandatory. Private-repository verification is included when an authorized test installation is available; lack of that fixture must be recorded, never simulated.
7. **One runner, one fresh VM per attempt.** No VM reuse or strict-to-development fallback.
8. **Existing canonical source, guest, lifecycle and Receipt V5/DSSE contracts are reused.** No receipt redefinition.
9. **No model/provider is needed.** M1 core works without API keys for AI or hosted inference.
10. **Gemini does not build production dashboard functionality until M1 is signed accepted.**

## 3. Included

- Native Go CLI skeleton and the six M1 commands.
- Existing device-flow human authentication and project-scoped authorization.
- Versioned M1 run, runner and evidence API operations.
- Durable idempotent run + attempt + outbox admission.
- Runner enrollment, heartbeat, claim/lease, fencing, state/completion and revoke.
- Strict dispatch to the existing Firecracker host adapter; legacy `SandboxExecutor` is not used for M1 strict runs.
- One customer-controlled Linux x86_64 KVM host.
- One pinned Firecracker/jailer and guest kernel/rootfs.
- Exact GitHub repository + full immutable commit ID + source digest.
- One pinned Python/pytest profile and bounded structured argv.
- Fresh microVM with CPU/RAM/disk/PID/time/output limits and deny-by-default network.
- Typed guest/host protocol with run/attempt/sandbox identity, nonce, sequence and size bounds.
- Bounded logs, test report, evidence manifest and hashes.
- Independent host-side teardown verification for all eight MicroVM checks.
- Canonical signed receipt and local offline verifier.
- M1 positive/negative test matrix and hashed evidence packet.

## 4. Explicitly excluded

- Go host full migration and removal of Python reference.
- Dashboard production implementation.
- Local-directory connector, multi-VCS and all four language profiles.
- Deep AI, agentic browser exploration, BYOK and hosted inference.
- Organization creation, memberships, invitations and multi-role RBAC.
- GitHub PR/check webhook automation.
- Public npm/pnpm/Bun publishing and production installer signing workflow.
- 15-user/45-submission load claim, multi-runner fair scheduling and hosted fleet.
- Autonomous patching, repository writes, merge, deploy, billing or marketplace.
- macOS/Windows strict local runner; clients may use a remote eligible Linux/KVM runner.

## 5. Required execution sequence

1. CLI parses and validates input. It does not execute repository-provided commands on the user's host.
2. Resolve the GitHub ref to a full object ID. Display the immutable SHA before submission.
3. Authenticate the human principal and resolve project scope server-side.
4. Submit source identity, profile, policy and required idempotency key.
5. Control plane atomically creates run + attempt + outbox.
6. Enrolled runner claims one active, expiring, fenced assignment.
7. Runner-side source broker acquires only the pinned revision; short-lived GitHub credentials remain host-side.
8. Validate canonical inventory/digest; enforce path, symlink, submodule, LFS, file count and byte limits.
9. Validate host eligibility and pinned artifacts; boot one fresh Firecracker microVM.
10. Authenticate guest handshake and reject stale, oversized, malformed, replayed or cross-attempt messages.
11. Execute only the approved profile's structured argv in the guest.
12. Collect bounded report, output, lifecycle and evidence hashes.
13. Shut down and independently probe all required host resources.
14. Sign only after trusted host verification; retain canonical signed bytes unchanged.
15. Download/copy receipt, evidence and trust anchor to a clean machine; verify offline.
16. Reproduce from a clean checkout and archive the full evidence packet.

## 6. CLI acceptance contract

Illustrative invocation; final spelling is frozen by DeepSeek + GLM on D2:

```bash
workflo doctor

workflo run \
  --repo https://github.com/OWNER/REPO \
  --ref FULL_COMMIT_OBJECT_ID \
  --profile python-pytest@PINNED_VERSION \
  --runner RUNNER_ID \
  --idempotency-key UNIQUE_VALUE \
  --output-dir ./workflo-artifacts

workflo status RUN_ID

workflo verify --offline \
  --receipt ./workflo-artifacts/receipt.json \
  --evidence ./workflo-artifacts/evidence \
  --trust-key ./trusted-workflo-key.pem
```

Semantics are fixed even if command spelling changes:
- full source identity is visible and immutable;
- runner choice is explicit or resolved by a server-authorized eligible pool;
- states distinguish queued/admitted/claimed/running/completed/rejected/cancelled/incomplete;
- execution, QA and trust are separate;
- verification performs no network call;
- exit codes distinguish usage, auth, admission, execution, QA and trust;
- no successful QA result can override a failed receipt verification.

## 7. Independent acceptance matrix

| ID | Scenario | Required outcome |
|---|---|---|
| M1-01 | Valid pinned commit, passing pytest fixture | Real VM, bounded evidence, clean teardown, offline-valid receipt |
| M1-02 | Same fixture with deterministic failing test | QA failed; execution/trust accurately represented; receipt remains valid only if trust evidence passes |
| M1-03 | Branch moves after SHA resolution | Run remains bound to original full SHA |
| M1-04 | Invalid SHA/repository permission denied | Rejected before VM provision |
| M1-05 | Guest attempts forbidden host filesystem/network access | Denied, logged as bounded evidence, host unchanged |
| M1-06 | Unknown/oversized/replayed/cross-attempt guest message | Denied and audited |
| M1-07 | Guest/VMM/host process crashes | Explicit infrastructure/trust failure; no false clean receipt |
| M1-08 | One teardown probe is unknown/failed | Trust cannot be VERIFIED_CLEAN |
| M1-09 | Evidence changed after signing | Offline verifier fails |
| M1-10 | Wrong key, altered receipt or non-canonical encoding | Offline verifier fails |
| M1-11 | Duplicate run request/idempotency key | One run intent and no duplicate active VM |
| M1-12 | Runner lease expires | Attempt fenced; retry uses new attempt and fresh VM |
| M1-13 | Verification with network disabled | Offline verification still succeeds |
| M1-14 | macOS/Windows CLI client | Client works; remote eligible Linux/KVM runner is required |
| M1-15 | No KVM / unsupported host | Strict run rejected; no Docker/bwrap/host fallback |

The eight MicroVM teardown checks are the existing canonical requirements: VMM exited, VM stopped, cgroups removed, netns removed, disk destroyed, sockets closed, capabilities expired and process scope empty. Each must be host-observed; guest self-report is not proof.

## 8. Agent responsibility in M1

- **DeepSeek:** Go CLI, core API client, strict workflow integration to current Python Firecracker host adapter, evidence/receipt handoff, offline verifier.
- **GLM:** command/flag/output/error contract, GitHub ref/SHA connector, safe source-selection UX and CLI integration tests. Package publishing remains post-M1.
- **MiniMax:** threat model, policy tests, adversarial fixtures, independent tests/review for source, network, resource, protocol, lease, teardown and receipt failure.
- **GPT-6 Luna:** additive M1 OpenAPI + FastAPI implementation, existing user/project auth adaptation, idempotent run/outbox, runner enrollment/claim/heartbeat/completion, host dispatch bridge, evidence metadata and PostgreSQL tests.
- **Gemini:** design tokens, IA, component contracts, synthetic prototype and accessibility test plan only until acceptance.

Full ownership, task IDs, file paths and day-by-day exit criteria are in each agent runbook and [M1 25-day execution plan](M1-25-DAY-EXECUTION-PLAN.md).

## 9. Evidence packet

Store a versioned packet with:
- integration commit SHA;
- CLI binary/build metadata/SHA-256;
- runner/host component version and SHA-256;
- host OS/kernel/architecture and KVM proof;
- Firecracker/jailer versions and binary digests;
- guest kernel/rootfs digests;
- source repo, full commit, inventory and source digest;
- RunSpec/assignment/protocol/policy versions and digests;
- resource/network policy and observed enforcement;
- bounded guest/host protocol transcript (no secrets);
- test report and bounded outputs;
- all eight teardown probes;
- receipt bytes, signer ID/fingerprint and receipt digest;
- offline verifier output from a clean network-disabled environment;
- M1-01..M1-15 result matrix, skipped/blocked tests, findings and waivers.

No GitHub access token, provider secret, private key, uncontrolled source archive or secret-bearing environment dump belongs in the evidence packet.

## 10. Go/no-go

M1 is **ACCEPTED** only when all mandatory cases pass on the exact release candidate, real KVM is proven, the offline verifier passes, no critical/high unresolved security/privacy defect remains, V1 compatibility is retained and the human owner signs the acceptance record.

Mocks may support development but cannot close KVM, teardown or offline-verification rows. A missing host, signer or private source fixture is reported as BLOCKED, not silently waived. No calendar deadline overrides this rule.

## 11. Dashboard gate

Gemini may prepare design artifacts using synthetic data before M1. Production dashboard implementation begins only after a signed M1 record includes exact CLI/host commits, host and guest digests, full source SHA/digest, receipt and verifier output, teardown evidence, security report, residual-risk dispositions and owner approval.
