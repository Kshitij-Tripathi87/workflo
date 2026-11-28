# Agent 01 — DeepSeek V4.1 Flash-1017
## Native Go CLI Core, M1 Runtime Integration and Receipt Verification

**Branch:** `agent/deepseek-native-cli-runner`  
**Primary owner:** DeepSeek  
**Reviewers:** GLM (command UX/connectors), GPT-6 Luna (API/protocol), MiniMax (security), human owner (architecture/security acceptance)  
**M1 priority:** P0 — the implementation critical path

## 1. Mission and expected capability fit

**Mission:** deliver the new native Go CLI and connect its typed workflow to the existing customer Firecracker host so that the complete M1 run succeeds on real Linux x86_64 KVM and can be independently verified offline.

The routing hypothesis is Go implementation, multi-file integration, typed client/runtime code, CLI lifecycle and receipt verification. DeepSeek's reported software-engineering/terminal benchmark results are task-routing evidence only; they do not establish Workflo-specific correctness or security capability.

**Use this agent for:** Go CLI architecture inside the accepted ADR, typed API clients, lifecycle/state handling, error paths, deterministic tests, host integration and reproducible debugging.

**Do not treat it as:** security approver, canonical protocol owner, production operator, architecture decision-maker or an authority that can waive failed gates.

## 2. M1 architecture boundary — mandatory

- Implement the **Go CLI** under `apps/workflo-cli-go/`. It must not require Python, Node, Docker or a model provider to run.
- Keep FastAPI/Python as the control plane.
- For M1, connect to the existing Firecracker host implementation under `worker/` through a narrow adapter and versioned contract.
- Do not create a second Firecracker manager or rewrite the whole Python host in Go during the 25-day critical path.
- Go is the target language for incremental customer-runner migration under ADR-0024. Full Go runner parity is a post-M1 workstream.
- Preserve the Python CLI, host, guest engine, schema and Receipt V5 reference until parity and release gates pass.
- The strict boundary is Firecracker/KVM. A Go process, Docker, bwrap, namespaces alone or host execution is not a security boundary.

## 3. Owned paths and shared reservations

