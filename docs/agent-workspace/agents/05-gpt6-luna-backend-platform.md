# Agent 05 — GPT-6 Luna
## FastAPI Control Plane, API Contracts, Identity, Tenancy, Persistence and Backend Reliability

**Workstream:** Control plane and platform backend  
**Branch:** `agent/gpt6-luna-backend-platform`  
**Implementation owner:** GPT-6 Luna  
**API/runner integration reviewers:** DeepSeek V4.1 Flash-1017  
**CLI/connector consumer reviewer:** GLM-5.3 Flash  
**Privacy/policy reviewer:** MiniMax M3.1 Flash  
**Dashboard consumer reviewer:** Gemini 4 Hydrogen  
**Human approver:** product owner for schema, tenancy, security and release decisions

---

## 1. Mission and expected outcome

Own the existing FastAPI/Python control plane and the API contract that the native Go CLI, customer Go runner, GitHub integration and later dashboard consume. Deliver a durable, tenant-safe, observable control plane that accepts a run request, resolves identity and authorization, admits a policy-bound immutable RunSpec, persists run/attempt/dispatch intent atomically, assigns work to an eligible customer runner, tracks leases and lifecycle events, and exposes only authorized run/evidence/receipt metadata.

The beta must support individual users and organization/team workspaces. The specified workload is 10–15 concurrent users, each able to submit multiple runs; the acceptance scenario is 15 authenticated users × 3 submissions (45 durable run requests). Do not translate this into a promise of 45 simultaneous VMs.

The control plane remains Python/FastAPI/PostgreSQL under ADR-0024. Go is used for native CLI and runner, not for a backend rewrite.

**Your output is not a large collection of unimplemented endpoints.** Every API operation must have a principal, authorization rule, request/response schema, idempotency/fencing behavior, error model, persistence semantics, audit event and executable tests.

## 2. Why this model owns the work

OpenAI's GPT-6 Luna announcement reports DeepSWE v1.1 at 66.6% at max effort and describes focused, efficient coding/tool work. The published evaluation is a repository-engineering signal; it is not a benchmark specifically for backend architecture, database security or tenancy. The assignment therefore remains a routing hypothesis. Workflo-specific calibration, PostgreSQL/RLS tests, independent MiniMax security review and human approval determine whether implementation is accepted.

Sources:
- https://openai.com/index/introducing-gpt-6-sol-and-luna/
- https://developers.openai.com/api/docs/models/gpt-6-luna

## 3. Authority and path ownership

### Primary owned paths
- `apps/control-plane/` — FastAPI routes, services, models, config and application wiring.
- `apps/control-plane/tests/` — backend/unit/integration tests.
- Existing control-plane PostgreSQL migrations and `db/rls/` where current project boundaries place them.
- `docs/agent-workspace/API-CONTRACT-FREEZE-M1.md` and approved API contract documentation.
- API contract fixtures, OpenAPI and generated client validation under the currently approved contract home.
- Backend load/chaos test harness for admission, dispatch, membership and tenant behavior.

### Shared/reserved paths
- `packages/workflo-schema/`: canonical Pydantic source is proposed/initial; preserve owner-approved contract authority. A schema edit is a reserved task requiring explicit owner decision.
- `packages/contracts/`: TypeScript mirror/compatibility types; do not create a second lifecycle authority.
- `worker/`, `apps/workflo-runner-go/`: DeepSeek owns runner implementation.
- `apps/workflo-cli-go/`, command handlers/connectors: DeepSeek/GLM split.
- `packages/workflo-policy-go/`, `security/`, `tests/security/`: MiniMax owns policy/security test source.
- `apps/dashboard/`: Gemini owns frontend.
- `website/`, `backend/`, `frontend/` adjacent Cortex Autopilot and marketing surfaces are not Workflo control-plane paths.

