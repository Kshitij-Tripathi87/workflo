# Workflo workspace restructuring and native CLI migration

**Plan version:** v2 — CLI-first beta  
**Repository baseline:** 373b02918a87854efe4427b1f4e4ae79905457e8  
**Change strategy:** additive workspace and side-by-side native CLI migration. No big-bang source movement.

## 1. Current repository reality

The repository is a historical monorepo containing more than one product and multiple runtime generations. The active Workflo Trust lineage currently spans:

| Responsibility | Current path | Plan |
|---|---|---|
| Canonical contracts | packages/workflo-schema/ | Proposed Pydantic authority; ADR-0015 still requires owner ratification |
| TypeScript contract mirror | packages/contracts/ | Compatibility/mirror; no competing lifecycle authority |
| Control plane and dispatch | apps/control-plane/ | Existing FastAPI/PostgreSQL implementation remains canonical pending approved change |
| Existing Python CLI | apps/workflo-cli/ | Keep operational as reference and compatibility path during migration |
| New native CLI | Proposed crates/ workspace | Additive Rust workspace after language spike and owner approval |
| Production microVM host | worker/ | Sole existing Firecracker/KVM host lineage |
| Guest workload engine | apps/worker-engine/ | Guest-side deterministic test execution |
| Development executor | apps/sandbox-executor/, supervisor/, packages/sandbox-runtime/ | Development/CI only; not a production fallback |
| Supporting security/test packages | packages/sandbox-isolation/, packages/probe-engine/, packages/workflo-utils/, packages/cortex-auth/ | Reuse existing components; avoid duplicate implementations |
| npm package wrapper | packages/npm-workflo/ | Thin native-binary launcher/distribution layer |
| Dashboard | apps/dashboard/ | API-first; substantial implementation deferred |
| Marketing | website/ | Claims must match verified product status |

Other TypeScript service/runtime paths include packages/db/, packages/events/, packages/sandbox/, packages/ingestor/ and packages/executor/. They must be mapped against the current boundaries and ADRs before adding features. PRODUCT_BOUNDARIES.md identifies backend/ and frontend/ as the adjacent Cortex Autopilot product, and client/, server/, shared/ and drizzle/ as legacy paths. apps/agent-cli/ and apps/validation-cli/ have unresolved dispositions. Do not delete or reassign any of these by assumption.

The repository's docs/implementation/BLUEPRINT_STATUS.md has an earlier audit base than this plan. Its task counts and statuses are not current proof. Re-run its commands and inspect current source before using it as a readiness report.

## 2. Product boundary and trust invariants

- The customer runner owns source acquisition, image admission and guest execution.
- Production untrusted code executes only inside a per-attempt Firecracker/KVM microVM under ADR-0022.
- The guest receives a pinned source snapshot and scoped workload capability, never GitHub tokens, runner identity secrets, host filesystem or signing keys.
- The host validates assignment, resource policy, evidence completeness and teardown independently of guest claims.
- Core, Deep AI and Security results are separate.
- Execution status, QA outcome and trust outcome are separate dimensions.
- A signed receipt authenticates specific signed claims and evidence references. It does not prove that the application is defect-free or that a security property held without its required evidence.
- Any local Docker/bwrap/namespace run is clearly labeled development-only.

## 3. Rust or Go: recommendation and decision method

**Current recommendation: Rust** for the new native CLI, protocol client and local orchestration process.

Reasons:
- Produces a native executable without requiring Python or Node merely to launch Workflo.
- Strong static typing and memory-safety defaults suit protocol parsing, process lifecycle and local orchestration.
- Supports Linux, macOS and Windows targets.
- Enables narrow, auditable platform-specific FFI behind a portable interface.

This is a recommendation, not an approved ADR. Language alone does not provide sandbox isolation. Firecracker/KVM is the production boundary; a Rust CLI does not make local Windows/macOS execution safe.

### Required Rust-vs-Go spike

