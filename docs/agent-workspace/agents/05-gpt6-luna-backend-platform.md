# Agent 05 — GPT-6 Luna
## Control Plane, API Contracts, Tenancy, Persistence and Web Backend

**Workstream:** web/platform backend and architecture  
**Branch:** agent/gpt6-luna-backend-platform  
**Primary owner:** GPT-6 Luna  
**Reviewers:** DeepSeek (runner protocol/client), GLM (CLI/connector API use), Gemini (dashboard contracts), MiniMax (privacy/security review), human owner (canonical contracts/release approval).

## 1. Why this model owns this work

OpenAI's GPT-6 Sol/Luna release reports:
- GPT-6 Luna on DeepSWE v1.1: **66.6% at max effort**.
- OpenAI describes this as comparable to its compared Opus/Fable medium-effort results in that evaluation.
- OpenAI reports materially lower cost per task than those compared models.
- OpenAI also reports improved cost-efficient computer-use behavior, but does not provide a directly comparable backend/API leaderboard score for Luna in that release.

Primary source: https://openai.com/index/introducing-gpt-6-sol-and-luna/

**Routing hypothesis:** long-horizon backend changes, API contract construction, database/schema implementation, integration and contract/test work. There is no basis to claim Luna is the best dedicated backend architecture model; the assignment is validated using Workflo-specific calibration and mandatory human review.

## 2. Mission

Own the control-plane and backend contracts that support both CLI-first execution and the later web app. Make Workflo ready for individual accounts and org/team workspaces, 10–15 concurrent users with multiple run submissions each, customer-owned runners, durable run dispatch and tenant-safe evidence.

The API contract is designed now. CLI-critical backend work can be implemented as needed. Dashboard-specific backend screens/endpoints are completed as the CLI/run contracts stabilize; Gemini's substantial UI implementation begins after the CLI gate.

## 3. Owned paths

Primary:
- apps/control-plane/
- apps/control-plane/tests/
- db/rls/ and database migrations owned by the control plane.
- docs/api/ and API/OpenAPI contract documentation.
- API integration tests and backend load-test harness.
- API-generated TypeScript types/client artifacts only with Gemini coordination.

Must not own:
- apps/workflo-cli-go/ core and apps/workflo-runner-go/ (DeepSeek).
- packages/workflo-policy-go/ and security/ fixture ownership (MiniMax).
- packages/npm-workflo/, connector client and CLI command handlers (GLM).
- apps/dashboard/ (Gemini).
- canonical packages/workflo-schema receipt/lifecycle/policy semantics without owner approval.
- marketing website and Cloudflare Pages D1.
- production deployment, production DB credentials or provider secret values.

## 4. Existing backend baseline to preserve and harden

The current repository already contains:
- FastAPI control plane.
- SQLAlchemy models including Organization, Project, API key, Device and TestRun.
- durable DispatchOutbox and RunAttempt path.
- transactional creation of run, first attempt and outbox record.
- lease/heartbeat and expiry recovery functions.
- per-project/run rate limiting.
- hosted inference route starting point.
- PostgreSQL RLS foundations, with real production-role acceptance still to be made non-skipping.

The existing code also has local/development defaults such as SQLite, disabled RLS and static/demo auth options. These must remain development-only and must fail closed in production. Do not rewrite the control plane from scratch.

## 5. Work packages

### LUNA-01 — Backend architecture audit

- Read current control-plane app, routes, services, SQLAlchemy models, migrations, config, startup guards, RLS scripts and workflow tests.
- Map current code to product responsibilities.
- Identify auth/session/OIDC/device flow status.
- Identify tenant ownership and membership gaps.
- Identify API compatibility constraints.
- Identify all development-only defaults.
- Identify Pydantic/OpenAPI schema source and existing TypeScript mirrors.

**Acceptance:** backend gap report with exact modules, APIs, table ownership, migration constraints and test status.

### LUNA-02 — API contract design (immediate)

Publish versioned OpenAPI for:
- auth/device flow;
- individual user and workspace selection;
- organization/membership/roles;
- projects;
- GitHub installations/repositories;
- runner enrollment and heartbeat;
- runner claim/lease;
- run admission/status/cancel/list;
- attempts and lifecycle events;
- evidence/receipt metadata/download grant;
- provider profile and consent metadata;
- audit/usage/quota.

For every endpoint specify:
- method/path;
- auth scheme and scopes;
- tenant context;
- request/response schema;
- idempotency behavior;
- pagination;
- rate/size/time limits;
- error envelope;
- audit event;
- owner and implementation status.

Do not create a new parallel lifecycle contract. Use current canonical schemas and obtain owner approval for any new version.

**Acceptance:** OpenAPI lint, generated client compile, contract examples and positive/negative API tests.

### LUNA-03 — Individual + organization tenancy

Implement:
- personal workspace for individual users;
- organizations;
- membership and invitation;
- roles Owner/Admin/Developer/Viewer;
- project-level permissions;
- runner pool assignment;
- ownership transfer and safe offboarding;
- audit events for privilege and integration changes.

All scopes are server derived. Client org_id/project_id values are selectors only, never authorization.

**Acceptance:** role permission matrix, organization boundaries and cross-tenant negative tests.

### LUNA-04 — Authentication and runner identity

- Use accepted managed OIDC/device authorization design.
- Short-lived access token and secure refresh/revocation.
- Avoid static demo token in production.
- Distinguish human users, GitHub App installation, runner service identity and API keys.
- Runner enrollment token is one-time and expires.
- Runner identity uses certificate/workload credentials; renewal and revoke supported.
- Provider secrets are write-only and encrypted at rest under a customer-controlled or explicitly configured KMS/key-wrapping model.
- No secret values returned through API or logged.

