# 01 — Workflo System Architecture

**Parent:** [Implementation Blueprint](00-master-implementation-plan.md)  
**Status:** Proposed, grounded in repository review at `5e82478572af26335906686c06703d41df4c3d1f`.

## 1. Architecture objectives

The architecture must satisfy five properties simultaneously:

1. **Source control:** user code remains on the customer-controlled runner; only a content-addressed snapshot is materialized inside an ephemeral guest VM.
2. **Policy control:** a model can suggest a probe but cannot expand permissions or execute arbitrary instructions.
3. **Evidence integrity:** guest-produced claims are distinguishable from host-measured facts; the host and verifier control final receipt creation.
4. **Portability:** CLI/web/control plane and guest contracts are shared across OS families while each OS uses a native VM adapter.
5. **Reproducibility:** a run is reproducible from a pinned source snapshot, immutable policy, runtime image digest and test configuration.

## 2. Deployment topologies

### 2.1 Local developer topology

```text
Developer workstation
  ├── workflo CLI
  ├── workflo-runner daemon
  ├── OS credential vault
  ├── source checkout (not uploaded)
  └── local VM hypervisor
       └── one Linux guest per run attempt
            ├── repository snapshot
            ├── build/test process tree
            ├── target app
            ├── Workflo guest supervisor
            └── local inference endpoint (optional)
```

The local runner talks to the control plane over an outbound authenticated connection if the user uses the web dashboard. For CLI-only local execution, it may operate in offline/local-only mode and write a local proof bundle. The runner never opens a general remote shell port.

### 2.2 Web-managed customer runner topology

```text
Browser -> Workflo dashboard -> FastAPI control plane -> PostgreSQL
                                      ^                       |
                                      |                       | signed run assignment
                              outbound runner stream <--------+
                                      |
                             customer runner daemon
                                      |
                               VM backend / guest
```

The browser submits a RunSpec and displays status. The runner fetches the local or remote repository snapshot directly using the user's configured access mechanism. The browser does not upload source content by default. A Git provider integration may later let a customer runner clone a private repo using short-lived, scoped credentials; the credentials must not be sent to the guest.

### 2.3 Remote runner topology

When the user's desktop OS lacks a certified strict local backend, the CLI or dashboard may submit a run to a customer-managed Linux/KVM runner. The runner must be explicitly selected and its runtime identity visible. The source snapshot is transferred directly from the local CLI/agent to the runner using an authenticated, encrypted, content-addressed transfer. It must never pass through an untrusted generic object store unless the customer deliberately configures that storage and encryption boundary.

A hosted Workflo-runner fleet is not required for the prototype and should not be assumed. It would change source custody, tenancy, billing and compliance requirements materially.

## 3. Core services and module responsibilities

### 3.1 `apps/workflo-cli`

Responsibilities:

- Project discovery and `workflo.yaml` validation.
- Local source snapshot creation and dirty-worktree handling.
- Provider profile selection and local provider health checks.
- Runner status/start/connect/disconnect.
- RunSpec authoring and submission.
- Streaming run events to terminal.
- Artifact/report/evidence export.
- Offline receipt verification.
- Upgrade/install/doctor UX.

The CLI should be a thin client of the canonical Python modules. The user-facing UX may be Click today; a future TUI is optional and must not own business logic.

### 3.2 `packages/workflo-schema`

Canonical Pydantic v2 models for:

- RunSpec and immutable resolved RunPlan.
- Project settings and policy.
- Runner identity and capabilities.
- Sandbox assignment and backend capability report.
- Guest protocol messages and action capabilities.
- Provider profile and inference observations/plans.
- Lifecycle events and state transitions.
- Findings and report summary.
- Evidence ledger entries/manifests.
- Teardown checks.
- Receipt payload and DSSE envelope.

JSON Schema is exported from Python. `packages/contracts` is validated from the exported schema and must not become an alternative source of truth.

### 3.3 `apps/control-plane`

Existing FastAPI service remains the authority for user/project access and durable run lifecycle. Required modules:

- `api/v1/projects.py` or versioned projects router.
- `api/v1/runners.py`: enrol, heartbeat, capabilities, leases, disconnect/revoke.
- `api/v1/runs.py`: create, inspect, cancel-request, event listing and artifact references.
- `api/v1/providers.py`: provider metadata, profile CRUD, secret replacement status, test result.
- `api/v1/inference.py`: provider-neutral metadata-only plan endpoint.
- service layer for runner assignment, retry policy, lease expiry and event projection.
- PostgreSQL outbox/transactional dispatch using existing durable dispatch foundation.
- row-level tenant isolation on all project/run/credential/evidence references.

