# Workflo CLI-first beta blueprint

**Owner decisions incorporated:** 2026-11-28  
**Baseline:** 373b02918a87854efe4427b1f4e4ae79905457e8  
**Delivery policy:** gate-driven, no fixed date.

## 1. User outcome

A developer installs Workflo CLI on Linux, macOS or Windows; connects a local repository or GitHub repository; selects a project profile and test gates; submits a run to a customer-controlled runner; sees Core, Deep AI and Security outcomes independently; then verifies evidence and a receipt. GitHub PR checks report those same gate outcomes against the exact commit. The web app is a later client of the same APIs.

This is software change verification infrastructure, not a model API provider or unrestricted agent sandbox.

## 2. Execution modes and zero-budget feasibility

The product architecture supports customer-controlled and managed runner modes, but the beta default is customer-controlled. Customer provides Linux/KVM compute and any provider API credentials. Workflo must not silently operate a funded hosted runner behind the scenes or assume a cloud budget.

The native CLI should run on Linux/macOS/Windows. Strict production execution of untrusted code in this beta is limited to customer-owned Linux hosts with Firecracker/KVM. macOS and Windows clients connect to a Linux runner. Local development execution can be available on the three client OSes but is clearly labeled non-production.

A future Workflo-managed runner can implement the same runner protocol after funding, but must be separately deployed, metered, quota-controlled and security-reviewed. Do not expose it as a working beta feature until it exists.

## 3. Target topology

    Developer workstation
      └── Rust Workflo CLI
            ├── config/profile resolver
            ├── auth and workspace session
            ├── source inspection and RunSpec builder
            ├── API client and local dev adapter
            └── run/evidence/receipt viewer
                     |
                     | authenticated, versioned API
                     v
    Customer-hosted control plane (existing FastAPI + PostgreSQL)
      ├── user, personal workspace and organization membership
      ├── project and source connection
      ├── policy admission and RunSpec digest
      ├── durable dispatch/outbox and idempotency
      ├── run/attempt/gate/finding metadata
      └── GitHub webhook and check-run adapter
                     |
                     | signed, expiring attempt assignment
                     v
    Customer-owned Linux runner (existing worker/ lineage)
      ├── enrollment, heartbeat, lease and drain
      ├── immutable artifact and image admission
      ├── Firecracker/jailer/KVM per run attempt
      ├── cgroup/resource/network enforcement
      ├── host-side Git/source snapshot
      ├── guest supervisor protocol
      ├── evidence collection and teardown
      └── receipt assembly and protected signing boundary
                     |
                     | typed, attempt-bound messages
                     v
    Guest VM
      ├── immutable runtime image
      ├── exact repository snapshot
      ├── core test process
      ├── bounded deep-test agent
      ├── security tools
      └── evidence output

This is a target architecture, not a statement that every arrow is implemented. Current code and open gate status must be re-audited before each phase.

## 4. Responsibility boundaries

### CLI
- Presents commands, validates local config, inspects source, creates RunSpec requests and displays results.
- Does not decide host security policy.
- Does not access database directly.
- Does not mount arbitrary host paths or expose a raw privileged shell.

### Control plane
- Authenticates users and workspace membership.
- Enforces tenant authorization and policy admission.
- Stores durable run/attempt/gate metadata and schedules runner assignments.
- Keeps BYOK credential values encrypted and write-only.
- Never trusts caller-supplied workspace ID without membership validation.

### Runner host
- Fetches source using host-only, short-lived GitHub credential.
- Pins exact commit and builds a safe snapshot.
- Admits pinned runtime image and signed assignment.
- Owns resource, egress, guest lifecycle, evidence and teardown validation.
- Never sends customer source to hosted models.

### Guest
- Receives only the assigned snapshot and bounded runtime capabilities.
- Cannot inspect host filesystem, GitHub token, runner identity or signing key.
- Runs declared test commands and bounded test agents.
- Returns typed events/evidence; host validates them independently.

## 5. CLI user journey

