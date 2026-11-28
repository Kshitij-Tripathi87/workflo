# Agent 01 — DeepSeek V4.1 Flash-1017
## Native Go CLI Core, Customer Runner and Execution Runtime

**Workstream:** Critical path — native client and customer execution plane  
**Primary branch:** `agent/deepseek-native-cli-runner`  
**Implementation owner:** DeepSeek V4.1 Flash-1017  
**Primary reviewers:** GPT-6 Luna (API/protocol), MiniMax M3.1 Flash (security), GLM-5.3 Flash (command/connector integration), human owner (architecture and release approval)  
**Authority:** ADR-0022 (accepted Firecracker/KVM boundary), ADR-0024 (accepted Go CLI/runner decision), accepted M1 milestone specification, approved API/runner protocol revision.

---

## 1. Assignment and expected result

Build the native Go Workflo executable and the customer-runner host agent in controlled stages. The executable is named `workflo`; it must start without Python, Node.js, a virtual environment or a model runtime. The runner is a separate long-lived Go process that connects outbound to the control plane and executes only authenticated, admitted attempts.

Your work is the systems backbone; you do not own all CLI commands, connectors, security policy, control-plane business logic or dashboard UX. The interfaces between those workstreams must be agreed before parallel implementation begins.

**First complete outcome (M1):** from a supported client, submit one exact GitHub commit through the native CLI; admit and dispatch it to a customer-controlled eligible Linux x86_64 KVM runner; create one fresh Firecracker microVM; execute one pinned deterministic Python/pytest profile; collect bounded evidence; independently verify teardown; create a valid signed receipt; and verify that receipt plus evidence offline from a separate clean environment.

The M1 result is a deterministic execution milestone. It does **not** mean Deep AI, Security, the four-language launch matrix, dashboard or managed execution are complete. Those are later beta workstreams and release gates.

## 2. Why this model owns this work

DeepSeek V4.1 Flash-1017's published model card reports:
- DeepSWE v1.1: **77.0**
- Terminal-Bench 4.0: **42.3**
- NL2Repo-Bench: **68.2**
- Automation-Bench v1.0.6: **60.5**

The same exact-model source identifies the DeepSWE harness as Mini-SWE-V2 and Terminal-Bench 4.0 as Claude Code. The result is a routing prior for repository engineering and terminal implementation, not proof of correctness or safe behavior.

Source: https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash-1017

## 3. Authority, ownership and file boundaries

### 3.1 Files/directories owned by DeepSeek

| Path | Ownership |
|---|---|
| `apps/workflo-cli-go/cmd/workflo/` | Native executable entry point, bootstrap and version metadata |
| `apps/workflo-cli-go/internal/app/` | Core application lifecycle and command invocation interface |
| `apps/workflo-cli-go/internal/runtime/` | Local client/runtime orchestration, cancellation and process supervision |
| `apps/workflo-cli-go/internal/api/` | Typed HTTP/API client, auth transport abstraction and retry policy |
| `apps/workflo-cli-go/internal/config/` | Core config loader, version handling and validation interface; command UX belongs to GLM |
| `apps/workflo-cli-go/internal/output/` | Stable output primitives and JSON/TTY renderer interface |
| `apps/workflo-cli-go/internal/platform/` | OS/architecture/process/credential-store interfaces and platform adapters |
| `apps/workflo-runner-go/cmd/workflo-runner/` | Runner daemon entry point |
| `apps/workflo-runner-go/internal/agent/` | Runner lifecycle, startup, drain and shutdown |
| `apps/workflo-runner-go/internal/claim/` | Claim, lease, heartbeat and assignment validation |
| `apps/workflo-runner-go/internal/firecracker/` | Firecracker lifecycle adapter |
| `apps/workflo-runner-go/internal/jailer/` | Jailer configuration and invocation adapter |
| `apps/workflo-runner-go/internal/guestchannel/` | Typed vsock protocol client and message fencing |
| `apps/workflo-runner-go/internal/resources/` | Resource reservation, measurement and limit application |
| `apps/workflo-runner-go/internal/network/` | Host-side egress/network lifecycle adapter |
| `apps/workflo-runner-go/internal/teardown/` | Expected-resource inventory and host teardown probes |
| `apps/workflo-runner-go/internal/evidence/` | Host-observed evidence collection and assembly |
| `packages/workflo-protocol-go/` | Generated/validated Go bindings and protocol compatibility tests only |

A task contract may narrow these directories to exact files. Do not assume directory ownership grants permission to change shared contracts.

### 3.2 Shared and protected paths