Gemini writes the decision criteria; DeepSeek implements the Rust proof; GPT-6 designs and runs the acceptance tests. Compare both languages on the same small requirements and toolchain versions:
- binary build and launch on Linux, macOS and Windows;
- startup time, artifact size and clean-machine install;
- config parsing and schema validation;
- stable help, version, exit-code and JSON output;
- authenticated API client against a test server;
- request ID propagation, retries and idempotency handling;
- child process lifecycle, cancellation and shutdown on all target OSes;
- structured logs with secret redaction;
- reproducible CI builds and dependency audit;
- maintenance cost and platform FFI complexity.

Set measurement thresholds before running the spike. If no Go prototype is requested, state that limitation in the report and make the Rust recommendation provisional. Owner approval is required before the full Rust workspace is expanded.

## 4. Additive native source layout

After the language ADR is approved, create:

    crates/
      Cargo.toml
      workflo-cli/       # command grammar, help, UX, exit codes
      workflo-protocol/  # versioned RunSpec, gate, runner and result types
      workflo-client/    # API client, auth/session, retry and pagination
      workflo-daemon/    # bounded local lifecycle and IPC
      workflo-platform/  # OS detection, process and service adapters

Do not add a second Firecracker host crate in this first migration. The existing worker/ lineage remains the host boundary. If a Rust host is later justified, that is a separate architecture decision, security review and migration project.

## 5. Layer responsibilities

1. CLI presentation: parse commands, render text/JSON, confirm destructive intent and map stable exit codes. It does not make security-policy decisions.
2. Application orchestration: config, source selection, run preview, API calls, daemon lifecycle, retries and cancellation.
3. Protocol: typed, versioned messages, schema validation, canonical serialization and golden test vectors.
4. Runner client: authenticated runner registration, lease, heartbeat and signed assignment verification. It exposes no arbitrary host shell or unrestricted filesystem operation.
5. Control plane: identity, workspace membership, project, policy admission, durable dispatch and run state. CLI never connects directly to the database.
6. Linux runner host: existing worker/ owns Firecracker, jailer, cgroups, egress enforcement, guest supervisor, host evidence and teardown.
7. Guest: apps/worker-engine/ receives only the RunSpec, pinned snapshot and narrow capabilities.

## 6. Supported client versus execution matrix

| Capability | Linux client | macOS client | Windows client |
|---|---|---|---|
| Native CLI install, update and uninstall | Required | Required | Required |
| help/version/doctor/init/config | Required | Required | Required |
| GitHub public/private source operations | Required | Required | Required |
| Connect to customer-owned Linux runner | Required | Required | Required |
| Local dev/test mode | Development-only | Development-only | Development-only |
| Strict production untrusted-code execution | Customer Linux/KVM runner only | Remote customer Linux/KVM runner | Remote customer Linux/KVM runner |
| Local strict sandbox claim | Only after real Gate B and supported host checks | Not in beta | Not in beta |

OS support is a client commitment. It is not a claim that every OS can host the production sandbox.

## 7. Incremental migration phases

### M0 — Current-state inventory (read-only)
- Record every current Python CLI command, alias, flag, output format, exit code, config path and install path.
- Map CLI callers in CI, docs, scripts and GitHub Action.
- Trace run, run-dev and verify into schemas, supervisor, control plane, executor, receipt writer and evidence verifier.
- Inventory all current runtime profiles and their actual isolation guarantees.
- Produce a current CI/test baseline at the exact main SHA.
- No source changes.

### M1 — Contract freeze and compatibility vectors
- Owner reviews ADR-0015 through ADR-0023 and resolves canonical schema/lifecycle/evidence authority.
- Publish golden RunSpec, RunResult, gate outcome, finding and runner-assignment vectors.
- Reconcile receipt v5 writer with legacy v1-v4 readers. Preserve legacy verification.
- Rust and Python serialization must match golden vectors.
- Unknown major schema versions and unknown critical fields fail closed.