### Must not do
- Do not rewrite the FastAPI control plane in Go.
- Do not implement CLI commands, runner host or dashboard pages.
- Do not redefine receipt/lifecycle/evidence/policy semantics unilaterally.
- Do not add a new backend service merely because a new UI/API route is needed.
- Do not expose provider/GitHub secrets in API responses, logs, exceptions or events.
- Do not trust client-supplied org/project/workspace IDs as authorization.
- Do not set production RLS bypass, run application as table owner/superuser, or fall back to SQLite/in-memory queue in production.
- Do not enable hosted model prompts without consent and metadata-only enforcement.
- Do not declare a cross-tenant or production security gate passed on SQLite-only tests.

## 4. Current-state baseline that must be re-verified first

The current repository audit documents these facts; re-check them at the assigned base SHA before relying on them:

1. `apps/control-plane/app/main.py` registers health, runs, keys, artifacts, audit, orgs, auth, key provisioning, inference, voice and OAuth routers. There is no registered runner/worker API router in the audit baseline.
2. `apps/control-plane/app/api/v1/runs.py` exposes existing V1 run endpoints. The main `POST /v1/runs` request is built around `workflo_schema.api.RunRequest` and the `require_api_key` dependency. It is not automatically an OAuth device-flow bearer endpoint.
3. The existing dispatch/outbox path atomically creates a TestRun, first RunAttempt and DispatchOutbox record. Preserve this durable admission foundation.
4. `dispatch_service.py::execute_payload` currently invokes `workflo_executor.SandboxExecutor`; it is not the signed assignment → enrolled Firecracker runner path.
5. `worker/src/workflo_worker_host/` contains a Firecracker/jailer/assignment/network/vsock/teardown foundation but is not connected to a registered runner API/claim lifecycle in the M1 audit.
6. Current User/Organization/Project structures have foundations, but the membership/role/invitation model required for team workspaces is incomplete. A single `org_id` and `project_id` on User cannot represent multiple organization memberships.
7. Existing project-scoped PostgreSQL RLS and production startup guards are useful foundations. Re-run them with a non-owner, non-superuser PostgreSQL application role that does not have BYPASSRLS.
8. SourceSpec V1's commit validation may accept abbreviated commit IDs (7–64 hex). M1 requires a full SHA-1 object ID for GitHub SHA-1 repositories. Tighten this only through an approved versioned contract, not by silently changing V1.
9. Receipt V5 writer/verifier and legacy receipt readers need explicit reconciliation. Preserve v1–v4 verification.
10. Development defaults (SQLite, disabled RLS, demo token, in-memory or disabled dispatcher) must remain development-only and must fail closed in production.

Deliverable: a current-state audit with exact file/symbol/route/model/migration references, test commands, pass/fail/skip counts and a comparison against these known gaps.

## 5. Contract freeze responsibilities

### GPT-01 — Existing API/schema/auth audit
Map:
- registered FastAPI routes and dependencies;
- request/response Pydantic schemas;
- OpenAPI output and generated clients;
- auth principals, OAuth device flow, refresh, revoke and development tokens;
- User, Organization, Project, API key, TestRun, RunAttempt, DispatchOutbox, Artifact and AuditEvent models;
- RLS SQL/policies, database role assumptions and startup guards;
- dispatcher/lease/heartbeat/recovery functions;
- GitHub installation/webhook/check-run code;
- inference/BYOK configuration and every outbound provider path;
- API callers in CLI, runner, dashboard, Actions and scripts.

Deliverables:
- endpoint inventory with auth principal and owner;
- schema/table/foreign-key map;
- current identity and project membership map;
- list of compatibility surfaces;
- current test baseline and known failures;
- current direct inference egress map.

Acceptance: no new route/model/migration in this task.

### GPT-02 — M1 API contract and OpenAPI
Publish versioned OpenAPI 3.1 contracts for the minimum CLI → control plane → customer runner vertical slice. Reconcile against `docs/agent-workspace/API-CONTRACT-FREEZE-M1.md`.

The proposal includes:
- current user/project selection (reuse compatible route or add versioned endpoint);
- run admission with exact immutable source identity;
- run/attempt retrieval;
- runner enrollment and runner identity;
- runner self/capability status;
- attempt claim, heartbeat, lifecycle events, completion and classified failure;
- runner drain/revoke;
- receipt/evidence metadata access;
- GitHub installation/check-run support only where needed by M1;
- stable health/readiness and protocol compatibility metadata.