1. doctor: inspect OS, architecture, version, dependencies and available runner connections without changing machine state.
2. init: create versioned project configuration with safe defaults and no embedded secret values.
3. auth login/status: establish and inspect an authenticated user session.
4. project connect/create: associate current repo with a personal or organization workspace project.
5. source inspect: show repository root, current commit, dirty status, ignore behavior and snapshot warnings.
6. runner status: display eligible customer runner, platform and runtime profile.
7. run preview: show source SHA, selected profile, three gates, execution mode, privacy policy and expected resource request.
8. run: submit idempotently and follow progress.
9. runs/evidence/verify: inspect gate results and independently verify evidence/receipt.

Suggested command surface:

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
    workflo verify --receipt <file> --evidence <directory>

These are proposed commands, not current implementation claims. Existing commands, flags, exit codes and package names must be inventoried before compatibility changes. A sandbox create alias may only create a policy-admitted run; it is not a raw shell.

## 6. Run lifecycle and three gates

A run binds:
- immutable RunSpec version;
- exact Git commit and deterministic source snapshot digest;
- profile and pinned runtime image digest;
- policy bundle/digest;
- runner identity and assignment expiry;
- unique run and attempt IDs;
- requested gate set and privacy policy.

Execution sequence:
1. validate config and profile;
2. resolve source to immutable revision/snapshot;
3. request admission and receive resolved policy digest;
4. create durable run and attempt;
5. dispatch to customer runner;
6. verify runner capability, signed assignment, image and policy;
7. boot microVM;
8. materialize source and run test suites in guest;
9. stream typed events and persist evidence;
10. host validates manifest, expected artifact set and integrity;
11. teardown probes independently validate resource cleanup;
12. signer validates allowed claims and signs the receipt;
13. CLI and GitHub expose execution, QA and trust results separately.

### Core gate
Deterministic declared checks: build, lint, unit/integration tests, startup/readiness, API probes and framework-specific checks.

### Deep AI gate
Bounded test discovery and exploration: coverage gaps, boundary cases, negative flows, API/browser workflows and regression candidates. Each finding remains candidate until reproduced and independently verified. Budgets: time, tokens, tool calls, plan depth, concurrency, memory, output and artifacts. Hosted models receive only metadata under explicit consent; source stays local/customer controlled.

### Security gate
Deterministic security checks: dependencies, SAST, secret/config scanning, authorization tests, network egress, host/guest attack matrix and receipt/evidence integrity. AI can suggest test cases, but a separate deterministic security gate decides the result.

Each gate reports PASS, FAIL, BLOCKED, SKIPPED, NOT_REQUESTED or ERROR. Required SKIPPED/NOT_REQUESTED cannot yield an overall passing run. Execution state, QA verdict and trust state remain separate.

## 7. Language profile contract

| Runtime | Initial baseline | Core test examples | Deep-test targets | Security test examples |
|---|---|---|---|---|
| Python | Python pinned image; FastAPI first | pytest/unittest, build/import, readiness | validation, state, exception, route edge cases | dependencies, static/config, auth, sandbox probes |
| Node.js | Node pinned image; Express first | npm/pnpm/Bun declared script, Jest/Vitest, readiness | async/error/middleware/API state cases | dependency audit, secrets, config, auth and sandbox probes |
| Go | Go pinned image; net/http first | go test, go vet, build, readiness | concurrency, cancellation and API cases | dependency/static/config and isolation checks |
| Java | JDK pinned image; Spring Boot baseline | Maven/Gradle, JUnit, startup | state, validation, exception and integration cases | dependencies, static/config, auth and isolation checks |

Every runtime and base image is pinned by immutable digest. Tool versions are not inherited from the customer workstation. Profile auto-detection is advisory; the resolved profile is recorded in the RunSpec.

## 8. GitHub private-source lifecycle