### M2 — Native shell
- Implement help, version, doctor, config validation and stable JSON/TTY output.
- Build on Linux, macOS and Windows.
- No Python or Node runtime is needed to launch the executable.
- Keep old Python CLI untouched.

### M3 — Local development vertical slice
- init creates a versioned, secret-free project config.
- source inspect reports repository root, commit, branch, dirty-tree state, ignore behavior and snapshot eligibility without uploading source.
- dry-run validates the plan without starting a runtime.
- dev run bridges the current development executor through an explicit adapter and labels its profile as non-production.
- verify preserves offline receipt/evidence verification and legacy compatibility.

### M4 — Customer-owned Linux runner
- Registration uses short-lived enrollment and runner identity.
- Runner receives a signed, expiring, attempt-bound assignment.
- Source token stays host-side. Checkout is commit-pinned.
- Strict execution requires real Firecracker/KVM, jailer, cgroup and egress enforcement.
- Failed admission does not fall back to Docker, bwrap or direct process execution.
- Evidence collector and teardown must independently validate expected resources and cleanup.

### M5 — Four language profiles and gate separation
- Pin toolchain/runtime images by digest.
- Deliver Python, Node.js, Go and Java profiles.
- Each profile supports declared commands, startup/readiness, bounded output and cancellation.
- Core, Deep AI and Security produce independent results.
- Add stable fixtures for success, failure, timeout, missing toolchain, malformed policy, path escape and teardown failure.

### M6 — GitHub integration and packages
- GitHub App permission design and webhook contract approved.
- Private/public source fetch via least-privilege, short-lived token.
- PR checks show each gate distinctly and map skipped/blocked correctly.
- Native binary is wrapped by npm/pnpm/Bun distribution.
- Native install archives/packages support the three client OSes.
- No automatic PR merge, branch push or deploy.

### M7 — API-first identity and workspace
- Define OpenAPI and identity model while CLI work proceeds.
- Support individual workspace and team/organization workspace.
- Prove workspace role enforcement and RLS/cross-tenant tests.
- Keep existing FastAPI control plane; do not create another backend as an incidental rewrite.

### M8 — Dashboard
Start substantial dashboard implementation only after the CLI run gate, OpenAPI contract tests, workspace role model, tenant isolation and stable evidence APIs pass. The dashboard is a client of the same API, not a new source of lifecycle truth.

## 8. Distribution contract

- npm, pnpm and Bun should all install the same native Workflo CLI through the maintained npm wrapper path.
- Package selection must match OS and architecture exactly.
- Downloaded/prebuilt binaries must be digest-verified before execution.
- Unknown or unsupported platforms fail with explicit diagnostics.
- Avoid arbitrary remote postinstall shell and unverified fallback downloads.
- Native package formats may include Linux archive/deb/rpm, macOS archive/Homebrew and Windows MSI or portable archive/winget manifest after install tests.
- Under zero budget, artifact checksum and provenance can be produced; Apple notarization and Windows publisher signing cannot be claimed unless the real signing identities and processes are used.
- Keep current package naming until a separate owner-approved rename migration.

## 9. CLI grammar proposal

    workflo --help
    workflo --version
    workflo doctor
    workflo init
    workflo auth login
    workflo auth status
    workflo project create
    workflo project connect
    workflo source inspect
    workflo source connect github
    workflo runner install
    workflo runner register
    workflo runner status
    workflo run --path . --profile python-fastapi --gates core,deep,security
    workflo run --repo org/private-repo --ref <full-commit-sha> --config workflo.yaml
    workflo runs list
    workflo runs show <run-id>
    workflo runs logs <run-id>
    workflo evidence show <run-id>
    workflo verify --receipt <path> --evidence <path>

This is the target surface, not a claim that all commands exist. Existing CLI behavior and package aliases remain until a parity and deprecation plan is accepted. A sandbox create shortcut may only create a policy-admitted run attempt; it must not expose a raw privileged shell.

## 10. Language profile launch map