| Path | Rule |
|---|---|
| `apps/workflo-cli-go/internal/commands/` | GLM owns command handlers, flags and command help |
| `apps/workflo-cli-go/internal/connectors/` | GLM owns GitHub/local connector adapters |
| `apps/workflo-cli-go/internal/source/` | Shared interface: DeepSeek owns immutable source/snapshot primitives only after interface review; GLM owns provider/local source acquisition adapters |
| `profiles/` | GLM owns Python/Node/Go/Java profile manifests and detection |
| `packages/npm-workflo/`, `scripts/release/install/` | GLM owns package/installer distribution |
| `packages/workflo-policy-go/`, `security/`, `tests/security/`, `tests/privacy/` | MiniMax owns policy/test source; DeepSeek supplies testable host interfaces |
| `apps/control-plane/`, migrations, `db/rls/` | GPT-6 Luna owns backend implementation |
| `apps/dashboard/` | Gemini owns frontend implementation |
| `packages/workflo-schema/` | Canonical Pydantic contract source; read-only to DeepSeek unless the human owner authorizes a schema task |
| `worker/` | Existing Python host is the compatibility/reference path; no mass rewrite or second production manager |
| `apps/worker-engine/` | Existing guest engine remains fit-for-purpose; guest migration requires a separate task |
| `packages/contracts/` | TypeScript compatibility mirror; do not create a competing state model |

### 3.3 Must never do

- Do not rewrite the FastAPI control plane in Go.
- Do not change lifecycle, RunSpec, policy, assignment, evidence or receipt semantics without an approved versioned contract.
- Do not build a generic shell, host filesystem, Docker socket or arbitrary privileged operation into the guest protocol.
- Do not implement a Docker/bwrap/native-process fallback for strict production execution.
- Do not send GitHub tokens, BYOK keys, host credentials, signing keys or source code to a guest or hosted model.
- Do not sign or declare a verified-clean receipt before independent host-side teardown/evidence validation.
- Do not move/delete the Python CLI, `worker/`, guest engine or canonical schema during migration.
- Do not edit GLM command handlers/package manifests, MiniMax policy rules, GPT-6 backend logic or Gemini dashboard code except through a reviewed interface task.
- Do not deploy production or operate customer infrastructure.

## 4. System architecture you must preserve

### Client process
- Parses requests through a command interface owned jointly with GLM.
- Resolves config and local platform requirements.
- Uses a typed API client, stable errors and idempotency.
- Displays exact source SHA, profile, stages, runner target and effective policy before submission.
- Never reaches directly into PostgreSQL or the runner's local admin socket.
- Supports TTY and machine-readable JSON modes.

### Runner process
- Enrolls with a one-time, expiring token and obtains a distinct runner workload identity.
- Claims a lease and verifies signed/expiring attempt assignment.
- Reports hardware/runtime capability and reserves resources before accepting work.
- Uses one attempt identity and one sandbox identity per run attempt.
- Performs source acquisition through GLM/GPT-6-approved host-side interface; GitHub credentials do not cross into the guest.
- Runs the existing approved Firecracker/jailer boundary and typed guest channel.
- Collects host-observed lifecycle/evidence and independently verifies teardown.
- Sends bounded metadata/evidence references to the control plane; does not trust guest assertions for trust state.

### Guest
- Is a fresh Firecracker microVM per attempt.
- Receives the exact immutable source snapshot, pinned image and declared argv.
- Has bounded CPU, memory, disk, PID, output and wall-clock budgets.
- Receives only explicit capabilities.
- Has no host shell, host filesystem, Docker socket, signing key, runner identity secret, GitHub token or generic outbound network.

## 5. Delivery sequence and task contracts

Do not start later tasks merely because earlier code compiles. Each work package has a separate PR, owner, reviewer and acceptance record.

### DS-00 — Workflo calibration and source audit
**Goal:** establish what is already implemented before creating a new Go surface.

Actions:
1. Record the current main SHA, exact Go version, build host and available cross-compilation targets.
2. Read ADR-0022, ADR-0024, M1 acceptance, API contract freeze, CLI specification, repository structure, current Python CLI, npm shim, schema, control plane dispatch, `worker/`, guest engine and current CI.
3. Inventory every existing command/flag/config value/output/exit code and caller of the Python CLI.
4. Trace the existing execution path from CLI to API/outbox/dispatcher/worker/guest/evidence/receipt.
5. Trace every host process/file/network operation in the existing worker and classify it as enforced, requested, mocked, development-only or unverified.
6. Record a fresh baseline for Go/Python/CLI/worker suites and all skips.

Deliverables: `DS-00-current-state.md`, CLI compatibility table, source flow, host operation inventory, test baseline and blockers.