For every endpoint specify:
- method/path/version;
- principal and scopes;
- resolved tenant/project context;
- request and response schema;
- all required/optional fields and constraints;
- maximum body/field/list sizes;
- request/correlation ID;
- idempotency/replay semantics;
- lease/attempt fencing;
- pagination and ordering where applicable;
- rate limits and retry rules;
- errors and retryable classification;
- audit event;
- persistence transaction;
- contract tests;
- implementation owner and status.

**M1 RunSpec requirements:**
- canonical provider/repository identity;
- full immutable commit ID, SHA-1 full 40 hex for M1 GitHub;
- snapshot digest when produced;
- profile ID/version;
- policy ID/version/digest;
- guest image/kernel/rootfs digest(s);
- runner ID or authorized runner-pool selector;
- resource ceilings and network policy;
- requested gate/stage information allowed in M1;
- privacy and consent state (M1 may keep inference disabled);
- schema version and correlation IDs.

Do not put source bytes, private keys, GitHub tokens, provider keys or raw log body in RunSpec or control-plane API payload.

Acceptance:
- OpenAPI lint passes;
- request/response examples validate;
- generated Go/TypeScript consumers compile against the version;
- golden fixtures are checked in;
- V1 compatibility suite stays green;
- no unapproved canonical schema change.

### GPT-03 — Principal and authorization model
Define different security principals:
1. human user / CLI;
2. runner workload identity;
3. GitHub App installation/repository grant;
4. legacy API key where still supported.

These principals are not interchangeable. A user token cannot claim a runner attempt; a runner certificate cannot create a user session; a GitHub installation identity cannot access arbitrary Workflo workspaces.

For every operation define:
- principal type;
- authentication mechanism;
- permission required;
- organization/workspace/project scope;
- resource ownership;
- expected audit event;
- revocation/expiry behavior.

Never trust `organization_id`, `workspace_id` or `project_id` from client body as proof of access. Resolve authorized membership server-side and bind the chosen project to the session/request.

Acceptance:
- user A cannot read/write another project/org by changing IDs;
- user token cannot impersonate runner;
- runner cannot select another org's work;
- revoked installation and revoked runner denied;
- unauthorized IDs do not disclose cross-tenant object existence.

## 6. Identity and team workspace workstream

### GPT-04 — Individual account and personal workspace
Specify a personal workspace distinct from an organization. User sign-up/login must create or attach a personal workspace idempotently. Every project/run/evidence resource belongs to a workspace. Account suspension/deletion and workspace archival semantics must be explicit.

### GPT-05 — Organization/team model
Support:
- multiple organizations per user;
- membership status and invitation;
- Owner, Admin, Developer, Viewer roles;
- invitation expiry/revoke/accept;
- member removal and role downgrade;
- ownership transfer / last-owner protection;
- project membership or well-defined role inheritance;
- runner-pool ownership/shared-use policy;
- source connection permissions;
- workspace audit events.

Create an action-level permission matrix, not ordinal role checks. Include:
- create/list/read/update/archive workspace;
- invite/accept/revoke/remove member;
- change role/transfer ownership;
- create/list/update/archive project;
- connect/disconnect/revoke GitHub;
- submit/cancel/retry run;
- read/download/export evidence and receipt;
- enroll/drain/revoke runner;
- change policy;
- add/rotate/delete BYOK secret;
- export audit/usage.

Acceptance:
- two organizations and one user belonging to both;
- personal workspace isolation;
- expired invitation and replay denied;
- last owner cannot remove itself without transfer;
- role downgrade removes high-impact permissions immediately;
- queued runs revalidate authorization before claim;
- every membership/policy/integration change creates audit event.

Do not delay M1's single-user deterministic execution milestone by prematurely building all team UI. However the broader beta must pass this work before claiming multi-user/team support.

