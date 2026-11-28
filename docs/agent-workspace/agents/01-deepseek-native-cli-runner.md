# Agent 01 — DeepSeek V4.1 Flash-1017
## Native Go CLI Core, Customer Runner and Execution Runtime

**Workstream:** CLI/runtime — critical path  
**Branch:** agent/deepseek-native-cli-runner  
**Primary owner:** DeepSeek V4.1 Flash-1017  
**Reviewers:** GLM for command integration; MiniMax for security review; GPT-6 Luna for API/contract integration; human owner for architecture and release approval.

## 1. Why this model owns this work

The DeepSeek V4.1 Flash-1017 model card reports:

- DeepSWE v1.1: **77.0**
- Terminal-Bench 4.0: **42.3**
- NL2Repo-Bench: **68.2**
- Automation-Bench v1.0.6: **60.5**

Within the exact model set being assigned, 77.0 is the strongest cited DeepSWE v1.1 result, and 42.3 is higher than MiniMax's 38.1 on the same Terminal-Bench 4.0 comparison table. DeepSeek reports Mini-SWE-V2 for DeepSWE and Claude Code as the Terminal-Bench 4.0 harness.

Primary source: https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash-1017

**Routing hypothesis:** strongest candidate for long-horizon repository engineering, terminal-oriented implementation and multi-file system work. This does not make it the security authority or contract owner.

## 2. Mission

Build the native Workflo CLI core and customer runner foundation in Go. Deliver a cross-platform executable named workflo and a customer-managed Linux runner that can execute a policy-bound run through the existing Workflo lifecycle.

The agent must not optimize for code volume. It must produce a small number of integrated, reproducible vertical slices.

## 3. Owned paths

### Primary implementation ownership
- apps/workflo-cli-go/
  - cmd/workflo/
  - internal/app/
  - internal/runtime/
  - internal/api/
  - internal/config/ (core schema/loading only)
  - internal/output/
  - internal/update/ (binary update safety, not package manifest)
- apps/workflo-runner-go/
  - cmd/workflo-runner/
  - internal/agent/
  - internal/claim/
  - internal/firecracker/
  - internal/jailer/
  - internal/guestchannel/
  - internal/resources/
  - internal/network/
  - internal/teardown/
  - internal/evidence/
- packages/workflo-protocol-go/ (generated or parity-validated bindings only)
- current worker/ Python host source only for read-only audit, compatibility adapters and approved staged migration PRs.

### Must not own
- apps/control-plane/ backend business logic and DB migrations (GPT-6 Luna).
- apps/dashboard/ (Gemini).
- packages/workflo-policy-go/, security/ and tests/security/ (MiniMax).
- CLI command handlers, GitHub connector and package distribution files owned by GLM:
  - apps/workflo-cli-go/internal/commands/
  - apps/workflo-cli-go/internal/connectors/
  - packages/npm-workflo/
  - profiles/
- canonical Pydantic/TypeScript lifecycle, RunSpec, policy, receipt and evidence semantics without owner approval.

## 4. Operating boundary and authority

You may:
- design and implement the Go binary, core command dispatcher interfaces and runtime client;
- implement a host runner that only calls the approved Firecracker/jailer APIs;
- implement typed guest/host protocol clients and host lifecycle probes;
- write unit/integration tests for owned code;
- add Go module/workspace configuration when the architecture proposal is accepted;
- propose API/contract improvements to the human owner and GPT-6 Luna.

You may not:
- grant yourself permission to run arbitrary host commands;
- expose a generic shell, Docker socket, host filesystem or privileged API to the guest;
- add an automatic Docker/bwrap fallback for strict mode;
- sign or attest the receipt before trusted teardown verification;
- change the meaning of an existing lifecycle state or receipt claim;
- store GitHub/BYOK credentials in guest environment variables;
- operate on production hosts/secrets or deploy to production;
- make a broad rename/move of worker/ or existing Python packages;
- silently change native install package names or public CLI flags owned by GLM.

## 5. Recommended Go architecture

Use a single Go codebase family rather than separate language runtimes for every host function.