Acceptance: no source edits; every claim cites a path/symbol or executable test. Do not re-use old November 22 task counts as current status.

### DS-01 — Go module and integration architecture
**Goal:** establish the Go implementation seam without duplicating existing runtime behavior.

Actions:
1. Define module boundaries for `apps/workflo-cli-go`, `apps/workflo-runner-go` and `packages/workflo-protocol-go`.
2. Choose dependencies deliberately; record package, exact version, licence, reason and alternatives.
3. Establish Go toolchain version and workspace/module layout consistent with repository build.
4. Define interfaces that GLM command handlers and connectors call.
5. Define API transport and runner client interfaces against GPT-6's approved OpenAPI/runner protocol.
6. Define how Go uses MiniMax-owned policy decisions without copying the evaluator.
7. Define an incremental adapter to the current Python Firecracker host. No second manager.
8. Record platform build targets, CGO policy, process model and logging/redaction standard.
9. Submit an architecture PR and obtain owner approval before expanding the implementation.

Acceptance: no conflicting interfaces, documented import graph, generated/validated contract decision, one owner per shared interface and migration rollback.

### DS-02 — Native binary skeleton
**Goal:** build a useful native executable with no Python/Node bootstrap.

Implement:
- `workflo --help`, `--version`, `doctor`;
- build metadata (version, commit, toolchain, platform, protocol versions);
- process signal handling and graceful cancellation;
- config discovery and versioned parsing interface;
- stable error taxonomy;
- JSON and human output modes;
- request/correlation ID generation and propagation;
- structured logs with redaction and bounded fields;
- timeout and cancellation primitives;
- OS/architecture capability report.

Acceptance:
- Linux x86_64, macOS arm64/x64 and Windows x64 builds compile;
- all target binaries start and run help/version/doctor on actual or valid hosted target runners;
- CLI startup requires neither Python nor Node;
- invalid config and unsupported platform fail deterministically;
- TTY and non-TTY snapshots pass;
- logs contain no secret values.

### DS-03 — Core API client and command host
**Goal:** provide the typed, stable substrate used by GLM's command handlers.

Implement:
- base URL and TLS verification;
- human-user auth transport interface;
- request ID/correlation header;
- idempotency key on mutation;
- bounded response body and timeout;
- retry only for safe requests or mutations with an idempotency key;
- exponential backoff/jitter with maximum elapsed time;
- pagination primitives;
- server Retry-After handling;
- structured error envelope parser;
- status/attempt separation;
- server version and protocol compatibility check.

Acceptance:
- fake API tests cover 200/201/202, 400, 401, 403, 404, 409, 422, 429, 500/502/503, timeout, connection reset and oversized body;
- duplicate submission returns the existing run or a deterministic conflict;
- client never retries a non-idempotent operation blindly;
- TLS validation is never disabled in production.

### DS-04 — Local runtime and cancellation model
**Goal:** make CLI commands predictable across three client OS families.

Implement:
- context propagation and cancellation tree;
- child-process lifecycle only for explicitly permitted local helper commands;
- no repository-controlled host command execution in preflight/detection;
- bounded temporary files and cleanup;
- safe path normalization and symlink handling;
- platform signal handling;
- shutdown order and timeout;
- no orphan process on CLI exit.

Acceptance: cancellation tests on Linux/macOS/Windows, path edge-case tests, process interruption tests, no host-side project setup hooks.

### DS-05 — Run and attempt lifecycle adapter
**Goal:** use the approved API/run contracts without redefining them.

Implement:
- typed client request construction from approved RunSpec bindings;
- exact source revision binding;
- profile/policy/runtime digest references;
- run ID and attempt ID separation;
- accepted/queued/admitted/running/completed/rejected mapping;
- execution, QA and trust outcomes as separate fields;
- status polling/streaming via approved interface;
- idempotent cancel request;
- bounded logs and evidence metadata access;
- offline verification invocation path.

Acceptance: golden JSON/fixture parity with Python; no invented enum/state; cancellation is not displayed as VM-stopped until host evidence confirms; no successful test can override trust failure.

### DS-06 — Runner enrollment, claim and service lifecycle
**Goal:** create the customer runner control process that accepts only authentic, eligible assignments.

Implement:
- one-time enrollment bootstrap;
- runner identity/certificate storage and rotation interface;
- capability inventory (OS, architecture, kernel, KVM, Firecracker/jailer, image digests, resource availability);
- online/offline/draining/revoked state;
- outbound runner registration and heartbeat;
- claim request with bounded wait;
- lease expiry and fencing token verification;
- duplicate claim prevention;
- safe process/service startup/restart;
- clean shutdown and drain.

