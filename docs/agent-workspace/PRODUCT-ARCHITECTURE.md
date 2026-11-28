# Workflo Product Architecture — CLI-First, Customer-Controlled Execution

## 1. Architecture principles

1. **CLI-first:** the CLI is the first complete user experience and is not dependent on the dashboard.
2. **One execution authority:** a customer-controlled runner provisions and supervises workloads; the CLI and dashboard never execute source directly.
3. **MicroVM boundary:** Firecracker/KVM remains the only strict production execution profile under ADR-0022.
4. **No silent downgrade:** missing KVM, invalid guest image, missing network policy or failed teardown is an explicit admission/infrastructure/trust failure.
5. **Customer-controlled by default:** customer compute and customer BYOK credentials are used first.
6. **Provider-minimal:** Workflo does not provide or fund LLM API models for this launch. The five development models are not product providers.
7. **Metadata-only hosted prompts:** only explicit, allowlisted, sanitized metadata can be sent to an external provider after per-project and per-run consent.
8. **Tenant isolation:** identity, organization, project, runner, run, artifact and secret scopes are enforced server-side and in PostgreSQL.
9. **Evidence before claims:** every security or privacy claim maps to a test and retained evidence.
10. **Scale by capacity:** scheduler admission derives from measured runner capacity, not an assumed VM count.

## 2. Logical planes

### 2.1 Client plane

- Native Go executable named workflo.
- Local configuration, OS credential-store integration and command UX.
- GitHub/local connector client flows.
- Run submission, status, cancellation, logs, evidence and offline verification.
- JSON output and stable exit-code contract for CI.
- No customer source is uploaded to the control plane by default.

### 2.2 Control plane

Retain the existing FastAPI/PostgreSQL implementation as the starting backend; do not rewrite the server in Go merely because the CLI/runner becomes Go.

Responsibilities:
- Individual and organization authentication.
- Organization membership, roles and project membership.
- GitHub App installation and token brokering.
- Project and policy registry.
- Run admission and idempotency.
- Durable transactional outbox and run-attempt state.
- Runner enrollment, identity, capabilities, health and lease.
- Capacity-aware dispatch.
- Receipt/evidence metadata and authorization.
- Audit events, usage budgets and rate limits.
- API contracts consumed by CLI and later dashboard.

The control plane must not be a source-code execution service. The control plane stores metadata and dispatch intent; the runner acquires/executes source.

### 2.3 Customer runner / execution plane

A customer installs the runner on an eligible Linux KVM host. It makes outbound authenticated connections to the control plane; inbound internet access to the runner is not required.

Responsibilities:
- Register runner identity and capabilities.
- Claim authenticated run assignments.
- Enforce assignment expiry, attempt binding and quotas.
- Resolve source using a scoped connector capability.
- Build/verify immutable source and runtime artifacts.
- Provision a fresh Firecracker microVM per attempt.
- Apply CPU, memory, disk, process, time and network limits.
- Start the guest supervisor and typed vsock protocol.
- Receive bounded guest observations.
- Terminate the VM and independently verify host resources are removed.
- Persist run evidence locally until authorized upload/synchronization.
- Produce signed receipt inputs through trusted host-side verification.

The runner agent is not a generic remote shell. It exposes only a narrow host API.

### 2.4 Guest execution plane

A fresh guest receives:
- pinned guest kernel/rootfs and runtime identity;
- immutable run ID and attempt ID;
- policy digest and permitted capability set;
- an exact source snapshot;
- explicit test profile and bounded argv;
- temporary, scoped credentials only if absolutely required and approved by a separate design.

It does not receive:
- host credentials;
- GitHub installation tokens;
- BYOK provider secrets;
- cloud metadata access;
- host filesystem mounts;
- Docker socket;
- general internet egress;
- authority to select host commands or alter the policy.

The guest runs test tooling and the optional governed agent. It never decides whether its own teardown succeeded.

## 3. Control and data flows

### 3.1 Run submission

1. CLI authenticates and resolves a project.
2. CLI resolves the repository and full commit SHA.
3. CLI builds a versioned RunSpec with policy/test profile identifiers, resource bounds and consent flags.
4. CLI sends POST with an Idempotency-Key.
5. Control plane validates user, org/project membership, quotas, repository authorization, schema, profile and consent.
6. One database transaction creates Run, RunAttempt and DispatchOutbox.
7. API returns a run ID and queued/admitted state; it does not claim that execution has started.

### 3.2 Runner dispatch

1. Runner authenticates with workload identity/mTLS or an equally strong enrolled identity protocol.
2. Runner claims a lease for a matching eligible run.
3. Control plane verifies runner eligibility and tenant/project assignment.
4. Assignment contains attempt-bound policy, runtime/guest image digests, resource limits, network policy, capabilities, expiry and nonce.
5. Runner validates assignment cryptographically and semantically before provisioning.
6. Lease heartbeat renews while the run executes.
7. Expired lease recovery fences the previous attempt; duplicate claims cannot start duplicate active VMs for the same attempt.

### 3.3 Source acquisition

