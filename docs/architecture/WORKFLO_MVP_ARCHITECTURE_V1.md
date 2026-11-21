# Workflo Trust Infrastructure — MVP Architecture v1

**Status:** Proposed architecture baseline for owner review  
**Repository baseline:** \`main\` at the time this branch was created  
**Scope:** Architecture and engineering plan only. No production code has been changed by this document.  
**Product decision:** Trust infrastructure for AI-produced and AI-operated software  
**Deployment decision:** Hybrid architecture; local/customer-controlled execution is mandatory  
**Budget posture:** No Workflo-funded cloud, GPU, observability, or SaaS dependencies for the MVP

---

## 1. Executive decision

Workflo should become **trust infrastructure for the AI software supply chain**. Its first product is not a general-purpose scanner, API monitor, autonomous coding agent, or generic sandbox. Its first product is a **verifiable change gate** for AI-native engineering teams.

The gate answers:

> Given this exact repository revision and its declared policy, what did Workflo execute, what did it observe, what passed or failed, what was not tested, and can an independent verifier confirm the evidence and teardown claims?

The first customer workflow is:

1. A developer or coding agent opens or updates a pull request.
2. GitHub Actions or the Workflo CLI starts a run on a customer-controlled runner.
3. Workflo pins the exact repository commit and resolves an immutable execution policy.
4. Deterministic checks run first: tests, build, type checks, dependency/secret checks selected by policy.
5. Optional bounded AI probes create additional test candidates or explore a running application through a restricted tool gateway.
6. Deterministic evaluators decide which findings are verified. Model output alone is never a verified failure.
7. The runner tears down the environment and independently checks cleanup.
8. Workflo emits a signed receipt, an evidence bundle, and a machine-readable verdict.
9. GitHub and the dashboard display the result. No automatic merge, deployment, or production mutation occurs.

This is the smallest coherent product that uses Workflo's current strengths: CLI, controlled execution, agent tool gateway, lifecycle supervisor, evidence ledger, receipt verification, control plane, and dashboard shell.

### 1.1 Product promise

**Verify every change. Govern every agent. Prove every run.**

This promise is intentionally narrower than “guarantee software is secure” or “prove software is correct.” A receipt proves the recorded scope, identity, policy, execution observations, verification steps, and limitations. It does not prove the absence of every defect or vulnerability.

### 1.2 Positioning and wedge

- **Category:** AI software trust infrastructure.
- **Entry point:** pull-request change verification for AI-native software teams.
- **Initial buyer:** CTO, VP Engineering, Head of Platform, or engineering lead at an AI-native B2B SaaS company.
- **Technical champion:** staff engineer, platform engineer, developer productivity lead, or AI engineering lead.
- **Initial environment:** GitHub, Python and TypeScript repositories, customer-owned Linux runner.
- **Initial outcome:** a verifiable, policy-governed run for an exact commit, including evidence and teardown status.

Do not start with continuous monitoring of every API, model provider, MCP server, warehouse, and data source. Those are expansion domains after the PR verification workflow is trusted and adopted.

---

## 2. Architecture principles

1. **Evidence before claims.** Every user-visible claim must point to a machine-verifiable event, artifact, check, or explicit limitation.
2. **Deterministic control plane.** Authentication, policy evaluation, run state transitions, permissions, resource limits, and signing are not LLM responsibilities.
3. **Customer-controlled source execution.** Repository content is acquired and executed on the customer's runner. The control plane receives metadata and approved evidence only; it does not receive a source archive.
4. **Default-deny execution.** No unapproved command, tool, filesystem path, network destination, or capability is available to a guest.
5. **No silent security downgrade.** A runtime that does not meet the declared isolation profile must be labeled as development-only or rejected. It must never be presented as equivalent to the production microVM boundary.
6. **No autonomous write-back in MVP.** Workflo may report, recommend, and later prepare a patch proposal. It cannot merge, deploy, or mutate a customer's remote branch without a separately implemented and explicitly approved flow.
7. **One contract authority.** Python Pydantic contracts in packages/workflo-schema are canonical. JSON Schema is exported for other languages; TypeScript schemas are generated or tested mirrors.
8. **One durable source of run truth.** PostgreSQL stores lifecycle state, transactional dispatch intent, event records, policy snapshots, evidence metadata, and receipt references. In-memory buses are development/test adapters only.
9. **Minimal viable infrastructure.** A modular FastAPI control plane, one PostgreSQL instance, one customer runner, one guest runtime, and one Next.js dashboard. No Kafka, Kubernetes, service mesh, Redis dependency, or paid telemetry platform in the MVP.
10. **Human authority remains explicit.** Agent proposals are not approvals. The exact action, scope, and content must be authorized by a human or a pre-approved policy.

---

## 3. MVP scope and explicit non-goals

### 3.1 Must ship in MVP

| Capability | MVP behavior | Acceptance evidence |
|---|---|---|
| CLI | Configure, run, inspect, verify, export evidence | CLI contract tests and clean installation |
| GitHub entry point | GitHub Actions workflow invokes the CLI on a customer-controlled runner | PR check points to exact commit and run |
| Repository identity | Provider, repository ID, ref, commit SHA, snapshot digest | Receipt binds all identifiers |
| Admission | Authorization, idempotency, policy resolution, resource limits | Rejected requests cannot provision a runner |
| Deterministic checks | Tests, build, type/lint, selected dependency and secret checks | Test result and tool version are recorded |
| Optional AI probes | Bounded plan and tool calls through a gateway | Every call is allowed or denied and recorded |
| Findings | Verified failure, candidate, inconclusive, infrastructure failure, not tested | Finding has evidence refs and detector identity |
| Evidence | Append-only, scoped, hashed evidence chain | Independent verifier rejects tampering |
| Teardown | Host-observed resource cleanup verification | Receipt includes teardown outcome |
| Receipt | New runs use receipt v5 contract; legacy receipts remain verifiable | Independent receipt verifier passes |
| Dashboard | Projects, runs, run detail, findings, activity, evidence, policies, settings | No mock data in production mode |
| Tenant controls | Organization-scoped queries, memberships, role checks, RLS | Cross-tenant negative tests pass |
| Deployment | Local Compose and customer-owned runner | No Workflo-funded hosted dependency |

### 3.2 Must not ship in MVP

- Autonomous merge or deployment.
- Open-ended agents with arbitrary shell, browser, network, or filesystem access.
- A public multi-tenant pool that runs untrusted repositories in Docker or bwrap and calls it production isolation.
- A Workflo-operated model-serving fleet, GPU cluster, or inference gateway requiring paid compute.
- A general MCP marketplace or arbitrary MCP tool execution.
- Slack/Teams/Jira/Linear bidirectional task management; outbound Slack/Teams notifications can be added after the core event contract is stable.
- SAML, SCIM, enterprise SSO, data residency controls, compliance certification, or a paid SLA.
- A broad API deprecation crawler or universal dependency graph.
- Automatic generated patches applied to a customer branch.
- Claims that the platform is “unhackable,” “zero risk,” “fully secure,” or “proves correctness.”

### 3.3 MVP release profiles

Workflo must label the runtime profile in every run and receipt.

| Profile | Use | Permitted claims |
|---|---|---|
| local-development | Current Docker/bwrap/namespace path for trusted developer code and CI regression | Development execution only; no production isolation claim |
| customer-microvm | Firecracker + jailer on customer-owned Linux/KVM host, after the security gate passes | Isolation claim limited to tested runtime/configuration and receipt scope |
| hosted-runner | Future Workflo-operated runner fleet | Not an MVP capability |

**Release rule:** no public or multi-tenant service may execute an untrusted customer repository until the customer-microvm Gate B test suite passes on the actual KVM host. If Firecracker/KVM is unavailable, fail closed for that run or require an explicitly selected local-development profile on trusted code.

---

## 4. System context and trust boundaries

### 4.1 Logical topology

\`\`\`text
Developer / AI coding agent
        |
        v
GitHub Pull Request ---- GitHub Actions workflow
        |                         |
        |                         v
        |                  Workflo CLI / API client
        |                         |
        v                         v
GitHub metadata             Workflo Control Plane
                                  |
                        PostgreSQL + transactional outbox
                                  |
                         outbound runner polling
                                  |
                                  v
                         Customer Runner Host
                         - repository acquisition
                         - policy verification
                         - Firecracker jailer
                         - host lifecycle observer
                                  |
                         typed vsock protocol
                                  |
                                  v
                         Per-attempt Firecracker VM
                         - source snapshot
                         - deterministic checks
                         - bounded agent runtime
                         - restricted tool gateway
                                  |
                         structured observations
                                  |
                                  v
                         Host Evidence Collector
                         - validate run/attempt scope
                         - hash evidence
                         - verify teardown
                         - invoke signer outside guest
                                  |
                                  v
                         Signed receipt + evidence bundle
                                  |
                   Control Plane metadata / Dashboard / CLI
\`\`\`

For a zero-cost developer setup, the control plane, PostgreSQL, dashboard, and runner may all run on one customer-owned Linux machine with Docker Compose. This is a deployment convenience, not a reason to collapse the security boundaries: guest code must remain separated from the host and control plane.

### 4.2 Trust zones

| Zone | Trust level | Contents | Rule |
|---|---|---|---|
| External event sources | Untrusted | PR titles, descriptions, comments, branch names, commit metadata, webhook body | Validate, bound, and treat as data |
| Control plane | Trusted control | Identity, tenant context, policy, admission, run state, dispatch | No execution of repository code |
| Runner host | Privileged trusted | Git fetch, VM lifecycle, host evidence, teardown observation | Narrow interfaces; no arbitrary guest host command |
| Guest VM | Untrusted workload | Repository, dependencies, test process, AI agent | Assume compromise from the first instruction |
| Model provider | Separate trust boundary | Model request and output | Send only policy-approved data; validate all output |
| Evidence/signing | Trusted control | Validated artifacts, ledger, signing key | Guest never holds private signing key |
| Browser client | Untrusted | User input, local state, route params | Server re-authorizes every operation |

### 4.3 Source-code privacy invariant

**Raw repository source, diffs, file contents, secrets, test fixtures, and source-bearing prompts must not be sent to a hosted model by default.**

- Local inference may receive source because it runs under the customer's control.
- Hosted BYOK inference may receive only an allowlisted, schema-constrained, redacted observation payload. It must not receive raw code, diffs, repository files, stack traces containing source, or secrets.
- If a task requires code-level reasoning, use local inference or deterministic analysis. Do not silently route it to a hosted provider.
- Model credentials are held by a host-side inference gateway and are never mounted into the guest.
- The current direct cloud LLM path in worker-engine must be disabled or routed through the same privacy gateway before any source-privacy claim is made. The existing environment-variable client is not, by itself, proof of the privacy boundary.

---

## 5. Service and module boundaries

MVP should be a **modular monolith plus an isolated runner/guest**, not a large microservice fleet.

### 5.1 Canonical components

| Component | Canonical location | Responsibility |
|---|---|---|
| Shared contracts | packages/workflo-schema | Pydantic models, JSON Schema export, lifecycle/outcomes/events/findings/evidence/policy/receipt/patch |
| Control plane | apps/control-plane | Auth, organizations, projects, admission, policy snapshots, run state, dispatch, API, audit |
| CLI | apps/workflo-cli | Local developer UX, auth, run, status, receipt verification |
| Runner host | apps/sandbox-executor plus supervisor | Acquire source, validate assignment, provision runtime, collect evidence, verify teardown |
| Guest worker | apps/worker-engine | Tests, web probes, bounded agent loop, tool gateway, structured observations |
| Dev isolation runtime | packages/sandbox-runtime | Local and CI security regression only until microVM gate |
| Model integration | migrate workflo-ai-integration into worker model package | Model routing, artifact identity, safety validation |
| Evidence and receipt | supervisor + sandbox-isolation + schema contracts | Host-side event ingestion, evidence validation, signing and verification |
| Dashboard | apps/dashboard | Canonical web application |
| Database migrations | packages/db as migration reference; Python Alembic remains runtime migration owner unless ratified otherwise | PostgreSQL schema and RLS |
| Event delivery | control-plane PostgreSQL outbox | Durable event storage, delivery leases, replay, polling |
| TypeScript contracts/events | packages/contracts and packages/events | Web-facing mirror and in-memory development adapter; not production source of truth |

### 5.2 Explicit ownership decisions

- **Canonical execution lineage:** Python.
- **Canonical API server:** apps/control-plane.
- **Canonical user-facing app:** apps/dashboard.
- **Canonical runtime:** Firecracker microVM for production untrusted workloads; existing Docker/bwrap paths are development/CI only.
- **Canonical contract authoring:** packages/workflo-schema.
- **Canonical run state:** frozen lifecycle in ADR-0017, not the old TypeScript 9-state enum.
- **Canonical evidence digest:** ADR-0016 profile, with legacy receipt/evidence verification retained.
- **Canonical signing:** receipt v5 flow from ADR-0018; signing key remains outside guest and ordinary worker.
- **Canonical patching:** ADR-0021 exact-byte proposal/approval protocol, but patch apply is not an MVP release dependency.
- **Autopilot capability:** integrate the existing data-platform capabilities into Workflo as a first-class product domain. Preserve the existing backend/ and frontend/ implementation initially behind Workflo service/API façades; map projects, users, assets, lineage, contracts, and evidence to canonical Workflo identities. Do not create a second identity, policy, audit, or evidence authority. Consolidate incrementally after parity and migration tests.
- **apps/dashboard:** replace the current Tenant Shield placeholder with Workflo's canonical experience; avoid building a second dashboard under frontend/.
- **workflo-ai-integration:** migrate the validated model router, artifact registry, schemas, and safety gate into the worker model module before removing the scaffolding.

These decisions should be reconciled with PRODUCT_BOUNDARIES.md and ADR-0015 through a reviewed architecture PR. They are not implemented merely because this document proposes them.

---

## 6. End-to-end run lifecycle

Use the product lifecycle already documented in ADR-0017:

\`\`\`text
CREATED
  -> ADMITTED
  -> PROVISIONING
  -> SOURCE_ACQUISITION
  -> PREPARING
  -> EXECUTING
  -> EVALUATING
  -> COLLECTING_EVIDENCE
  -> TEARDOWN
  -> VERIFYING_TEARDOWN
  -> SIGNING
  -> COMPLETED
\`\`\`

Failure terminals: REJECTED, INFRASTRUCTURE_FAILED, EXECUTION_FAILED, TEARDOWN_FAILED, ATTESTATION_FAILED. Cancellation is a request that proceeds through teardown; it is not permission to skip cleanup.

### 6.1 Three independent outcomes

Do not collapse execution state, QA verdict, and trust state into a single pass/fail field.

| Dimension | Values | Meaning |
|---|---|---|
| Execution | completed, rejected, infrastructure_failed, execution_failed, teardown_failed, attestation_failed, cancelled flag | Did the lifecycle complete? |
| QA verdict | pass, fail, warn, inconclusive, not_applicable | What did the checks conclude? |
| Trust | verified_clean, verification_failed, cleanup_incomplete, unknown | Can the evidence and teardown claims be trusted? |

Examples:
- Tests fail reproducibly and teardown verifies: execution completed; QA fail; trust verified_clean.
- Tests pass but teardown cannot be verified: execution teardown_failed or equivalent terminal; QA pass; trust cleanup_incomplete.
- Model output cannot be parsed: execution may complete with QA inconclusive; trust depends on evidence/teardown.
- Runner disappears: infrastructure_failed; QA inconclusive; trust unknown.

A “clean success” requires completed execution, no cancellation, and verified trust components. A “full pass” additionally requires QA verdict pass.

### 6.2 Admission sequence

Before provisioning:
1. Authenticate caller and resolve organization/project.
2. Verify requested permissions and repository authorization.
3. Validate repository URL/provider/ref and pin an exact commit SHA.
4. Check idempotency key and deduplicate the request.
5. Resolve a named policy profile to a complete immutable policy bundle.
6. Validate every policy component and recompute its digest.
7. Enforce maximum duration, memory, CPU, disk, process count, output bytes, agent iterations, model tokens, and network profile.
8. Persist run, attempt, policy snapshot, and outbox dispatch row in one transaction.
9. Transition CREATED to ADMITTED.
10. Reject before VM provisioning if any check fails.

### 6.3 Run/attempt model

- A run is the user-visible request and stable identity.
- An attempt is one concrete execution, with an exact runner/runtime/source/policy identity.
- Retries create a new attempt; they do not overwrite previous attempt evidence.
- Every event and artifact binds org, project, run, attempt, and sandbox where applicable.
- A retry cannot reuse the previous attempt's approval, mutable workspace, model context, or signing material.

---

## 7. Repository acquisition and dependency handling

1. Resolve repository identity using provider repository ID, not only a mutable name.
2. Pin the exact commit SHA; never use a moving branch name as the executed revision.
3. The runner acquires source using a short-lived read-only credential.
4. The credential remains on the host and is never passed to the guest.
5. Create a content-addressed source snapshot and record its digest.
6. Pass a read-only source mount or immutable block image to the guest; writable state is a separate ephemeral overlay.
7. Remove or strictly scope Git metadata and credential helpers before guest execution.
8. Do not accept arbitrary clone URLs without strict provider and host validation. Block local addresses, loopback, link-local, metadata-service addresses, private ranges unless explicitly configured, redirects to unapproved hosts, and URL credential material.
9. Dependencies are installed from lockfiles. For the strict profile, prefetch artifacts through a controlled host-side registry proxy/cache and run package installation offline in the guest.
10. If controlled network access is later required, it must be an explicit, per-run allowlist routed through a host gateway. No guest may directly reach arbitrary Internet destinations.

The first supported provider is GitHub. GitLab and generic Git providers follow only after the GitHub path is reliable.

---

## 8. Agent architecture

MVP does not need a swarm of independent agents. It needs one deterministic orchestrator and a small number of bounded agent roles.

### 8.1 Agent roles

| Role | Type | Inputs | Outputs | Authority |
|---|---|---|---|---|
| Run orchestrator | Deterministic service | Run spec, policy, runner status | State transitions and stage dispatch | Owns lifecycle |
| Repository analyzer | Deterministic + optional local model | Snapshot, manifests, diff metadata | File/dependency/change inventory | Read-only |
| Test planner | Optional LLM | Policy-safe repository context, test framework inventory | Typed test-plan proposal | Propose only |
| QA probe agent | Bounded guest agent | Approved tool list, test plan, app endpoint | Tool calls and observations | Only through ToolGateway |
| Evaluation judge | Deterministic | Test outputs, observation records, criteria | Verified finding / candidate / inconclusive | Owns verification classification |
| Security policy gate | Deterministic | Tool/action request, immutable policy | Allow/deny decision | Owns capability authorization |
| Patch proposer | Deferred | Verified finding and exact base snapshot | Immutable PatchProposalV1 | No apply authority |
| Evidence verifier | Deterministic host service | Artifacts, ledger, run identity, teardown | Validation result | May authorize signing |
| Signer | Isolated host-side process | Fully validated receipt payload | Signed envelope | Signs only; cannot alter results |

### 8.2 Agent execution protocol

\`\`\`text
OBSERVE
  -> PLAN
  -> POLICY_CHECK
  -> EXECUTE_TOOL
  -> COLLECT_OBSERVATION
  -> EVALUATE
  -> REPORT
\`\`\`

- All proposed tool calls are schema-validated before execution.
- The ToolGateway checks action, arguments, resource budget, host/path allowlist, and policy digest.
- A denied call is recorded as a denial; it is not retried with weaker permissions.
- The agent cannot edit policy, change its own tools, alter run state, sign receipts, read host credentials, or access another tenant.
- Limits are enforced outside the prompt: maximum iterations, calls, bytes, wall time, concurrency, and model tokens.
- Untrusted repository files, comments, test output, web pages, and issue text are treated as data, not trusted instructions.
- Store concise rationale, action, observation, evidence reference, model identity, and timing. Do not store chain-of-thought.
- A model-generated test is a candidate until it compiles, passes policy checks, executes in the guest, and produces reproducible evidence.
- A model cannot create a verified_failure finding. Only deterministic verification can assign that category.

### 8.3 MVP agent budget

Start with:
- One repository analysis stage.
- One optional test-planning call.
- One probe loop with a hard maximum of 12 steps per batch and a bounded total iteration budget.
- One deterministic judge.
- One evidence verifier.

Do not create agents for status updates, summarization, policy decisions, or simple deterministic transformations.

---

## 9. Inference and model privacy architecture

### 9.1 Supported modes

| Mode | Location | Allowed context | MVP status |
|---|---|---|---|
| disabled | None | No model calls | Supported and default-safe |
| customer-local | Customer runner or local endpoint | Source context within customer boundary | Preferred for code-aware reasoning |
| customer-hosted BYOK | Customer-selected hosted endpoint through Workflo privacy gateway | Redacted, allowlisted observations only | Optional; customer bears provider cost |
| Workflo-hosted inference | Workflo-operated service | N/A | Out of scope until funded |

### 9.2 Hard rules

- The runner chooses the model route from the immutable policy bundle, not from model output.
- A hosted model request must pass a strict request schema. Do not implement the privacy boundary as a keyword filter alone.
- No source file, diff, code snippet, source-bearing stack trace, secret, environment value, or raw test fixture may enter the hosted request.
- Do not mount hosted model API keys into a guest VM.
- Use request size, token, timeout, retry, and per-run budget caps.
- Record model provider, model ID, artifact digest where applicable, schema version, usage counts, latency, error category, and route. Do not persist raw prompt/response bodies by default.
- If privacy gateway validation is uncertain or unavailable, deny the hosted request; do not bypass the gateway.
- The existing worker cloud client must be disabled until it uses this same gateway. The local llama.cpp runtime remains the preferred path for source-aware tasks.
- Customer-provided keys are environment/secret-manager inputs on the customer host, not Workflo-owned credentials. Do not create a Workflo-funded model budget.

### 9.3 Model acceptance

No model is accepted based on a demo alone. It must pass:
1. Schema conformance.
2. Prompt-injection test corpus.
3. Tool-argument abuse corpus.
4. Cross-run and cross-tenant leakage tests.
5. Output redaction tests.
6. Regression evaluation on a held-out dataset.
7. Latency and resource limits.
8. Explicit fail-closed behavior on malformed output, timeout, provider errors, and policy denial.

---

## 10. Communication and integration architecture

“Communication platform” means three separate capabilities. Keep their boundaries clear.

### 10.1 Internal service communication

**MVP transport: PostgreSQL transactional outbox and append-only run events.**

- Admission writes the run/attempt and dispatch intent in one database transaction.
- Runner claims work using a lease with expiry, heartbeat, bounded retries, and fencing/attempt identity.
- Every event has event ID, org/project/run/attempt ID, sequence, type, producer, occurred_at, correlation ID, payload digest, and schema version.
- Event payloads are strict, size-capped, contain no chain-of-thought, and reject unknown fields.
- Event append is durable before notification.
- Consumers store a cursor/sequence and can replay missed events.
- The dashboard uses authenticated polling initially; SSE is a later optimization.
- In-process event bus is only for tests and local composition.
- Do not introduce Kafka, NATS, RabbitMQ, or Redis as a core dependency in the no-budget MVP.

The existing durable dispatch logic in apps/control-plane is the starting point. The old list-based Redis/in-memory queue must not become the production system of record.

### 10.2 External developer integrations

| Integration | MVP | Later |
|---|---|---|
| GitHub Actions | Yes; primary entry point | Keep |
| GitHub App | No public webhook dependency initially | Installation, webhook-driven automation, Checks API |
| GitHub Checks API | Not until GitHub App exists | Create checks and annotations |
| Slack | No | Outbound alerts via signed webhook |
| Microsoft Teams | No | Outbound alerts |
| Jira / Linear | No | Link findings to existing tickets |
| GitLab | No | Provider adapter |
| MCP | No arbitrary tools in MVP | Carefully scoped connector after threat review |
| VS Code | CLI integration only | Thin extension over stable API |

GitHub Actions avoids the need to operate a public webhook endpoint during the no-budget phase. The CLI can run inside the customer's self-hosted runner. The GitHub Checks write API requires a GitHub App, so do not pretend a normal OAuth token or personal token is an equivalent implementation.

### 10.3 In-product collaboration

MVP collaboration is:
- Run timeline and event log.
- Reviewable findings with evidence references.
- Policy view and policy version history.
- Approve/reject controls only for future patch proposals.
- Comments/annotations associated with a finding can be added after the first end-to-end run.

Do not build a separate chat product. Do not allow a conversation message to become an execution instruction without passing the same admission and policy gates as any other action.

---

## 11. Frontend architecture and product experience

### 11.1 Canonical app

Build on apps/dashboard as the canonical Workflo application shell. Bring the existing data-platform experience and workflows into this dashboard incrementally. Initially retain backend/ and frontend/ behind authenticated Workflo service/API façades; share canonical Workflo identity, tenant scope, policy, audit, and evidence. Migrate routes and components only after API and data-model parity tests. Do not maintain two competing user experiences or duplicate security authorities.

### 11.2 MVP route map

| Route | Purpose | MVP |
|---|---|---|
| /login | Authentication | Yes |
| /device | CLI device authorization | Yes |
| /app | Authenticated entry redirect | Yes |
| /app/overview | Recent runs, trust summary, quick start | Yes |
| /app/projects | Organization projects | Yes |
| /app/projects/new | Connect repository / setup instructions | Yes |
| /app/projects/[projectId] | Project overview and run history | Yes |
| /app/runs | Filterable run list | Yes |
| /app/runs/[runId] | Run status, findings, outcome dimensions, event timeline | Yes |
| /app/runs/[runId]/evidence | Receipt, evidence artifacts, verification metadata | Yes |
| /app/policies | Read and manage policy profiles | Read-only + file-based MVP |
| /app/integrations/github | GitHub Actions setup and status | Yes |
| /app/settings | Members, API keys, runner setup | Minimal |
| /app/audit | Tenant audit records | Later |
| /app/agents | Agent performance analytics | Later |
| /app/integrations/slack | Slack connection | Later |
| /app/integrations/teams | Teams connection | Later |

### 11.3 Core UI components

Create reusable components under apps/dashboard/components:
- AppShell, PrimaryNavigation, OrganizationSwitcher.
- ProjectCard, RepositoryIdentity, RunnerStatus.
- RunTable, RunStatusTimeline, OutcomeSummary.
- FindingList, FindingDetail, EvidenceReference.
- PolicySummary, PolicyDiff, PolicyEditor (read-only until policy validation is complete).
- AgentActivityTimeline (sanitized events only).
- ReceiptSummary, ReceiptSignatureStatus, EvidenceChainViewer.
- EmptyState, ErrorState, LoadingSkeleton, PermissionDenied.
- CopyCommandButton, InstallInstructions, ApiKeyCreateDialog.

### 11.4 UI behavior

- Never silently substitute mock data when API calls fail. Demo mode must be explicit and visibly labeled.
- Every view is tenant-authorized server-side; hiding a button is not authorization.
- Run states are derived from the canonical contract.
- Display execution, QA, and trust outcomes separately.
- Show “not tested” distinctly from “passed.”
- A model-generated candidate is visually distinct from a verified failure.
- Evidence pages expose what the receipt proves and its limitations.
- Do not expose raw prompts, secrets, source code, or internal model reasoning.
- Start with responsive desktop-first UX; no complex graph visualization is required for the MVP.

### 11.5 Frontend data flow

- Next.js server components load initial organization/project/run summaries using server-side API credentials.
- Client components use typed API functions for interactive run timelines and filters.
- Every API call includes request correlation and tenant context from authenticated server session; never accept org ID as sole authorization evidence from browser input.
- Use React Query only if the current app shell needs client cache; do not add a second data store.
- Typed contracts mirror exported JSON Schema from packages/workflo-schema. CI compares them to the canonical export.
- Browser local storage must not hold long-lived access tokens. Prefer secure, HttpOnly, Secure, SameSite cookies for browser sessions with CSRF protections.

---

## 12. Backend API design

All public APIs remain under /v1. Use the existing FastAPI control plane as the canonical API.

### 12.1 Public endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| POST | /v1/runs | Admit an idempotent run request |
| GET | /v1/runs | List authorized runs |
| GET | /v1/runs/{run_id} | Read run status and outcomes |
| GET | /v1/runs/{run_id}/events?after={sequence} | Replay run events |
| GET | /v1/runs/{run_id}/findings | Read scoped findings |
| GET | /v1/runs/{run_id}/receipt | Retrieve receipt envelope/metadata |
| POST | /v1/receipts/verify | Verify a supplied receipt/evidence bundle or return verifier result |
| GET | /v1/projects | List projects |
| POST | /v1/projects | Create project |
| GET | /v1/projects/{project_id} | Read project |
| GET | /v1/policies | Read policy profiles |
| POST | /v1/policies/validate | Validate a proposed policy bundle |
| GET | /v1/integrations/github | Read GitHub integration status |
| POST | /v1/audit/query | Query authorized audit metadata |

The existing OAuth/device endpoints and key provisioning endpoints remain available under the current contract. New fields must be additive or versioned according to docs/api_contract.md.

### 12.2 Runner-only endpoints

These require a runner identity and a short-lived, scoped capability; normal user/API-key credentials are not accepted.

| Method | Endpoint | Purpose |
|---|---|---|
| POST | /v1/runner/leases/claim | Claim one eligible attempt |
| POST | /v1/runner/leases/{lease_id}/heartbeat | Renew lease |
| POST | /v1/runner/leases/{lease_id}/events | Append bounded guest/host observations |
| POST | /v1/runner/leases/{lease_id}/artifacts | Register evidence metadata and digest |
| POST | /v1/runner/leases/{lease_id}/complete | Submit outcomes and receipt reference |
| POST | /v1/runner/leases/{lease_id}/fail | Report infrastructure/teardown/attestation failure |

Runner endpoints enforce lease expiry, exact attempt identity, fencing token, policy digest, body size limits, strict schemas, and replay protection.

### 12.3 API conventions

- Idempotency-Key on run creation and all retryable write endpoints.
- Request ID and correlation ID returned in response headers.
- Consistent error envelope with stable error codes; no stack traces in public responses.
- Pagination uses opaque cursors, not unbounded offset scans.
- Timestamps are UTC.
- All IDs are opaque and unguessable, but authorization never relies on ID secrecy.
- Public endpoints are rate-limited per organization and caller.
- No endpoint accepts an arbitrary shell command, arbitrary path, arbitrary URL to fetch, or arbitrary model target without policy resolution.

---

## 13. Data model and persistence

PostgreSQL is the source of truth for multi-user runs. SQLite may be used for local tests and single-user development only; do not claim PostgreSQL RLS guarantees on SQLite.

### 13.1 Core entities

| Entity | Required fields / relations |
|---|---|
| organizations | id, name, status, created_at |
| users | id, identity, status, created_at |
| memberships | org_id, user_id, role, state |
| projects | id, org_id, name, provider, repository_id, repository_url, default_ref |
| github_installations | org_id, installation_id, repository allowlist, credential reference |
| runners | id, org_id, name, runtime capabilities, version, status, last_seen |
| runner_leases | id, runner_id, run_id, attempt_id, lease expiry, fencing token |
| policies | id, org_id, name, version, immutable payload, digest |
| runs | id, org_id, project_id, requester, idempotency key, lifecycle state, outcomes |
| run_attempts | id, run_id, org_id, attempt number, source SHA, snapshot digest, runtime identity |
| dispatch_outbox | id, org_id, attempt_id, event type, payload, state, lease, retry metadata |
| run_events | event identity, tenant/run/attempt scope, sequence, type, producer, digest, previous hash |
| findings | id, run/attempt scope, category, severity, detector, evidence refs, verification stamp |
| evidence_artifacts | id, run/attempt scope, type, media type, size, digest, classification, retention, object ref |
| evidence_manifests | attempt scope, artifact digest set, ledger root, event count |
| receipts | run/attempt scope, schema version, payload digest, signer identity, envelope ref |
| audit_log | org scope, actor, action, resource, result, request ID, timestamp |
| inference_usage | run/attempt, provider class, model ID, token counts, latency, error class; no prompt body |
| webhook_deliveries | future GitHub App delivery ID, signature result, event/action, processed state |

### 13.2 Tenant isolation rules

- Every tenant-owned row includes org_id, including join tables and event/evidence records.
- Enable RLS on every tenant-owned table and use FORCE ROW LEVEL SECURITY where appropriate.
- Runtime database role is not a superuser, table owner, or BYPASSRLS role.
- Set organization/user context transaction-locally and clear it automatically at transaction end.
- Missing tenant context denies reads and writes.
- All writes validate org_id against the authenticated actor or runner capability.
- Composite foreign keys include org_id where possible to prevent cross-tenant relation creation.
- Add negative tests for SELECT, INSERT, UPDATE, DELETE, joins, nested relations, exports, and guessed IDs across tenants.
- Administrative/background roles are explicit, separately permissioned, and audited.

PostgreSQL documents that superusers and BYPASSRLS roles bypass row security and table owners normally bypass it unless FORCE ROW LEVEL SECURITY is used. RLS therefore requires database-role discipline; enabling policies alone is insufficient.

### 13.3 Retention and storage

- No source archive is stored by the control plane.
- Temporary source snapshots and writable overlays are deleted at teardown.
- Evidence is metadata-first. Large artifacts remain on the customer runner or customer-selected object store.
- The MVP stores small signed receipt payloads and redacted metadata locally.
- Retention is configurable by policy; defaults must be explicit in the product and tested.
- No raw prompt/response persistence by default.
- Backup/restore procedure and key recovery must be documented before hosted multi-tenant production.

---

## 14. Internal event contract

Use the RunEventV1 contract proposed in ADR-0020.

Required envelope:
- event_id
- org_id, project_id, run_id, attempt_id
- sequence_number
- event_type and schema_version
- occurred_at (canonical UTC millisecond string)
- producer component, role, instance ID, and version
- correlation_id
- payload_digest
- previous_hash / ledger binding
- strict payload with unknown keys rejected

Rules:
- Events are append-only. Corrections create a superseding event; they do not mutate finalized evidence.
- A guest event is an observation, not a lifecycle transition.
- Only trusted-control authorities may transition the product run state.
- A guest cannot invent host teardown proof or receipt-signing success.
- Chain-of-thought keys and free-form internal reasoning fields are rejected.
- Consumers are idempotent and cursor-based.
- The ledger commit occurs before any best-effort notification.
- An event whose payload cannot be validated is rejected and audited.

The existing TS in-memory bus documents the correct concept that delivery is not truth. Reuse the contract idea, but production delivery must use durable PostgreSQL records and replay, not an in-process subscriber set.

---

## 15. Security architecture

### 15.1 Threat model

Assume attackers can:
- Submit a malicious pull request or dependency.
- Put prompt-injection instructions in README, comments, issue text, test output, or generated documentation.
- Attempt path traversal, symlink escape, command injection, SSRF, DNS rebinding, or resource exhaustion.
- Replay a run request, webhook, runner lease, or approval.
- Guess another tenant's IDs or exploit a forgotten tenant filter.
- Tamper with receipts, evidence artifacts, or event order.
- Abuse an overprivileged GitHub credential or model tool.
- Compromise the guest process and attempt to access the host.
- Exploit a compromised dependency, model artifact, container image, or build workflow.

### 15.2 Mandatory controls

**Identity and authorization**
- Use existing OAuth device flow for CLI and scoped API keys for CI.
- Hash API keys at rest; show plaintext once; support rotation/revocation.
- Separate scopes for run:create, run:read, receipt:read, policy:manage, project:manage, runner:register.
- Use short-lived runner credentials bound to org, project, run, attempt, policy digest, expiry, and fencing token.
- Require re-authorization for privileged actions; do not trust frontend state.
- Browser session uses secure HttpOnly cookies, CSRF protection, strict origin checks, and session rotation.

**Webhook / GitHub**
- In the first phase, use GitHub Actions rather than public webhook ingestion.
- When a GitHub App is added: validate X-Hub-Signature-256 over the unmodified raw body using constant-time comparison; check event type/action; deduplicate X-GitHub-Delivery; store delivery state; respond quickly and process asynchronously.
- Subscribe to the minimum events and grant minimum permissions.
- Never put credentials in callback URLs, PR comments, or logs.
- Checks API write operations require a GitHub App; use a proper App installation token when that feature is introduced.

**Tenant boundary**
- PostgreSQL RLS on all tenant-owned tables.
- Runtime DB role is non-owner and non-superuser with no BYPASSRLS.
- FORCE RLS where required.
- Tenant context is set transaction-locally; missing context fails closed.
- Cross-tenant access tests run on every PR, not as an optional manual test.

**Execution isolation**
- Production untrusted code: per-attempt Firecracker microVM with pinned Firecracker and jailer, dedicated non-privileged host identity, cgroups, namespaces, seccomp, strict host filesystem permissions, resource limits, and regular host/guest patching.
- No host Docker socket or host filesystem access is exposed to guest.
- No host shell command API.
- Guest-host interface is a narrow typed vsock protocol with sequence numbers, size caps, attempt binding, and an allowlist of operations.
- Egress defaults to deny; dependency fetching is performed before guest execution or through a tightly controlled proxy.
- Teardown is host-observed and independently verified.
- If the runtime cannot prove its configured boundary, reject the run or mark trust unknown; never silently fall back.

**Tool and agent security**
- Typed allowlisted tools only; no general shell in the agent.
- Exact file roots and URL hosts are bound to policy.
- Validate canonicalized paths after resolving symlinks; reject traversal, symlink escape, path separator ambiguity, and special files.
- Protect against SSRF at both application and network layers, including redirects and resolved IP ranges.
- Tool definitions are versioned and hashed. Changes require code review and tests.
- Model output is untrusted input. Parse strictly, validate schemas, then validate semantics and policy again before execution.
- Prompt injection cannot grant permissions, change system policy, or access credentials.
- All tool calls (allowed and denied) are recorded as bounded metadata.

**Model privacy**
- The default hosted route accepts no source-bearing payload.
- BYOK does not mean unrestricted data transfer.
- Local model endpoints bind to loopback or a private customer network, are not public by default, and are checked for identity/config drift.
- Model artifacts and adapter manifests are digest-pinned.
- No API key or credential is included in a model prompt or guest environment.

**Evidence and signing**
- Guest has no signing key.
- Evidence service validates run/attempt/tenant scope, artifact digests, canonical event chain, outcome semantics, policy digest, model/runtime identity, and teardown proof before constructing a receipt v5 payload.
- Signer is outside guest and ordinary worker.
- Development signing key is explicitly marked as development-only; production startup refuses it.
- Independent verifier validates signature and factual bindings separately.
- Legacy receipts v1-v4 remain verifiable.

**Supply chain and build**
- Lock Python and Node dependencies; pin action and base-image digests for release workflows.
- Run static analysis, type checks, tests, dependency vulnerability checks, secret scanning, and container scanning where relevant.
- Generate an SBOM for release images when practical.
- Protect release branches and require reviewed changes to workflow files, dependencies, policies, and runtime images.
- Do not store secrets in CI artifacts or debug logs.

**Abuse and availability**
- Per-tenant request and concurrency limits.
- Hard caps on CPU, memory, disk, process count, log bytes, output bytes, wall time, model calls, and model tokens.
- Backpressure and queue lease expiry.
- Bounded retries; retries create new attempts.
- No unbounded recursion, crawling, or agent loops.

### 15.3 “Hard to break” security target

No architecture can guarantee that an experienced attacker cannot break in. The measurable goal is to make compromise materially harder, contain a compromised guest, prevent cross-tenant access, detect tampering, fail closed on missing security controls, and make every security claim independently testable.

Use OWASP ASVS 5.0 as the application/API verification checklist, OWASP LLM Top 10 as the AI threat checklist, and NIST SSDF as the secure development lifecycle baseline. These are engineering baselines, not certification claims.

---

## 16. Observability and operations

No paid monitoring platform is required for the MVP.

- Structured JSON logs with request_id, org_id, project_id, run_id, attempt_id, component, event_type, and error_class.
- Redact authorization headers, API keys, repository credentials, environment values, prompt bodies, code, and raw test output.
- Local metrics endpoint and OpenTelemetry SDK instrumentation; exporter is configurable and disabled or local by default.
- Keep run-level audit separate from diagnostic logs.
- Health checks: liveness, readiness, database, runner heartbeat, model route readiness, runtime capability, and signing readiness.
- Avoid logging payloads just to debug agent failures; log schema errors, IDs, byte counts, and error classes.

Core metrics:
- workflo_runs_total by execution outcome and QA verdict
- workflo_run_duration_seconds
- workflo_queue_wait_seconds
- workflo_runner_lease_expired_total
- workflo_agent_tool_calls_total by tool and allow/deny
- workflo_agent_budget_exhausted_total
- workflo_teardown_verification_failures_total
- workflo_receipt_verification_failures_total
- workflo_evidence_replay_failures_total
- workflo_model_requests_total by provider class/model
- workflo_model_latency_seconds
- workflo_model_tokens_total
- workflo_tenant_rls_denials_total

---

## 17. Zero-budget deployment model

### 17.1 Development environment

One developer-owned machine:
- Docker Compose for PostgreSQL and local services.
- FastAPI control plane.
- Next.js dashboard.
- CLI and runner host process.
- Firecracker only on Linux/KVM-capable hardware.
- Existing bwrap/namespace runtime for development and regression tests, clearly marked non-production.
- Local inference only when suitable hardware/model artifacts are available; otherwise model features are disabled.

No paid database, queue, object storage, model API, logging vendor, or Kubernetes cluster.

### 17.2 Design-partner pilot

Prefer a customer-owned Linux/KVM runner:
- Customer keeps repository checkout and execution artifacts.
- Runner initiates outbound HTTPS connections; no inbound port is required.
- Workflo control plane can be customer-hosted in Compose for the first pilot.
- If the control plane is hosted later, it stores metadata and approved evidence only.
- Customer brings any hosted model/API credentials; no Workflo-funded usage.
- If a partner cannot supply a supported isolation host, limit testing to trusted code and do not represent the run as an untrusted-code security boundary.

### 17.3 Infrastructure intentionally deferred

- Workflo-operated production multi-tenant hosting.
- Managed PostgreSQL, Redis, Kafka, Kubernetes.
- KMS/HSM signing service.
- Centralized object storage.
- GPU inference fleet.
- 24/7 alerting and paid observability.
- Multi-region deployment and disaster-recovery service.
- Enterprise identity and compliance programme.

### 17.4 Cost guardrails

- No background cloud resources.
- All external providers are disabled unless explicitly configured by the customer.
- Per-run resource and token budgets are mandatory.
- Default model mode is disabled or customer-local.
- Local telemetry only.
- CI is limited to necessary test suites and public fixture repositories.
- No paid SaaS dependency is a merge requirement unless an approved budget exists.

---

## 18. Quality strategy and acceptance gates

### Gate A — contract consistency
- Python contracts are the only authored source.
- JSON Schema export and TypeScript mirrors match.
- Lifecycle transition tests cover all allowed and denied edges.
- Canonical JSON cross-language fixtures match.
- Receipt v1-v4 verification regression remains green.

### Gate B — execution isolation
- Firecracker and jailer are pinned.
- KVM and host capabilities are verified before admission.
- Guest cannot access host files, host process, Docker socket, credentials, signing key, or another VM.
- Egress defaults deny.
- Resource limits are verified.
- VM crash, timeout, force termination, and host reboot paths are tested.
- Teardown proof is independent from guest self-report.
- No Docker/bwrap fallback is accepted as a production microVM run.

### Gate C — tenant and API security
- Cross-tenant read/write tests cover every entity.
- Missing tenant context denies.
- User and runner scopes are tested separately.
- IDOR, replay, duplicate idempotency, lease expiry, stale fencing token, and rate-limit tests pass.
- Public errors do not reveal internal secrets or stack traces.

### Gate D — agent and model security
- Prompt-injection corpus cannot expand tool access.
- Unknown tools and malformed arguments are denied.
- Path traversal and symlink escape are denied.
- SSRF and redirect attacks are denied.
- Model output is strictly parsed and independently validated.
- Hosted privacy gateway rejects source-bearing data.
- Agent loop, token, timeout, and output limits are enforced.

### Gate E — evidence integrity
- Tampered receipt rejected.
- Tampered artifact rejected.
- Cross-run/cross-tenant reference rejected.
- Event sequence/hash mismatch rejected.
- Missing teardown evidence prevents clean trust status.
- Guest cannot forge host-observed evidence.
- Signer refuses incomplete payloads.
- Independent verifier succeeds from a clean environment.

### Gate F — product workflow
- One real AI-native repository can connect.
- One PR update produces one idempotent run against the exact commit.
- Run status and event history are visible in dashboard.
- Findings link to evidence.
- Signed receipt verifies offline.
- No source is present in control-plane storage or hosted model requests.
- A human can explain why the verdict was pass, fail, warn, inconclusive, or not tested.

### Pilot metrics

Do not publish targets as achieved until measured. Establish baselines for:
- Time from PR update to verdict.
- False-positive and false-negative rates on labeled fixtures.
- Dependency/change mapping precision and recall.
- Percentage of generated test candidates accepted after validation.
- Teardown verification rate.
- Receipt verification rate.
- Agent tool-denial rate and policy violations.
- Setup time to first successful run.
- Minutes saved per PR and buyer willingness to pay.

---

## 19. Phased engineering plan

### Phase 0 — architectural consolidation
1. Ratify ownership: Python lineage, apps/dashboard, canonical contracts.
2. Reconcile PRODUCT_BOUNDARIES.md with ADR-0015 and the current trust product identity.
3. Freeze MVP scope and prohibit unrelated feature work.
4. Export canonical JSON Schemas and create Python/TypeScript consistency tests.
5. Identify model-serving paths that bypass the privacy gateway.
6. Establish one end-to-end golden fixture repository.

**Exit:** one architecture, one contract authority, one supported product workflow.

### Phase 1 — local-first vertical slice
1. Run a local CLI against a pinned repository commit.
2. Execute deterministic tests and build checks through the existing executor.
3. Produce structured findings and evidence events.
4. Verify teardown and create a signed development receipt outside the guest.
5. Verify the receipt using an independent CLI command.
6. Make run outcomes distinguish product failure from infrastructure failure.

**Exit:** repeatable local run with independently verifiable evidence. The runtime must be labeled development-only unless Gate B passes.

### Phase 2 — control plane and dashboard
1. Use PostgreSQL locally.
2. Implement organization/project/policy/run/attempt models and RLS.
3. Use transactional outbox and lease semantics.
4. Add authenticated run, event, finding, and receipt APIs.
5. Build apps/dashboard pages for projects, runs, evidence, and settings.
6. Remove implicit mock fallback from production mode.

**Exit:** one user can create a project, submit a run, follow it, inspect evidence, and verify the receipt.

### Phase 3 — GitHub and runner integration
1. Add a documented GitHub Actions example that invokes the CLI.
2. Use a self-hosted customer runner for the strict runtime.
3. Pin commit identity and bind the result to the PR SHA.
4. Post a concise status/comment using the permissions available to the Action.
5. Add webhook/GitHub App only when a public endpoint and App credentials are available.

**Exit:** every PR update is tied to an idempotent, exact-commit Workflo run.

### Phase 4 — security and microVM release gate
1. Implement Firecracker runner host and typed vsock protocol.
2. Implement host-only source acquisition and evidence collection.
3. Enforce jailer, seccomp, cgroups, namespaces, dedicated identity, no guest secrets, and default-deny egress.
4. Complete adversarial test matrix and independent teardown verification.
5. Run Gate B on actual customer-owned KVM infrastructure.
6. Keep strict production claims disabled until evidence is retained and reviewed.

**Exit:** security claims match the proven runtime profile.

### Phase 5 — bounded AI features
1. Merge model router and artifact registry into the worker.
2. Make local inference the source-aware route.
3. Add hosted BYOK through a strict metadata-only privacy gateway.
4. Add the bounded test-planner and probe workflow.
5. Validate every tool action and finding deterministically.
6. Benchmark model utility against deterministic-only baseline.

**Exit:** AI demonstrably improves useful coverage without weakening policy, privacy, or evidence.

### Phase 6 — paid-pilot readiness
1. Run with three design partners on customer-controlled infrastructure.
2. Measure setup time, usefulness, trust, false positives, and cost.
3. Document support boundaries and installation runbook.
4. Prepare hosted control plane only after repeated demand and funding.
5. Expand to Slack/Teams, GitHub App, IDE and MCP connectors based on validated requests.

**Exit:** at least one repeatable workflow with a customer willing to pay; expansion decisions are evidence-based.

---

## 20. Decisions deferred until funding

| Future capability | Why deferred |
|---|---|
| SaaS control plane at scale | Requires operating budget, reliability, backup, and support |
| KMS/HSM signing service | A local host-side signer is sufficient for the pilot; production central signing requires infrastructure |
| Multi-tenant runner fleet | Expensive and materially increases isolation/operations burden |
| SAML/SCIM | Not needed to validate MVP buyer demand |
| Full object storage and evidence retention service | Customer-local evidence is enough initially |
| Redis/Kafka | PostgreSQL outbox is adequate at MVP throughput |
| Model serving fleet | Customer-local/BYOK routes avoid Workflo compute costs |
| Slack/Teams and task trackers | GitHub PR status is the highest-value initial feedback path |
| VS Code extension | CLI and GitHub are enough to validate workflow |
| Broad API/model dependency monitoring | Expand after PR trust gate achieves adoption |
| Automatic patch apply | Requires exact-byte approval, new sandbox apply, retest, and remote-write security review |

---

## 21. Repository-level ownership summary

| Path | Disposition |
|---|---|
| packages/workflo-schema | Canonical contracts; extend and export schemas |
| apps/control-plane | Canonical API, auth, admission, tenant, outbox, events, policy |
| apps/workflo-cli | Canonical developer entry point |
| apps/sandbox-executor | Host-side execution adapter; add strict runtime selection |
| apps/worker-engine | Guest worker and bounded agents |
| supervisor | Lifecycle orchestration and host evidence coordination |
| packages/sandbox-runtime | Dev/CI isolation only until microVM gate |
| workflo-ai-integration | Merge validated router/registry/gate into worker; retire scaffolding later |
| apps/dashboard | Canonical web app; replace Tenant Shield placeholder |
| packages/db | PostgreSQL migration/RLS reference; align with Python runtime migration owner |
| packages/contracts | Validated Zod mirror of canonical Pydantic/JSON Schema |
| packages/events | In-memory development bus; production truth remains DB ledger/outbox |
| backend/ and frontend/ | Existing data-platform implementation to integrate incrementally behind Workflo service/API façades; migrate UI into apps/dashboard after parity tests |
| apps/agent-cli | Evaluate for overlap with canonical workflo CLI; do not introduce a second default command |
| action/ | Legacy/archive; use existing CLI in GitHub Actions first |

---

## 22. Research and standards references

These references inform the design; they do not imply Workflo is compliant or certified.

1. Firecracker production host setup: https://github.com/firecracker-microvm/firecracker/blob/main/docs/prod-host-setup.md
2. Firecracker security design and threat containment: https://github.com/firecracker-microvm/firecracker/blob/main/docs/design.md
3. Firecracker seccomp defaults: https://github.com/firecracker-microvm/firecracker/blob/main/docs/seccomp.md
4. OWASP LLM Application Top 10: https://owasp.org/www-project-top-10-for-large-language-model-applications/
5. OWASP Application Security Verification Standard 5.0: https://asvs.owasp.org/
6. NIST SP 800-218 Secure Software Development Framework: https://csrc.nist.gov/pubs/sp/800/218/final
7. PostgreSQL Row Security Policies: https://www.postgresql.org/docs/current/ddl-rowsecurity.html
8. GitHub webhook best practices: https://docs.github.com/en/webhooks/using-webhooks/best-practices-for-using-webhooks
9. GitHub webhook signature verification: https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries
10. GitHub Checks API: https://docs.github.com/en/rest/checks/runs
11. MCP authorization security considerations for a future MCP connector: https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization/security-considerations

---

## 23. Architecture acceptance statement

This document is the proposed MVP architecture, not proof that the current repository implements it.

No production security claim may be made until the corresponding gate has passed on the actual deployment profile. In particular:
- Existing Docker/bwrap tests do not satisfy the Firecracker production boundary.
- Mock model tests do not satisfy real model acceptance.
- A valid Ed25519 signature does not by itself prove the facts in a receipt.
- A dashboard hiding an action does not enforce authorization.
- A hosted model key supplied by a customer does not authorize sending source code to that provider.
- A passing test suite does not prove the absence of vulnerabilities.

The next engineering task after architecture approval is Phase 0: reconcile the existing ADRs/contracts and create the end-to-end golden fixture. Do not start by adding agents, queues, microservices, or dashboard pages disconnected from that workflow.