Acceptance: expired/revoked enrollment denied; two runners cannot own the same attempt; stale fencing token rejected; runner restart does not duplicate active execution; no public admin endpoint exposed by default.

### DS-07 — M1 deterministic execution bridge
**Goal:** complete the first real vertical slice using the current approved Firecracker lineage.

Actions:
1. Confirm current Python host capabilities and gaps by running actual code/tests.
2. Use the existing worker implementation as the single production candidate while building a typed Go integration seam.
3. Do not start a duplicate Firecracker manager merely to make the code appear Go-native.
4. Wire admitted assignment → runner claim → source acquisition → VM provision → guest execution → evidence → teardown → receipt verification.
5. Keep the M1 profile to one pinned deterministic Python/pytest workload.
6. Mark all local/dev executor paths development-only; strict request must fail closed when KVM is unavailable.

Acceptance: all M1-01…M1-15 cases in the milestone specification, with real KVM for the strict cases. No mocks count for VM boot, egress enforcement, teardown or offline receipt acceptance.

### DS-08 — Host resource and Firecracker lifecycle migration
**Goal:** incrementally replace the Python runner host only after the Go control/contract seam is stable.

Work sequence:
1. map current Firecracker/jailer invocation inputs and outputs;
2. pin Firecracker and jailer binaries by digest/version;
3. pin kernel/rootfs and guest image manifest;
4. model resource reservation and cleanup inventory;
5. implement host operations behind narrow typed interfaces;
6. create a fresh writable disk per attempt;
7. implement jailer/cgroup/seccomp/filesystem/network setup;
8. enforce vCPU/RAM/disk/PID/output/time limits;
9. handle launch errors and partial provisioning rollback;
10. implement graceful shutdown, bounded grace and force termination;
11. verify all expected host resources were removed;
12. run parity against Python implementation;
13. switch production ownership only after real Gate B and owner approval.

Acceptance: no overlapping production managers; Python compatibility remains until Gate B and receipt parity pass.

### DS-09 — Guest channel and protocol hardening
**Goal:** every host/guest request is authenticated, typed and attempt-bound.

Requirements:
- protocol version negotiation;
- run ID, attempt ID, sandbox ID and policy digest in every relevant exchange;
- monotonic sequence number;
- nonce/expiry and replay prevention;
- bounded message length and field size;
- strict schema validation;
- unknown critical operation rejected;
- no arbitrary host shell, path or network operation;
- guest cannot report a host teardown pass;
- timeout and disconnect behavior is deterministic.

Acceptance: wrong-run, wrong-attempt, stale nonce, replay, oversized payload, unknown operation, malformed JSON and guest restart cases fail closed and are audited without logging sensitive payload contents.

### DS-10 — Source and evidence boundaries
**Goal:** ensure the VM receives the exact permitted source snapshot and produces bounded evidence.

Actions:
- integrate with GLM connector source interface and MiniMax source policy;
- accept only full commit identity for M1;
- validate repo/install identity and source acquisition authorization;
- enforce submodule/LFS policy explicitly;
- build canonical file manifest/digest;
- reject path traversal, symlink escape, hardlink ambiguity and oversized tree;
- deliver an immutable guest-visible source artifact;
- remove source acquisition credential before guest start;
- collect host/guest evidence separately;
- validate output size, file count, artifact types and hash manifest;
- keep source, secret and raw log data out of hosted prompts.

Acceptance: source hash fixtures, changed branch after admission, malicious symlink/archive, oversize source, secret canaries and malformed evidence reports.

### DS-11 — Receipt and offline verifier integration
**Goal:** preserve historical compatibility and prove the M1 receipt path.

Actions:
- consume canonical Python contract and approved Go bindings;
- maintain v1-v4 legacy receipt verification;
- reconcile v5 writer/verifier status against actual current code;
- preserve canonical JSON encoding and duplicate-key rejection rules;
- verify envelope signature, trust anchor and signer identity;
- verify run/attempt/source/policy/image/evidence binding;
- distinguish signature valid from evidence complete and trust verified;
- produce a deterministic verifier report and nonzero exit code on any invalid binding.

Acceptance: valid, tampered, wrong-key, missing artifact, wrong source SHA, altered manifest, replayed attempt and incomplete teardown fixtures; offline run succeeds without control-plane/provider connectivity.

### DS-12 — Cross-platform build and runtime acceptance
**Initial client targets:** Linux x86_64, macOS arm64/x64, Windows x64.  
**Runner target:** eligible Linux x86_64 KVM first. Linux ARM64 and Windows ARM64 are conditional, not assumed.