Suggested responsibilities:
- CLI process: command lifecycle, config, auth client, run planning, status polling, receipt verification interface and JSON output.
- Runner process: authenticated claim/heartbeat, assignment validation, capacity reporting, Firecracker lifecycle, guest channel, host evidence and teardown.
- Protocol library: generated and version-checked structs/models from accepted contracts.
- Policy library: consumed from the MiniMax-owned package; do not fork or duplicate the policy evaluator.

Avoid CGO unless a required library makes it unavoidable. Every CGO/native dependency needs a documented cross-platform and supply-chain review.

Go is selected to simplify static distribution and the cross-platform build matrix. The language is not itself the sandbox. KVM, Firecracker, jailer, kernel controls, network enforcement and independent evidence remain the boundary.

## 6. Work packages

### DS-01 — Repository and execution audit

- Read README, PRODUCT_BOUNDARIES, ADR-0022, Phase 0 reconciliation, P4_ACCEPTANCE, worker/, apps/worker-engine/, apps/workflo-cli/, package shim, schema and dispatch service.
- Produce exact source-to-run data flow and state machine.
- Classify each current component as production candidate, development-only, mock-only, compatibility or unproven.
- Capture exact base commit SHA and command/test inventory.
- Identify all host operations and all existing direct/indirect shell call sites.

**Acceptance:** a file-level architecture map, a list of missing gates, and no code refactor during the audit.

### DS-02 — Go architecture and migration ADR

- Propose Go module boundaries and dependency graph.
- Define CLI-core interface that GLM command handlers will consume.
- Define runner agent interface that GPT-6 API endpoints will consume.
- Define contract-generation/parity flow.
- Define compatibility strategy with Python CLI and worker.
- Record cross-platform build targets and CGO policy.
- Get approval before creating the new Go workspace/module layout.

**Acceptance:** accepted Go migration ADR; no duplicate implementation of the current Firecracker manager is created before the target boundary is agreed.

### DS-03 — Native CLI skeleton

Implement:
- cmd/workflo entrypoint.
- version/build metadata.
- root help/completion plumbing.
- signal handling and graceful cancellation.
- config loading and schema validation.
- OS key-store abstraction (platform-specific adapter interfaces; GLM handles package/installer integration).
- common authenticated HTTP client abstraction.
- typed error taxonomy and structured JSON output contract.
- telemetry disabled by default and no raw source/secret payload.

**Acceptance:** build and unit tests on Linux, macOS and Windows; workflo --help and --version work without Python or Node execution dependencies.

### DS-04 — Run client and lifecycle core

- Consume GPT-6-approved API schemas.
- Resolve RunSpec to a versioned request.
- Require idempotency key on mutating run submission.
- Enforce response size/time limits.
- Distinguish accepted/queued/admitted/running/complete/rejected.
- Keep run and attempt identities separate.
- Support status, cancellation request and event pagination.
- Map canonical execution/QA/trust outcomes without inventing states.
- Implement bounded retry only for safe/idempotent calls.

**Acceptance:** exact golden API fixtures, duplicate POST tests and cancellation/status tests pass against the control-plane integration environment.

### DS-05 — Native runner service

- Add enrollment bootstrap using one-time expiring token.
- Exchange enrollment token for runner workload identity/cert.
- Report capabilities and hardware profile.
- Claim work using lease and attempt identity.
- Heartbeat at bounded interval.
- Respect drain, revoke, pause and offline states.
- Recover expired leases without double execution.
- Expose no inbound public admin endpoint by default.
- Use outbound authenticated control-plane communication.

**Acceptance:** enrollment, claim, heartbeat, lease expiry, revocation, restart recovery and duplicate-claim tests pass.

### DS-06 — Firecracker lifecycle integration

Continue the existing canonical host implementation under worker/ until the approved Go migration milestone. Do not create a second production manager while the old manager is still the only candidate.

Then:
- implement Go host lifecycle behind the existing assignment protocol;
- verify Firecracker/jailer binary versions and hashes;
- verify kernel/rootfs digest allowlist;
- create a fresh writable disk per attempt;
- create host-owned resource/cgroup/network scopes;
- launch through jailer with restricted permissions;
- deliver capabilities over typed vsock only;
- bind every message to run ID, attempt ID, sandbox ID, sequence and nonce;
- reject unknown/oversized/replayed operations;
- enforce vCPU, memory, disk, PID, output and wall-clock limits;
- apply default-deny egress;
- implement graceful shutdown, bounded grace and force termination.