## 7. PostgreSQL persistence, RLS and migration engineering

### GPT-06 — Data model and tenant ownership
For every table, record:
- tenant/workspace owner;
- project/run parent;
- foreign key and cascade behavior;
- uniqueness scope;
- soft delete/archive/retention rules;
- API permission;
- audit requirement;
- index/query patterns.

Add explicit workspace/org identity to tenant-owned entities only after migration design and owner contract approval. Do not add an `org_id` to every table without reasoning about parent ownership and migration compatibility.

### GPT-07 — PostgreSQL RLS hardening
- PostgreSQL is mandatory for production.
- Use a dedicated application role that is not table owner, not superuser and has no BYPASSRLS.
- Enable/force RLS where appropriate.
- Set organization/project context transaction-locally and clear it safely before pool connection reuse.
- Ensure background dispatch/worker service principals have least-privilege access and explicit role context.
- Keep API service authorization in addition to RLS.
- Prevent query paths that bypass tenant scoping.
- Production startup guards fail if PostgreSQL/RLS/credential encryption/durable dispatcher requirements are disabled.

Acceptance tests must use an actual PostgreSQL service and realistic application role, not SQLite-only tests:
- same connection used sequentially for tenants A and B;
- pooled connection reuse with no context leakage;
- direct object ID guessing;
- list/filter/export queries;
- insert/update with wrong tenant ID;
- background dispatcher scope;
- service account BYPASSRLS absence;
- rollback/migration safety;
- backup/restore access and encryption metadata.

### GPT-08 — Durable dispatch/outbox, attempt lease and recovery
Preserve and extend the existing transactional outbox. A successful admission is durable only when Run + initial Attempt + Outbox intent commit atomically.

Requirements:
- unique idempotency scope and request body digest;
- same key + same body returns the same intent/result;
- same key + different body returns conflict;
- no VM is started before committed admission;
- bounded claim query;
- attempt lease + generation/fencing token;
- lease expiry and recovery produce a new attempt only after previous execution is fenced/terminated;
- duplicate worker claim cannot start two VMs for one attempt;
- heartbeat does not hold DB connection for entire VM run;
- cancellation is a request, not proof of VM termination;
- queue saturation returns durable queued state and visible backpressure;
- outbox replay/restart never loses accepted run intent.

Acceptance:
- DB transaction failure between records leaves no partial run/outbox;
- control-plane process killed after commit → outbox recovered;
- duplicate submit with retries does not create duplicate attempts;
- two runners race for one attempt;
- lease expires mid-run;
- runner disconnect and reconnect;
- cancel during queued/provisioning/execution/teardown;
- dispatcher restart and DB restart;
- 15 users × 3 submissions with constrained runner slots.

## 8. Runner API and protocol coordination (DeepSeek dependency)

### GPT-09 — Runner control-plane APIs
Implement the approved endpoint surfaces only after the M1 contract is frozen:
- enrollment token issue/exchange and revocation;
- runner identity/certificate registry;
- runner self/capability/health read;
- claim eligible work with one current attempt;
- heartbeat with monotonic sequence and fencing token;
- lifecycle event ingestion with idempotent event IDs;
- complete/fail with evidence manifest metadata and host teardown result;
- drain/revoke and runner lease cleanup.

Runner auth must be separate from user auth. No long-lived human bearer token as runner credential. Claim response has a signed/immutable assignment binding run, attempt, sandbox, source SHA, policy digest, image digest, resource budget, network policy, capability IDs, nonce, expiry, claim generation and protocol version.

Acceptance:
- enrolled runner can claim only assigned scope;
- expired/revoked identity cannot claim/heartbeat/complete;
- stale fencing token cannot modify terminal attempt;
- duplicate event id is idempotent;
- wrong run/attempt/sandbox tuple denied;
- oversized/malformed event rejected;
- assignment expiry and key rotation tested.