Actions:
- prefer `CGO_ENABLED=0` for CLI if dependencies allow;
- inspect actual binary dynamic dependencies before calling it static;
- build reproducibly in CI;
- verify artifact checksums and provenance;
- test spaces/unicode paths, shell quoting and Ctrl-C;
- test credential store adapter and fallback disclosure;
- test update/rollback interface with GLM packaging;
- ensure Mac/Windows client never reports local strict runner eligibility.

Acceptance: clean machine installation/run on every claimed target; no hidden Python dependency; runner eligibility and unsupported profiles accurately shown.

### DS-13 — Operational performance and reliability
Measure:
- CLI startup and memory;
- API latency/retry behavior;
- runner startup and heartbeat overhead;
- claim/lease timing;
- VM provision and teardown duration;
- cancellation-to-verified-termination delay;
- goroutine count and leak tests;
- process/file descriptor limits;
- bounded output/evidence memory;
- concurrency at 1/5/10/15 users and runner slots 1/2/4 on an owned KVM lab.

The 15-user/45-submission test measures durable admission/queue behavior. Do not claim 45 simultaneous VMs. Any VM throughput claim must state runner hardware, kernel, Firecracker version, guest image and workload profile.

Acceptance: p50/p95 and resource measurements with exact environment, no unbounded queue/goroutine growth, lease recovery and no cross-run evidence mix-up.

## 6. Required test matrix

| Area | Minimum tests | Acceptance environment |
|---|---|---|
| CLI core | help/version/doctor/config, invalid flags, TTY/JSON | Linux/macOS/Windows |
| API client | auth, timeout, 429, retries, idempotency, pagination | fake server + real control plane |
| process | cancellation, child cleanup, restart | OS-specific CI |
| runner | enroll, claim, lease, heartbeat, drain, revoke | synthetic test control plane |
| source | full SHA, branch movement, symlink/archive/submodule/LFS policy | synthetic repositories |
| VM | boot, isolation, resource caps, egress, crash, force stop | real KVM for Gate B |
| guest protocol | replay, wrong attempt, oversized, malformed, unknown op | unit + real guest |
| evidence | size/hash/schema/tamper/attempt binding | unit + integration |
| teardown | VMM/jailer/cgroup/network/disk/vsock/resource inventory | real KVM for Gate B |
| receipt | legacy versions, valid/tampered/wrong-key/offline | clean separate verifier machine |
| distribution | OS/architecture builds, no Python dependency | clean machines with GLM packaging |
| performance | 15 clients/45 submissions, runner saturation/recovery | customer-owned test environment |

## 7. Required handoffs

### To GLM
- stable command-host interface;
- API client method surface;
- config interface and error types;
- source connector interface and source snapshot contract;
- version/target artifact naming and checksums;
- compatibility matrix for previous CLI behavior.

### To GPT-6 Luna
- exact OpenAPI and runner protocol gaps;
- required endpoint names/fields and error mapping;
- request/idempotency/fencing behavior;
- evidence/receipt references;
- API contract tests and client expectations.

### To MiniMax
- host/guest operation list;
- policy decision request/response schema;
- exact test hooks for cgroup/egress/resource/teardown enforcement;
- all negative tests and known unobservable gaps.

### To Gemini
- stable CLI command behavior and actual API states for UI integration;
- status, error, event and evidence fields;
- runner capability model;
- limitations that must be exposed in UI.

## 8. Mandatory handoff report

Every PR must include:
- task ID and milestone;
- base SHA and result SHA;
- model identifier and toolchain version;
- changed file inventory and reason;
- commands executed and exit codes;
- pass/fail/skip/not-run counts;
- host OS/architecture and KVM availability;
- exact real vs mocked evidence classification;
- benchmark/model cost/latency only when actually visible;
- compatibility impact;
- security/privacy impact;
- known limitations and follow-on task IDs.

## 9. Stop conditions

Stop and mark BLOCKED if a protocol/schema change is required but unapproved; the task crosses another agent's path boundary; guest requires a host capability not in the allowlist; source token would enter the guest; KVM/image/jailer prerequisites are missing; teardown cannot be independently observed; strict mode would fall back to a development executor; a compatibility change would invalidate old receipts/config without migration; or a required test is being skipped/softened to get a green result.

## 10. Definition of done

The native Go CLI and customer-runner path produce one reproducible M1 run on real customer-owned Linux x86_64 KVM, execute the pinned deterministic profile, preserve source identity, enforce host/guest boundaries, independently verify cleanup, issue a correctly bound signed receipt and pass offline verification on a clean machine. The old Python path remains intact until the Go migration is independently accepted.