Avoid expanding the legacy `/v1` wire model in place. Use additive endpoints or a versioned `/api/v2` surface if the existing API compatibility requires it. The schema version, API version and receipt version are separate concepts.

### 3.4 `worker/` host manager

Trusted host services:

- validate assignment signature, runner registration, source digest and policy digest;
- check backend eligibility and required runtime/image identity;
- reserve VM, CPU, memory, disk and process budget;
- apply host egress policy before VM boot;
- provision per-attempt VM and ephemeral disk;
- deliver a one-time, short-lived run capability;
- maintain the guest protocol session and sequence numbers;
- accept bounded evidence messages into a host-owned append-only ledger;
- request shutdown, force terminate and independently probe cleanup;
- produce host lifecycle evidence for verifier/signing service.

There is deliberately no public `execute_command` or arbitrary file-read method. A host administrator may have operational tooling out-of-band, but that is not a guest protocol capability.

### 3.5 `apps/worker-engine` guest runtime

Responsibilities:

- Validate capability and guest identity before work.
- Receive/verify immutable source snapshot.
- Prepare declared toolchain/dependency layers under policy.
- Run fixed test command argv.
- Start application with bounded environment and lifetime.
- Provide governed agent tool adapters.
- Capture app/API/browser/test observations.
- Return only declared typed data and digests through the guest protocol.
- Exit on shutdown request or fail closed on protocol violation.

The guest must treat repository files, package install scripts, build tools, test output, browser content and network responses as hostile.

### 3.6 `apps/dashboard`

The dashboard is a UI client of the control plane. It must not replicate run orchestration in browser JavaScript. All actions are authenticated API calls. The browser receives sanitized status/events, not source artifacts by default. For local runner connection, the daemon is the channel endpoint; the browser cannot directly invoke arbitrary workstation processes.

## 4. Runner enrollment and assignment

### 4.1 Enrolment

1. CLI performs `workflo runner connect`.
2. Control plane issues a short-lived enrolment challenge.
3. User authenticates in browser/device flow.
4. Runner generates a local keypair in OS-protected storage; private key never leaves runner.
5. Control plane associates the public identity with user/project/workspace and issues limited runner certificate/refresh token.
6. Runner reports capabilities: OS, architecture, backend type/version, runtime image digest, hypervisor status, memory/CPU/disk envelope, guest transport and security profile.
7. Control plane evaluates the desired project execution profile and records `strict_ready`, `development_only` or `ineligible` with concrete reasons.

### 4.2 Assignment

A run assignment must include:

- `run_id`, `attempt_id`, `sandbox_id`;
- source type, full commit or snapshot digest, snapshot size and materialization policy;
- resolved RunSpec digest and policy digest;
- runtime image/kernel/rootfs digests;
- requested backend/runtime class;
- CPU, memory, disk, wall clock, process and I/O quotas;
- network policy and approved destinations;
- allowed tool capabilities and their budgets;
- inference profile id and source/privacy mode;
- evidence protocol and receipt version;
- expiry and one-time nonce;
- issuer/signature/key identity.

The assignment signature must be verified before any VM resource is allocated. The guest capability must be bound to the assignment, attempt and sandbox; it must expire no later than the assignment deadline.

### 4.3 Lease and failure handling

- Runner claims are leased, not permanent.
- Heartbeats carry runner id, active attempts, capacity and last event sequence.
- The control plane reassigns only when the current attempt is known to have stopped or fenced; never create two simultaneous writers for one attempt.
- Fencing tokens increment on each ownership change.
- Cancellation records intent first; runner executes graceful shutdown and then a bounded force-termination path.
- An unreachable runner yields `UNKNOWN` trust until host evidence is returned or the lease is conclusively expired and the backend confirms resources are gone.

## 5. Source snapshot model

### 5.1 Git source

For a remote repo:

- Resolve requested ref to a full immutable commit SHA before admitting run.
- Clone/fetch with credential helper in a trusted prep component; do not pass tokens to guest.
- Prefer a bare object fetch or content-addressed archive. Materialize only the selected commit tree into the guest input disk.
- Exclude `.git` credential helpers, remote refs with secrets, LFS credentials and submodule credentials unless explicitly declared and scoped.
- Record commit SHA, tree digest, submodule identities and LFS object digests when used.

### 5.2 Local source

For local working directory:

- `workflo source inspect` reports HEAD, staged/unstaged/untracked changes and ignored data.
- Default is fail closed for dirty tree until user chooses `--snapshot-worktree` or `--commit-only`.
- Snapshot is built without following symlinks outside the repo root; reject device nodes, sockets, FIFOs and unsafe paths.
- Honor `.workfloignore` with a visible exclusion preview; never silently omit tracked source files.
- Detect secrets and large/generated directories, but do not claim that scanners guarantee secret removal.
- Hash a deterministic manifest; use this digest in RunSpec and receipt.
- Source transfer to guest is encrypted and chunked; verify every chunk and final manifest in the guest before execution.

### 5.3 Snapshot immutability

The guest's source tree is mounted read-only during test/agent execution by default. Writable output/cache/build directories are separately mounted or stored on scratch. If a build requires source mutation, Workflo creates a writable overlay and records its diff digest; the original snapshot digest remains immutable. Agent-proposed fixes are generated outside the original checkout and exported as patch artifacts only.

## 6. Evidence pipeline and receipt issuance

### 6.1 Evidence sources

Each evidence entry contains:

- unique evidence id and sequence;
- run/attempt/sandbox binding;
- timestamp and clock source;
- producing component identity;
- evidence type and schema version;
- trust source: `host_measured`, `guest_reported`, `agent_observed`, or `model_generated`;
- bounded metadata and/or content digest;
- previous entry digest and current entry digest;
- optional redaction metadata.

No raw unbounded stdout/stderr is included in a signed receipt. Evidence payloads may be separately exported under customer-selected retention policy, but must be size-limited, scrubbed and encrypted where persisted. The evidence index binds payload digests.

### 6.2 Host vs guest truth

The guest can report that a test passed. The host can independently assert that the guest VM was provisioned with a particular image and that a process/VM exited. The verifier can assert that the signature and hashes validate. These are different facts. A model-generated explanation is not evidence and must be visibly labeled as an interpretation.

### 6.3 Receipt finalization

Only the trusted receipt finalizer may sign after:

1. source and policy digests agree across admission, assignment and evidence;
2. runtime identity is pinned and recognized;
3. guest evidence chain and manifest digest validate;
4. test result completeness rules are satisfied;
5. lifecycle/outcome graph is legal;
6. host teardown probes have completed;
7. trust outcome matches the teardown and evidence results;
8. provider provenance is consistent with privacy mode;
9. limitations are populated;
10. no required integrity gate is unknown.

Receipt v5's DSSE-style envelope is the canonical new format currently represented in `packages/workflo-schema/src/workflo_schema/contracts/receipt.py`. Preserve legacy receipt v1–v4 verification. See master blueprint for versioning rule.

## 7. API contract families

The following are logical API families; exact URL/methods need to align with the existing FastAPI router and schema:

| Family | Operations |
|---|---|
| Identity | device login, token refresh, revoke runner/session |
| Projects | create/list/get/update policy |
| Providers | list provider catalog, create/update profile, test connection, set active profile, replace/remove key |
| Runners | enrol, heartbeat, capabilities, claim/lease, stream events, revoke |
| Runs | create, get, list, cancel-request, retry policy-eligible failure |
| Artifacts | upload/download signed evidence chunk/index under strict scope; retrieve report |
| Inference | metadata-only plan request, provider-neutral model response, provenance |
| Verification | server-side verify status optional; offline verifier remains authoritative and independent |

All IDs are opaque. Every query that reaches tenant-owned data must include tenant/project authorization at the database layer and application layer.

## 8. Operational signals

Minimum metrics:

- runner online/heartbeat/lease-age;
- eligible and ineligible backend counts, by OS/backend/reason;
- queue age, claim delay, VM boot duration, guest readiness;
- phase duration: source snapshot, dependency prep, tests, app start, agent, evidence, teardown;
- VM failure and host resource shortage;
- API/browser/test counts and failure categories;
- inference request count, provider/model id, tokens/cost metadata, latency and invalid-plan rate (never prompt text);
- privacy policy denials and redaction counts;
- teardown check pass/fail/unknown counts;
- receipt finalization and independent verification outcomes;
- evidence upload/retention failures.

Do not log API keys, source content, raw prompt, entire browser response or unredacted logs.

## 9. Architecture acceptance criteria

- The local CLI and web UI construct the same canonical RunSpec.
- Control-plane dispatcher sends a signed assignment to an enrolled runner.
- Runner chooses a backend through capability negotiation; no fallback to less-secure profile.
- Guest and host speak one versioned typed protocol with transport-specific implementation only.
- Host can terminate guest independently from guest cooperation.
- Guest cannot access host credentials, host mounts or host control API except the one-time capability transport.
- Evidence ledger persists outside guest-controlled filesystem.
- Receipt verifies offline and binds all important identities.
- All dashboard-visible results derive from actual events/artifacts, not mocked placeholders.