### GPT-10 — Integration with existing dispatch
Current dispatch invokes a development SandboxExecutor in the audited baseline. M1 strict dispatch must not quietly call that executor or treat it as a Firecracker runner. Implement an additive runner dispatch adapter and preserve development behavior only behind an explicit dev-only profile. Never convert a failed strict dispatch into a Docker/bwrap fallback.

## 9. GitHub server-side integration

### GPT-11 — GitHub App installation, webhook and PR check API
Coordinate client UX with GLM, runner source acquisition with DeepSeek, and adversarial tests with MiniMax.

Responsibilities:
- validate OAuth/App installation callback state and CSRF;
- store App private key only server-side using configured secret storage;
- issue short-lived installation token scoped to selected repo and permission set;
- webhook signature validation and delivery-id deduplication;
- event replay/window checks;
- repository installation/grant lookup;
- source access capability broker for customer runner;
- separate GitHub source identity from runner and user identity;
- publish separate Core, Deep AI and Security check statuses tied to exact commit/run;
- store check-run IDs and update idempotently.

Launch permission policy:
- metadata read;
- contents read;
- checks write only if PR/commit status required;
- PR read only if required;
- no contents write, admin, branch protection, merge or deployment permissions.

Acceptance:
- invalid signature/replay rejected;
- duplicate delivery no duplicate run;
- selected repository only;
- private repo source token never reaches guest, model or receipt;
- installation revoke prevents future clone;
- check result bound to exact repository, full SHA, run ID and gate.

## 10. BYOK and metadata-only hosted prompt backend

Workflo does not supply API models, API credits or a customer model marketplace. Customer supplies provider credentials and controls provider relationship. MiniMax owns policy tests/negative data-class tests; GPT-6 owns API, persistence and gateway business behavior.

### GPT-12 — Credential metadata and write-only secret reference
- secret write endpoint accepts secret once and returns opaque ID/version;
- read endpoint never returns secret bytes;
- secret encrypted at rest with key separation/envelope model;
- no value in SQL logs, trace, audit payload, error or metrics;
- rotation/revocation is versioned;
- tenant scoping enforced;
- guest receives no BYOK secret by default.

### GPT-13 — Consent and metadata-only gateway
- consent defaults false;
- workspace policy plus explicit per-run consent;
- consent has actor, scope, provider/model alias, endpoint class, data-policy version, allowed categories, time and revocation state;
- API cannot accept arbitrary prompt text;
- provider gateway constructs request only from typed allowlisted metadata;
- source files/snippets/diffs/repository archives/raw logs/raw HTTP bodies/environment values/credential values/PII are unrepresentable or rejected;
- consent cannot expand payload schema;
- provider origin allowlist and TLS verification;
- strict request/call/time/token/cost budget;
- provider 401/429/5xx/timeouts do not trigger direct or alternate-provider fallback;
- outbound payload and result metadata audited without storing source/prompt contents.

Acceptance: MiniMax inspects actual serialized outbound body in controlled tests; synthetic canary source/secret values are rejected before egress. If direct inference paths remain, hosted metadata mode remains disabled. Keep current legacy direct inference paths explicitly inventoried and frozen until approved migration; do not claim privacy established merely because a new gateway endpoint exists.

## 11. API data model and state semantics

Contract objects consumed by CLI and dashboard:
- User, Workspace (individual/organization), Membership, Invitation;
- Project, SourceConnection, GitHubInstallation, RepositoryGrant;
- Runner, RunnerPool, RunnerCredentialMetadata, RunnerCapability, Lease;
- RunSpec, Run, RunAttempt, DispatchOutbox, LifecycleEvent;
- Core/Deep/Security GateResult;
- QA outcome, execution state and trust outcome;
- Finding, ReproductionRecord, EvidenceManifest, EvidenceObject, Receipt;
- ProviderSecretReference, ConsentRecord, AuditEvent, Usage/Quota.

Keep these dimensions independent:
- **Execution:** accepted/queued/admitted/assigned/provisioning/running/completed/failed/cancelled/timed out/infrastructure error.
- **QA outcome:** pass/fail/inconclusive/blocked/not requested.
- **Trust outcome:** verified/invalid/incomplete/not verified.
- **Gate status:** PASS/FAIL/BLOCKED/SKIPPED/NOT_REQUESTED/ERROR.