**Acceptance:** login expiry, refresh replay, logout, device revocation, role change, runner certificate expiry/revocation and unauthorized runner tests.

### LUNA-05 — PostgreSQL and data model hardening

- PostgreSQL is mandatory for production.
- Add/repair org_id to tenant-owned tables where absent.
- Define foreign keys and uniqueness constraints with tenant scoping.
- Add RLS policies and FORCE ROW LEVEL SECURITY where appropriate.
- Application role is not table owner, is not superuser and does not have BYPASSRLS.
- Set organization context transaction-locally and clear safely.
- Index run timeline, project, runner, status and outbox access patterns.
- Bound log/evidence metadata and retention.
- SQLite only for local tests where explicitly labelled; no production fallback.

**Acceptance:** migration test, real PostgreSQL role/RLS test, cross-tenant direct-ID test, connection pool context isolation test, backup/restore exercise.

### LUNA-06 — Durable run API and scheduling contract

- Use current transactional outbox as the durable source of dispatch.
- Persist run + attempt + outbox atomically.
- Add idempotency key required in production.
- Expose clear accepted/queued/rejected vs executing status.
- Implement runner claim/lease/heartbeat/recovery endpoints for DeepSeek.
- Attempt fencing prevents duplicate active work.
- Cancellation is a request and remains incomplete until runner reports verified termination.
- Capacity-aware queueing uses runner-advertised resources and profile eligibility.
- Fair scheduling across org/project/user.
- Per-tenant quotas and rate limits.
- No synchronous request performs full test execution.

**Acceptance:** API restart, DB restart, duplicate submission, two runners racing, lease expiry, cancellation race and 15-user/45-submission burst tests.

### LUNA-07 — GitHub App server connector

- Implement installation callback and secure state validation.
- Store App private key in server-side secret manager, not repo or frontend.
- Verify webhook signatures and timestamp.
- Deduplicate webhook delivery IDs.
- Request minimal permissions: metadata read, contents read, checks write if needed, PR read only if needed.
- Issue short-lived installation tokens scoped to selected repository.
- Provide source-acquisition capability to customer runner without passing token into guest.
- Publish commit/PR check result tied to run ID and exact commit SHA.
- No contents-write, merge, admin or deployment permission in launch.

**Acceptance:** installation/revocation, permission matrix, token expiry, webhook replay, invalid signature, selected repo scope and PR check tests.

### LUNA-08 — Inference/privacy backend integration

MiniMax owns policy specification and outbound/privacy tests. GPT-6 owns the actual control-plane API/business implementation.

- Provider secret CRUD is write-only.
- Provider/model metadata is visible; secret never returned.
- Consent record records org/project, user, run, provider, model ID, data policy version, data categories and timestamp.
- Per-run consent required for hosted metadata mode.
- No hosted request if policy/consent is absent or revoked.
- Gateway constructs prompt from allowlisted metadata only.
- Caller cannot submit arbitrary raw prompt.
- Rate, token, call, time and cost budget enforced.
- Provider endpoint/origin allowlist.
- Provider 401/429/5xx/timeout does not trigger direct fallback.
- No hosted provider request can be initiated from a guest with raw source.
- Provider terms and retention policy displayed before consent.

**Acceptance:** actual outbound payload inspection by MiniMax's test suite; secret redaction; consent revocation; strict profile bypass tests.

### LUNA-09 — Future dashboard APIs

After CLI/run contract stabilizes, finish:
- overview aggregation;
- project/repository views;
- run listing/detail/timeline;
- attempt/finding/evidence endpoints;
- runner/pool list/detail/capacity;
- member/role APIs;
- provider/privacy settings;
- audit and usage queries.

All endpoints return the same lifecycle, trust and evidence semantics consumed by CLI.

### LUNA-10 — Multi-user capacity and backend observability

Build:
- per-org active-run and submission quotas;
- per-project rate limit;
- fair scheduler;
- runner capacity snapshots;
- queue-age and outbox-age metrics;
- lease and heartbeat metrics;
- DB pool metrics;
- idempotency replay counters;
- audit logging and redaction.

Load scenario: 15 concurrent users, 3 submissions each (45 burst), across multiple orgs. Use constrained runner pools to prove queue/backpressure. Measure and report all environment details; do not claim a fixed VM concurrency.

### LUNA-11 — Operations and handoff

Deliver:
- OpenAPI spec and generated client;
- data model/migration diagram;
- auth and RBAC matrix;
- RLS/tenant test evidence;
- queue/lease state diagrams;
- operational health/readiness endpoints;
- database backup/restore and migration runbook;
- audit retention and redaction specification;
- capacity/load test results;
- backend known-limitations list.

## 6. Security invariants

1. Every object read/write is tenant-authorized at the API boundary.
2. PostgreSQL RLS is defense-in-depth and tested using a realistic application role.
3. Production config fails startup with SQLite, static demo credentials, disabled required RLS or an in-process-only queue.
4. Run admission and outbox intent are atomic.
5. Retried mutations are idempotent.
6. Runner attempts are fenced and lease-bound.
7. Cancel is not verified termination.
8. Provider credentials are never returned to clients.
9. Consent is scoped and recorded.
10. Hosted model requests contain only allowlisted metadata.
11. The control plane does not receive or store raw repo contents for the normal customer-controlled path.
12. No API response claims verified teardown based solely on guest or runner self-report.

## 7. Definition of done

The native CLI and runner can use stable, versioned APIs for individual/org auth, GitHub installation selection, project/run admission, runner claims, status/cancel and evidence metadata. PostgreSQL RLS passes with a non-owner role. A 15-user/45-submission burst loses no committed work and maintains tenant isolation. APIs are documented and consumed by the later dashboard without a second backend implementation.