- GitHub App installation tokens remain server/host-side, short-lived and repository-scoped.
- Runner obtains a narrowly scoped acquisition capability through the connector/token-broker protocol.
- Source is fetched at an exact full commit SHA.
- Git submodules, LFS and symlinks must follow explicit policy; default deny or require a declared allowlist.
- The runner verifies source inventory and digest.
- Source is placed into a fresh guest-visible block/disk artifact; do not mount the host's working filesystem.
- Credentials are removed before guest execution and are never placed in RunSpec, logs, receipt or guest environment.
- The acquisition and test phases are separate. Dependency preparation is network-restricted and policy-bound; sealed test execution uses deny-by-default egress.

### 3.4 Execution

- One microVM per run attempt.
- A retry gets a new attempt identity and a fresh VM.
- Profiles resolve to pinned toolchain images and structured command argv.
- User-controlled command strings are never concatenated into a host shell.
- Commands run inside the guest under the assigned policy.
- stdout, stderr, logs, test reports and artifacts have size and retention caps.
- The guest reports evidence references; the trusted host validates hashes and inventories.

### 3.5 Completion and proof

- Test results are evaluated independently of infrastructure outcome.
- Host supervisor requests guest shutdown and force-terminates after bounded grace.
- Independent host probes verify process, jailer, VM, cgroup, namespace, network, disk and temporary capability cleanup.
- Trust status is one of the canonical outcomes; unknown/incomplete is never converted to clean.
- Receipt signing occurs only after all required claims are independently validated.
- Offline verification checks signature, trusted key, evidence hashes, policy/run/attempt/source binding and lifecycle semantics.

## 4. Native Go component layout

Proposed Go modules (subject to a recorded ADR and existing package audit):

- apps/workflo-cli-go — user-facing workflo binary and CLI command tree.
- apps/workflo-runner-go — customer runner daemon, control-plane client and host supervisor.
- packages/workflo-protocol-go — generated/validated protocol models from canonical schemas.
- packages/workflo-policy-go — deterministic admission and capability policy types/evaluation, generated or parity-checked against canonical contract sources.
- packages/npm-workflo — npm/pnpm/Bun distribution shim and platform-specific optional binary dependencies.

Do not create a second Firecracker runtime. The Go runner must progressively replace or wrap the existing Python host implementation under worker/ only after contract parity and real KVM acceptance. Keep the Python path as a development/reference path until the Go path passes the same Gate B evidence. Guest test engines and framework adapters may remain Python/Node/Go/Java as appropriate.

## 5. Why Go, not Rust, for this programme

This is a schedule/maintainability decision, not a security claim:
- Go's static cross-compilation and simple deployment model suit one CLI binary across Linux/macOS/Windows.
- Standard library support reduces dependencies for network, TLS, process and file handling.
- A single Go implementation avoids operating two native language runtimes.
- The current team can integrate Go faster while retaining Python test adapters.

Go does not automatically make Firecracker safe. The actual boundary comes from Linux/KVM, Firecracker/jailer, kernel configuration, cgroups, seccomp, network controls, capability design and independent teardown evidence. Avoid unsafe Go packages and CGO in the CLI unless a specific dependency requires it and has a documented review.

## 6. Operating system matrix

### CLI client

- Linux x86_64: native release binary.
- Linux ARM64: release only when build/test runners exist.
- macOS arm64 and x86_64: native client binary; local strict runner not claimed.
- Windows x86_64: native client binary; local strict runner not claimed.
- Windows ARM64: later, after toolchain and installer validation.

### Runner

- Linux x86_64 with accessible KVM is the strict release target.
- Linux ARM64 is conditional on Firecracker support, guest image pipeline and real integration acceptance.
- macOS/Windows clients connect to a registered Linux runner.
- WSL2/Docker/bwrap is a developer/compatibility mode only and must be marked non-strict in the CLI, API and receipt.
- No native Hypervisor.framework/Hyper-V strict backend is in scope; it needs a separate security ADR.

## 7. Four initial language ecosystems

The runner supports four pinned profile families:

| Ecosystem | Default test entry | Common project files | Notes |
|---|---|---|---|
| Python | pytest | pyproject.toml, requirements/lock files | FastAPI/Flask/Django app lifecycle through explicit profile metadata |
| Node.js | npm/pnpm/Bun test scripts and Playwright | package.json and lockfiles | Express/Next.js supported through declared app profile |
| Go | go test ./... | go.mod | Toolchain pinned in guest profile |
| Java | Maven or Gradle test | pom.xml, gradlew/build.gradle | JDK and build tool pinned |

Detection is advisory; it must not silently execute arbitrary scripts. The user or a reviewed Workflo config selects the exact profile/argv. Lockfiles are preferred; non-lockfile installs are marked non-reproducible. No dependency install runs in the sealed test stage unless a separate policy explicitly admits it.

## 8. Core, deep and security stage separation

### Core
- Declared unit/integration tests.
- Health/readiness and deterministic smoke tests.
- Exact configured command arrays.
- Test results and baseline comparison.