**Primary ownership**
- `apps/workflo-cli-go/cmd/workflo/`
- `apps/workflo-cli-go/internal/core/`
- `apps/workflo-cli-go/internal/api/` (typed transport/client; consumes Luna's approved OpenAPI output)
- `apps/workflo-cli-go/internal/auth/` (protocol/client behavior; Luna owns server)
- `apps/workflo-cli-go/internal/verify/`
- `apps/workflo-cli-go/internal/runnerclient/`
- corresponding unit/integration tests and Go build files.

**Narrow M1 host integration ownership, only after file reservation**
- `worker/` adapter files that connect the control-plane assignment to the existing Firecracker host package.
- New code must call the existing lifecycle API. It must not fork/reimplement VMM launch, jailer, networking or teardown.

**Not owned**
- CLI command UX, GitHub connector, output formatting and language profile registry (GLM).
- FastAPI routes, database, outbox, auth server, RLS or GitHub App server credential handling (Luna).
- Threat-model authority, default policy approval or security acceptance (MiniMax + human owner).
- Canonical Pydantic schemas, lifecycle enums, assignment semantics, guest protocol schemas or receipt format.
- Dashboard, marketing website, production secrets, production deployment or release signing authority.

Shared files require an explicit reservation in the agent operating model before any write.

## 4. Required M1 commands and behavior

Implement these commands through stable interfaces; GLM owns user-facing command handlers and text/JSON presentation where indicated:

| Command | Core behavior | Owner split |
|---|---|---|
| `workflo --help`, `--version` | Native binary discovery and version/build metadata | DeepSeek core |
| `workflo auth login/status/logout` | Existing device-flow lifecycle; secure token storage; no secret output | DeepSeek client + GLM UX + Luna server |
| `workflo doctor` | OS/arch, network, auth, runner reachability and KVM eligibility; clearly distinguishes client from strict runner | DeepSeek capability checks + GLM output |
| `workflo run` | Validate full SHA/profile/policy/runner; idempotent API submission; show lifecycle | DeepSeek API/core + GLM command |
| `workflo status` | Poll/stream only through approved API; print three outcomes separately | DeepSeek API/core + GLM output |
| `workflo cancel` | Request cancellation; never claim termination until runner proves it | DeepSeek API/core + GLM command |
| `workflo verify --offline` | Verify receipt/evidence/trust anchor without network | DeepSeek verifier + MiniMax negative tests |

A command may be hidden/not advertised until the backend operation is ready. Do not ship a command that returns fabricated success.

## 5. Package-level work plan

### DS-01 — Source audit and migration map · D1

Read:
- `apps/workflo-cli/`
- `packages/npm-workflo/`
- `packages/workflo-schema/`
- `worker/` and `worker/src/workflo_worker_host/`
- `apps/worker-engine/`
- current dispatch/outbox and receipt verifier code
- ADR-0022, ADR-0024, M1 milestone and interface registry.

Deliver:
- file-level map of existing behavior and ownership;
- CLI-to-control-plane-to-worker call graph;
- exact Firecracker host reuse seams;
- current receipt/teardown verification path;
- list of tests and missing real-KVM proof.

**Acceptance:** audit cites exact files/symbols and labels what is proven, mocked, missing or unknown. No refactor in the audit PR.

### DS-02 — CLI module skeleton and core interface · D2–D3

Build the smallest maintainable Go module:
- one executable entrypoint;
- version/build metadata;
- dependency injection for API transport, auth storage and output;
- typed errors and stable exit-code mapping;
- context cancellation/timeouts;
- structured logging with mandatory secret redaction;
- Go tests and CI compile targets.

Coordinate module boundaries with GLM before adding command packages.

**Acceptance:** clean machine with no Python/Node can build and run `workflo --help` and `workflo --version`; tests cover bad config, invalid flags, interruption and redaction.

### DS-03 — Typed API/auth client · D4–D5

Consume only Luna's owner-approved generated OpenAPI/client contract:
- device-flow login/poll/refresh/revoke as supported;
- secure credential-store interface;
- server-resolved current project scope;
- run admission with required idempotency key;
- get status and request cancel;
- bounded retries only for safe/idempotent operations;
- timeouts and clear retry-after handling.

**Acceptance:** generated/golden fixtures match the OpenAPI contract; duplicate submission is idempotent; non-idempotent calls are not blindly retried; no access token in logs, error strings or process arguments.

### DS-04 — Strict CLI run lifecycle · D5–D8

Coordinate with GLM's command handlers:
- full 40-char SHA-1 object ID validation (and explicit SHA-256 only if the contract supports it);
- immutable repo/ref display before admission;
- profile and policy version binding;
- runner selection/eligibility;
- state polling and cancellation request;
- execution/QA/trust result separation;
- deterministic exit code behavior.

**Acceptance:** invalid/abbreviated SHA rejected before request; lifecycle fixture covers queued→claimed→running→completed and error/cancel states; no fake or guessed state.

### DS-05 — Runner-control integration to current host · D7–D10

- Consume Luna's runner enrollment/heartbeat/claim/lease/complete contract.
- Keep the runner service identity distinct from human CLI auth and GitHub source auth.
- Connect the strict dispatch path to the existing worker host package using the approved adapter.
- Do not let M1 strict runs fall through to legacy `workflo_executor.SandboxExecutor`.
- Enforce lease expiry/fencing and a new attempt/new VM for retries.
- Preserve existing host checks and fail closed if a required host capability is absent.

**Acceptance:** integration test shows V2 assignment reaches the Firecracker host adapter; legacy executor is not invoked; expired lease and duplicate claim cannot start duplicate active VMs.

### DS-06 — Guest protocol and one pytest profile · D10–D14

- Bind every exchange to run, attempt, sandbox and protocol version.
- Verify nonce, sequence, replay, schema, operation and size before processing.
- Send only a pinned structured argv for the approved Python/pytest profile.
- Never interpolate repository content into host shell.
- Use immutable source snapshot and bounded execution resources.
- Capture only bounded, structured reports and output.

**Acceptance:** positive pytest fixture executes on real KVM; malformed, stale, replayed, oversized and cross-attempt messages fail closed; resource/time/output cap tests are attached.

### DS-07 — Teardown and receipt handoff · D14–D17

- Drive bounded graceful shutdown followed by forced termination as policy requires.
- Use host-observed evidence for all eight canonical MicroVM teardown checks.
- Never use guest shutdown claim as proof.
- Invoke existing canonical receipt signer/verifier path; do not alter receipt semantics.
- Bind source, run, attempt, sandbox, policy, runtime and evidence digests.

**Acceptance:** intentional teardown failure cannot produce VERIFIED_CLEAN; receipt signature/digest checks pass; evidence alteration and wrong trust key fail.

### DS-08 — Offline verifier · D16–D18

- Implement `verify --offline` using local receipt, evidence and trust anchor only.
- Verify signature, signer trust, canonical encoding, evidence hashes and identity bindings.
- Return deterministic nonzero exit codes and actionable non-secret errors.
- Do not reach control plane, GitHub or inference provider.

**Acceptance:** verifier succeeds in a clean environment with network disabled; tampered receipt, evidence, missing evidence and wrong key all fail.

### DS-09 — Real KVM vertical slice and regression · D18–D22

Run the full workflow from clean checkout against the pinned public/private test repository fixture and actual KVM host. Reproduce M1-01..M1-15 with MiniMax. Label every test by environment type.

**Acceptance:** complete evidence packet exists; no mocked case is represented as real KVM; repeat run uses a new VM and fresh attempt identity.

### DS-10 — Release candidate and handoff · D23–D25

Deliver:
- exact CLI/host adapter commit and binary digest;
- Go module/build/provenance metadata;
- known limitations and compatibility report;
- test command/result matrix;
- KVM and offline-verification evidence;
- rollback and debugging runbook;
- post-M1 Go runner parity design.

**Acceptance:** human owner can reproduce installation, run and offline verification from the handoff without relying on undocumented agent context.

## 6. How to work

1. Start each task by checking the current base SHA and reading the owning contract.
2. Reserve shared paths before edits.
3. Publish interfaces and compile stubs before parallel consumers implement.
4. Work in small PRs: core binary; API/auth; run path; host adapter; verifier.
5. Rebase daily; merge only after owner review and relevant CI.
6. Add one regression test with every bug fix.
7. Attach exact commands, environment and pass/fail/skip counts.
8. Escalate blocked KVM, source credential, signing or API work the same day.

## 7. Do not

- rewrite FastAPI, Python guest or all worker code;
- start full Go runner migration before M1 proof;
- create a second Firecracker/jailer implementation;
- change canonical schemas, lifecycle enum, policy or receipt unilaterally;
- add a generic host shell or arbitrary guest-to-host tool;
- execute repo scripts on the user's host;
- silently downgrade strict mode to Docker/bwrap/host execution;
- log tokens, private URLs containing credentials or secret-bearing environment values;
- turn mock results into KVM claims;
- merge or approve your own sensitive PR.

## 8. Required test classes

- Go unit and golden command tests.
- API client contract and auth expiry/revocation tests.
- Idempotency, retry and cancellation tests.
- Real Firecracker/KVM boot and guest test.
- Source immutability and credential non-disclosure tests.
- Guest protocol adversarial tests.
- Resource/network enforcement.
- Eight teardown checks and fault injection.
- Canonical receipt integrity.
- Offline verifier network-disabled and tamper tests.
- Clean-client install/build checks for claimed OS targets.

## 9. Completion report

Include: task ID, base SHA, commit SHA, paths changed, exact tests, environment classification, KVM host/artifact identity, output hashes, security impact, known limitations, blockers, next task and PR link. "Works on my machine" is not evidence.