| Language | First profile | Core checks | Deep AI focus | Security focus |
|---|---|---|---|---|
| Python | pytest/unittest; FastAPI first | declared tests, import/build, startup/readiness | request validation, state and exception boundaries | dependency, static/config, auth and sandbox probes |
| Node.js | Node scripts; Express first | npm/pnpm/Bun scripts, Jest/Vitest, startup | async errors, middleware, API and state boundaries | dependency audit, secret detection, config and sandbox probes |
| Go | standard library net/http first | go test, go vet, build, startup | concurrency, cancellation and API contracts | dependency/static/config and isolation checks |
| Java | Spring Boot baseline | Maven/Gradle, JUnit, startup/readiness | API/state/exception/integration tests | dependency/static/config/auth and isolation checks |

Framework discovery is advisory. Selected profile and pinned runtime image digest are recorded in RunSpec. FastAPI and Express are first framework adapters; Go and Java profiles must still ship language-level support without inventing a false framework maturity claim.

## 11. Runtime modes and BYOK policy

### Execution modes
- Customer-controlled runner is the beta default.
- Local dev mode works where supported but is never strict production isolation evidence.
- Workflo-managed mode may be represented as a future-compatible capability in the protocol; it is not operationally offered under this zero-budget beta.

### Inference
- Customer brings provider/model keys.
- No Workflo model API or API-credit service is created.
- Local/customer-controlled inference or no-model deterministic operation is default.
- Hosted prompt execution is disabled by default and requires workspace plus per-run consent.
- Hosted payload schema only admits explicitly typed metadata such as aggregate statuses, durations, categorical failure codes and coverage counts.
- Source files, diffs, snippets, repository archives, raw logs, environment values, secrets, credentials and customer personal data are prohibited.
- Consent does not override the payload schema. If data classification is uncertain, the request is blocked.
- Add canary payloads and egress tests proving prohibited data is rejected.

## 12. Concurrency and capacity acceptance

The requirement is 10–15 concurrent users each submitting multiple runs. Do not invent a guaranteed number of simultaneous microVMs: the active run limit depends on customer runner CPU, RAM, disk, network and configured quotas.

Required load scenario:
- 15 authenticated users concurrently.
- Three run submissions per user within one test window: 45 durable submissions.
- Mixed individual and team workspaces; multiple projects; private-source checkouts.
- Idempotent repeated submits and duplicate webhook delivery.
- Queue/backpressure above runner slots; visible status and fair scheduling.
- Control plane and runner restart during queued/running work.
- Verify no dropped, duplicated, cross-tenant or cross-run-misattributed records/evidence.
- Record real host resource profile, p50/p95 API latency, queue age, dispatch lag, throughput, retry count and recovery time.

## 13. Gate-driven release, not calendar-driven release

| Gate | Evidence required |
|---|---|
| G0 Architecture | Owner-approved language, contracts, runtime modes and required ADR decisions |
| G1 Native CLI | Clean installs and help/version/doctor/init on Linux, macOS and Windows; no Python/Node launch dependency |
| G2 CLI run | Reproducible dev run, source selection, RunSpec, honest profile labels, receipt verification and old CLI compatibility |
| G3 Strict runner | Real KVM Firecracker boot, jailer, cgroups, enforced egress, source materialization, evidence collector, teardown, crash recovery and adversarial negatives |
| G4 Profiles and gates | Python/Node/Go/Java; separate Core/Deep/Security results; evidence and fixtures |
| G5 GitHub | Public/private fetch, SHA pin, short-lived credentials, webhook validation and correct PR checks |
| G6 Capacity | 15 users × 3 submissions, durable 45-run workload, fairness, isolation and recovery |
| G7 API and identity | Individual/team accounts, role model, RLS and cross-tenant negative tests |
| G8 Distribution | npm/pnpm/Bun and native packages; clean install/update/uninstall; checksums/SBOM/provenance |
| G9 Release | Fresh-machine acceptance, rollback, accurate limitations, owner go/no-go |

No required gate may be called complete based only on mocks, model reasoning or skipped tests. The release has no fixed date.