### Deep AI-assisted
- Bounded application/API/browser exploration.
- Candidate edge-case proposals.
- Structured plans validated by deterministic schema and ToolGateway policy.
- Generated test artifacts remain reviewable artifacts; no auto-commit/auto-merge.
- Provider use requires per-run consent and BYOK.
- Metadata-only external payload contract.

### Security
- Dependency/security posture checks, static analysis and explicitly scoped application probes.
- No arbitrary external scanning.
- Target scope must be the selected repository/application or an explicitly authorized test environment.
- High-impact security tests have separate profile authorization, egress scope, resource limits and receipt claims.
- Security findings require reproduction and severity triage; model text alone is not a vulnerability.

A run may combine these stages, but each stage has a separate policy, result and evidence outcome. Failure of one stage cannot silently erase or overwrite another stage's result.

## 9. BYOK inference data path

1. Organization admin enables an approved provider and data-handling policy.
2. User sees the provider, model identifier, categories that may leave the customer environment, timeout/budget and relevant retention terms.
3. User explicitly consents to hosted metadata inference for the project and the individual run.
4. The customer runner retrieves a provider credential from an OS secret store/approved local vault; it is not passed to the guest.
5. A runner-side privacy broker accepts only versioned allowlisted observation types.
6. It rejects source, file contents, raw logs, raw bodies, headers, cookies, environment variables, credentials and free-form unreviewed text.
7. It creates a new provider prompt itself; the agent/guest cannot submit arbitrary prompts.
8. Egress is restricted to the selected provider origin.
9. Provider output is schema-validated and converted into a typed plan.
10. Every proposed tool call is independently authorized by the deterministic ToolGateway.
11. Provenance records provider/model identity, schema and policy version, payload field classes, sizes, request count and timings—not raw source or secrets.

BYOK is not consent to send source code. Explicit metadata consent is required. If a provider endpoint or data category is not approved, hosted inference is unavailable and the run can continue only with a deterministic mode that does not require it.

## 10. Zero-budget and hosted mode

Zero-budget means Workflo does not operate a shared execution fleet or subsidize customer LLM calls for this release.

- Customer-owned runner is the default and launch path.
- Self-hostable control plane and customer-managed Postgres are the baseline deployment path.
- A low-cost hosted control plane can be a later service, but is not assumed to exist for launch.
- Workflo-managed hosted execution remains disabled until funded, capacity-engineered, monitored and separately security-accepted.
- A customer can use their own cloud VM/KVM machine as a customer-controlled runner; the customer pays their infrastructure provider.
- Local artifact storage on the customer runner is the zero-cost default. External object storage is an optional customer-provided adapter.

## 11. 10–15 user and multiple-run design

The platform must pass:
- 15 concurrent authenticated client sessions.
- 45 run submissions in a short burst (3 per user) with no lost intent.
- Idempotent retries after client/network timeout.
- Fair queueing between organizations/projects.
- Per-user, project, organization and runner resource budgets.
- Runner capacity advertisement and atomic reservations.
- Runner lease, heartbeat and recovery.
- Cancellation and timeout propagation.
- No duplicate active VM for one attempt.
- No cross-tenant run/evidence access.

The number of simultaneously executing VMs is capacity-dependent. The load programme measures 1/5/10/15/30 concurrent attempts across available customer runner hosts where safe; the product reports measured capacity and queue state instead of promising a fixed VM count.

## 12. Control-plane scale design

- PostgreSQL is the durable source of truth.
- Transactional outbox persists admission and dispatch intent in one transaction.
- Lease-based runner claims with expiry, fencing and heartbeat.
- Idempotency key on run creation and other mutating requests.
- Per-org/project/user quotas and weighted fair queueing.
- Database RLS enabled and tested with a non-owner/non-superuser application role.
- SQLite/in-memory queue only for local development and tests; never silently used in production.
- Redis is optional for ephemeral fanout/cache, not the durable queue authority.
- API pagination, filtering, bounded payloads and request timeouts.
- Artifact content is separate from control-plane metadata and stored in customer-controlled storage by default.
- No synchronous API request waits for a complete sandbox run.

## 13. Main risks

| Risk | Mitigation |
|---|---|
| Go rewrite breaks working Python path | Strangler migration, contract parity, feature gates and dual-run fixtures |
| Windows/macOS implied to have strict local isolation | Explicit client-vs-runner support matrix |
| Source or secrets leak to BYOK provider | Runner-side schema allowlist, explicit consent, outbound payload assertions |
| GitHub credential leaks to guest | Host-only token broker, short-lived token, no secret in RunSpec |
| Duplicate run from retry/worker restart | Transactional outbox, idempotency, attempt fencing and leases |
| Tenant data leak | Server authorization + PostgreSQL RLS + cross-tenant negative tests |
| Resource exhaustion | Per-run hard limits, capacity admission and fair queue |
| AI plan executes unsafe action | Model is planner only; deterministic ToolGateway authorizes |
| False trust/success receipt | Independent verifier and teardown evidence |
| Zero-budget promise conflicts with hosted execution | Customer-managed default; hosted fleet disabled until funded |