**Acceptance:** real KVM boot and guest workload on exact pinned artifacts. Mocks and capability probes do not pass Gate B.

### DS-07 — Source materialization contract

Work with GLM on GitHub and local source acquisition and GPT-6 on the API contract.

Runner must:
- obtain source at exact full commit SHA;
- validate repository/installation authorization;
- reject unsupported submodule/LFS behavior unless policy explicitly allows it;
- hash a canonical source inventory;
- avoid host working-tree mutation;
- deliver a read-only source artifact to a fresh guest disk;
- remove or expire acquisition capability before guest starts;
- never pass GitHub token into the guest.

**Acceptance:** branch-movement, private-repo scope, malicious symlink, oversized repository, token expiry and source hash tests.

### DS-08 — Guest channel and workload integration

- Use the narrow approved host operations only.
- Implement protocol version negotiation and attempt fencing.
- Reject malformed/unknown operations.
- Ensure guest does not decide host cleanup status.
- Integrate the approved deterministic guest worker first.
- Connect language profile adapters through structured argv and immutable image versions.
- Collect test reports through bounded channels and independently validate hashes/schema on host.

**Acceptance:** same exact test fixture produces deterministic results; malformed reports and wrong-attempt messages fail closed.

### DS-09 — Evidence, teardown and receipt handoff

- Host observes VMM/jailer process removal.
- Verify cgroup, namespace, network, vsock/listener, disk and workspace resources removed.
- Record one of the accepted teardown outcomes.
- Send host evidence and guest evidence separately to the trusted verifier.
- Do not sign before evidence/teardown validation.
- Ensure retry gets a new attempt and a new sandbox identity.

**Acceptance:** teardown fault causes trust failure/incomplete and never produces a false verified-clean receipt.

### DS-10 — Cross-platform client release

- Build Linux x64, macOS arm64/x64 and Windows x64 first.
- Add ARM64 targets only after CI and dependency support exist.
- Verify static/dynamic dependency profile.
- Run install smoke test and CLI command tests on each OS.
- Provide platform/runner eligibility messaging.
- Ensure macOS/Windows client does not claim strict local execution.

**Acceptance:** clean-machine binary executes help/auth/client commands on each claimed OS; no Python dependency.

### DS-11 — Handoff

Deliver:
- Go module map.
- build/release command list.
- runtime lifecycle documentation.
- protocol compatibility matrix.
- KVM acceptance report.
- known limitations.
- migration/deprecation recommendation for Python host/CLI.

## 7. Required test matrix

- CLI core argument and config loading.
- process signal/cancellation behavior.
- API timeout/retry/idempotency.
- token expiry/revocation.
- run/attempt lifecycle parity.
- runner enrollment/claim/lease/heartbeat/recovery.
- real Firecracker boot/guest run/teardown.
- resource/network enforcement.
- wrong attempt/replay/oversize vsock.
- host and guest crash.
- force terminate.
- no source/credential in guest.
- offline receipt compatibility.
- cross-platform binary build/test.

## 8. Performance and scalability

- Runner heartbeat and polling must not hold DB connections while VM runs.
- Work claims are bounded and lease-based.
- Host should reserve CPU/memory/disk before claim acceptance.
- Avoid goroutine-per-event without limits.
- Cap API response, log and evidence sizes.
- Keep local command startup responsive.
- Support 15 CLI clients and 45 burst run submissions at the control-plane contract level; actual VM parallelism is runner capacity-based.
- Benchmark 1, 5, 10, 15 and 30 concurrent VMs only on safe owned KVM infrastructure, recording hardware and guest profile.

## 9. Stop/escalation rules

Stop and ask for owner decision if:
- protocol/schema must change;
- assignment includes generic shell or host paths;
- source credentials must enter guest;
- strict execution would fall back to Docker/bwrap;
- no real KVM host or pinned guest artifacts exist;
- independent teardown evidence cannot be gathered;
- Go migration would require removing current compatibility code before parity;
- platform build requires an unreviewed native dependency.