Do not compress all of them into a single `success` boolean. The exact state names must be reconciled with accepted ADRs and existing lifecycle before implementation.

## 12. Reliability, scale and observability

### GPT-14 — 15-user / 45-submission test
Scenario:
- 15 authenticated users concurrently;
- each submits 3 runs (45 submissions);
- at least 2 organizations and personal workspaces;
- multiple projects and at least one private GitHub repo;
- uneven burst patterns;
- repeated idempotency key and conflicting idempotency body;
- runner pool has fewer active slots than submitted runs;
- a runner goes offline and a lease expires;
- a dispatcher/control-plane process restarts;
- one cancellation during provisioning and another during execution.

Prove:
- no committed run intent lost;
- no duplicate active attempt;
- tenant isolation holds;
- queue remains durable and visible;
- fairness/backpressure works;
- stale runners are fenced;
- evidence/receipt never cross run/attempt/tenant;
- retries are classified;
- cancellation state is honest.

Measure actual:
- API p50/p95/p99 latency;
- auth and admission latency;
- queue/outbox age;
- claim/lease/heartbeat lag;
- runner slot utilization;
- DB connection/pool behavior;
- retry/idempotency counters;
- evidence/receipt request latency;
- resource consumption;
- recovery time.

Do not advertise SLO or throughput until the benchmark is repeated on a recorded reference environment. User count does not imply fixed VM concurrency.

### GPT-15 — Observability and operational guardrails
Build:
- readiness vs liveness endpoints;
- structured request/correlation IDs;
- auth failure, rate-limit and policy-denial metrics;
- outbox age and retry metrics;
- lease expiry and stale fencing counters;
- runner heartbeat/eligibility metrics;
- per-tenant quota consumption;
- evidence upload/verification latency;
- DB pool saturation and slow query indicators;
- redaction and audit policy.

No metric labels contain secrets, source paths, customer names/PII or arbitrary untrusted strings. Health endpoint must not disclose internal credentials or exception traces.

## 13. Database migrations, backup and operations

Each schema migration requires:
- current-schema audit;
- forward migration;
- rollback or forward-fix plan;
- lock/availability analysis;
- backfill strategy if existing records;
- tenant ownership invariant;
- RLS policy update;
- app compatibility window;
- pre/post migration tests;
- backup verification before production-like migrations.

Operational runbooks:
- control-plane restart;
- dispatcher/outbox recovery;
- runner registration/revoke;
- database restore;
- queue backlog drain;
- migration rollback;
- credential rotation;
- GitHub app revocation;
- audit export and retention;
- privacy incident and provider disable.

## 14. Work packages and acceptance matrix

| ID | Priority | Deliverable | Acceptance |
|---|---|---|---|
| GPT-01 | P0 | Current backend/API/auth/RLS audit | Exact path/route/schema/test map |
| GPT-02 | P0 | M1 OpenAPI + runner protocol contract | Lint, fixtures, Go/Python consumer compatibility, owner approval |
| GPT-03 | P0 | Principal/authorization matrix | Human/runner/GitHub identities separated; no IDOR |
| GPT-04 | P1 | Personal workspace | Idempotent setup and isolation |
| GPT-05 | P1 | Organization membership/roles | Invitation, role change, revocation and audit |
| GPT-06 | P0 | PostgreSQL ownership/RLS hardening | Non-owner app role, no BYPASSRLS, tenant negative tests |
| GPT-07 | P0 | Outbox/idempotency/lease/fencing | fault/retry/race/restart cases |
| GPT-08 | P0 | Runner APIs and dispatch bridge | signed assignment, lease and Firecracker adapter contract |
| GPT-09 | P1 | GitHub App server integration | repo-scoped tokens, verified webhooks, PR checks |
| GPT-10 | P1 | BYOK secret/consent/gateway | write-only secret, metadata-only actual outbound proof |
| GPT-11 | P1 | Evidence/receipt APIs | tenant-safe immutable refs and receipt verification metadata |
| GPT-12 | P1 | Load/observability/operations | 15×3 workload plus restart/recovery and actual metrics |
| GPT-13 | Post-M1 | Dashboard API completion | all Gemini-required API fields and states stable |