- Use GitHub App installation or another owner-approved least-privilege mechanism.
- Only request the minimal metadata/contents-read permission plus checks-write where necessary.
- Validate webhook signature, installation, repository identity, event ID and replay window.
- Host obtains short-lived source token; guest never receives it.
- Checkout by full commit SHA, never moving branch head.
- PR checks show Core, Deep AI and Security separately and point to a run/evidence summary.
- Duplicate webhook deliveries and retried submissions are idempotent.
- No automatic merge, branch write, force push or deployment in beta.
- On revocation, remove source connection, revoke token issuance and reject new runs.

## 9. Accounts and workspace authorization

Support a personal workspace and one or more organization/team workspaces per user. Candidate roles are Owner, Admin, Developer and Viewer; exact action permissions must be approved by GPT-6 contract work and Gemini review.

Every project, source connection, runner, run, finding, evidence bundle, receipt and audit event has workspace ownership. Workspace selection does not itself confer access: server derives authorization from authenticated membership. RLS and service-level checks are both required. Role downgrade/removal must invalidate access and queued work must re-check membership.

## 10. API-first, dashboard later

Define API schemas now for identity, workspaces, memberships, projects, sources, runners, RunSpec, runs, attempts, gates, findings, evidence, receipts, audit and GitHub checks. Use versioned OpenAPI and golden contract vectors. Existing FastAPI control plane is the baseline; no new Node service.

Dashboard implementation waits until:
- CLI core workflow passes;
- runner/run/evidence/gate contracts are stable;
- contract tests pass against FastAPI;
- individual and organization membership works;
- RLS and cross-tenant negative cases pass;
- pagination, idempotency, error handling and audit are defined;
- design maps to the same lifecycle and never invents its own statuses.

GLM may work on IA, copy and static prototypes before this gate, but no substantial dashboard integration.

## 11. Capacity model

The acceptance workload is 15 concurrent users with three run submissions each (45 requests). This tests user concurrency and queued workloads. It does not claim 45 concurrent Firecracker VMs.

Runner concurrency is bounded by customer-provided hardware and policies. The control plane must durably queue work above active runner slots, apply fair per-workspace scheduling and expose queue status. Load tests must measure API latency, queue age, dispatch delay, CPU/RAM/disk, database saturation, retries, lease recovery and artifact integrity. Kill/restart control plane and runner components to validate recovery; no accepted run may be lost, duplicated or attributed to another workspace.

## 12. Zero-budget operating model

- Customer provides strict execution compute and controls runner network placement.
- Customer supplies BYOK credentials.
- Control plane can run in customer-managed infrastructure.
- No Workflo-hosted GPU, model endpoint, browser farm, artifact store or always-on runner is assumed.
- Local development and CI use available project resources and should be quota-aware.
- Workflo-managed runner mode is a future architecture extension only.
- npm distribution is free to publish under existing package ownership; release automation must not require paid Workflo infrastructure.

## 13. Risk register

| Risk | Required mitigation |
|---|---|
| Native rewrite regresses Python workflow | command parity, compatibility adapter, rollback and delayed deletion |
| Cross-platform CLI implies false local isolation | clearly separate client OS support from Linux production runner |
| No budget conflicts with hosted SaaS assumptions | self-hosted/customer-owned execution; no unfunded cloud dependency |
| Multiple runs overload customer compute | durable queues, fairness, admission, quotas and measured backpressure |
| AI invents bugs | deterministic reproduction and evidence validation |
| Source leaks to hosted BYOK endpoint | typed metadata allowlist, default denial, consent and egress canaries |
| GitHub token reaches guest | host-only short-lived credential and cleanup proof |
| Competing schema/lifecycle emerges | canonical owner decision and golden vectors |
| Installer trusted by OS without valid signature | label unsigned status; no false signing/notarization claims |

## 14. What this plan does not authorize

No source-tree deletion/movement, autonomous merge/deploy, unrestricted guest shell, host Docker socket, new production isolation boundary, hosted model API service, Workflo-funded compute fleet, dashboard-first implementation, unapproved ADR ratification or fixed launch date.