Tasks can run in parallel only where they have separate reserved paths and frozen interfaces. The M1 runner contract is P0 and must precede implementation across the runner boundary.

## 15. Test plan

| Area | Required tests |
|---|---|
| Auth | login, refresh, logout, expiry, replay, revoke, wrong principal |
| Tenancy | two orgs, multi-membership, cross-project IDOR, stale role and session |
| PostgreSQL | real RLS role, pooled context isolation, rollback, FK/unique scope |
| Runs | idempotency, conflict, admission transaction, queue, cancel and retry |
| Outbox | crash before/after commit, replay, delayed processing, duplicate event |
| Runner | enroll, claim, two-runner race, heartbeat, stale lease, revoke |
| GitHub | invalid webhook, replay, repo scope, expired token, private clone grant |
| BYOK | write-only secret, rotation, revoke, consent absent/expired, canary leakage |
| Privacy | forbidden source/log/secret fields, arbitrary prompt, direct bypass, timeout fallback |
| Evidence | cross-run access denial, digest mismatch, oversized manifest, receipt tamper |
| Scale | 15 users × 3 submissions, constrained runner pool, API/runner/DB restart |
| Operations | backup/restore, migration forward/rollback, audit export and key rotation |

## 16. Collaboration and handoffs

**DeepSeek:** provide OpenAPI/runner types, exact endpoint/error/fencing behavior, runner principal auth contract, test server and integration fixture. Receive runner client conformance tests and clear backend error semantics.

**GLM:** provide command/API consumption matrix, installation and GitHub client needs, user-facing error shape and package compatibility. Receive stable endpoint routes and documented permission scopes.

**MiniMax:** provide policy/consent threat model, negative test requirements, outbound payload assertion harness and security findings. Receive backend hooks/test fixtures but no access to real secrets.

**Gemini:** provide stable view models, pagination/filter needs, role matrix and exact error/state fields. Receive generated OpenAPI client and contract fixtures; no invented screen-specific backend states.

## 17. Required PR handoff

Every PR must include:
- linked task ID and API contract version;
- base/head SHA and migrations;
- route/model/table diff;
- tenant ownership and permission matrix change;
- schema/OpenAPI examples and generated-client diff;
- commands/tests with pass/fail/skip/not-run counts;
- PostgreSQL version/role and whether RLS actually enforced;
- idempotency/retry/lease evidence;
- privacy/secrets/logging impact;
- migration, rollback and backup implications;
- known limitations and owner decisions requested.

## 18. Stop conditions

Stop and mark BLOCKED if:
- canonical schema/lifecycle/receipt semantics need change without approval;
- endpoint uses client tenant ID as authority;
- PostgreSQL role bypasses RLS or tests only use SQLite;
- an accepted run can be lost between DB and dispatch;
- duplicate runner claim could execute same attempt twice;
- cancellation is presented as verified termination without host evidence;
- provider secret is retrievable or logged;
- arbitrary prompt/raw source can reach hosted provider;
- direct legacy inference path cannot be frozen or accounted for;
- GitHub token reaches guest;
- backend change requires paid Workflo-owned infrastructure contrary to zero-budget constraints;
- test failure must be suppressed to make CI green.

## 19. Definition of done

The existing FastAPI control plane exposes versioned, documented and tested contracts used by the Go CLI and runner; run admission/outbox/attempt state is durable and idempotent; runner claims are authenticated, lease-bound and fenced; individual and organization membership is server-authorized; PostgreSQL RLS is proven with a realistic application role; BYOK secrets are write-only and hosted requests are metadata-only with consent; and 15 users × 3 submissions demonstrate durable backpressure and recovery without tenant or evidence crossover. The dashboard can then consume these stable APIs without inventing a second backend.
