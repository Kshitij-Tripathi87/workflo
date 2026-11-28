# Agent 05 — GPT-6 Luna
## M1 Control Plane, FastAPI Contracts, Durable Admission and Runner Dispatch

**Branch:** `agent/gpt6-luna-backend-platform`  
**Primary owner:** GPT-6 Luna  
**Reviewers:** DeepSeek (runner/CLI contract), GLM (consumer behavior), MiniMax (security/RLS/privacy), human owner (canonical API/security decisions)  
**M1 priority:** P0 — backend is a direct critical-path dependency

## 1. Mission and corrected scope

**Mission:** make the existing FastAPI control plane capable of admitting an authenticated user's exact GitHub commit, assigning it safely to one enrolled customer runner and exposing real run/evidence status to the native Go CLI.

This runbook supersedes any earlier wording that made enterprise memberships, roles, inference, dashboard APIs or the 15-user/45-submission burst an M1 prerequisite.

Luna is responsible for:
- M1 source audit and OpenAPI contract;
- additive human CLI auth adaptation;
- current user/project authorization;
- idempotent run + attempt + outbox;
- runner identity/enrollment/heartbeat/claim/lease/fencing/state/completion;
- strict dispatch bridge to the **existing** Firecracker host;
- evidence/receipt metadata and status APIs;
- PostgreSQL/RLS/restart/idempotency integration tests;
- generated contract/client artifacts and backend handoff.

Luna is not responsible for rewriting the backend, owning Go CLI/host internals, changing canonical receipts, or delivering every later platform capability.

## 2. Expected capability fit and constraints

Routing hypothesis: long-horizon software-engineering, API/OpenAPI design, multi-file backend integration, SQLAlchemy/data migrations, tenant-safe query logic and test diagnosis. Published benchmark data is not a guarantee of backend architecture correctness.

Use Luna for bounded contract implementation and integration. Require human review for auth, tenancy, RLS, secret handling, signer/receipt and production configuration. Do not assume the model can make an independent security decision or that its output authorizes a database migration.

## 3. Owned paths and shared boundaries

**Primary ownership**
- `apps/control-plane/` route/service/model/config/test changes required by M1;
- additive M1 database migrations only where the existing data model needs them;
- M1 OpenAPI source/snapshot, generated-client metadata and contract fixtures;
- PostgreSQL integration tests and run/runner API handoff docs.

**Must not own**
- `apps/workflo-cli-go/` core/commands/connectors/verifier (DeepSeek/GLM);
- `worker/` Firecracker host lifecycle implementation (DeepSeek);
- guest engine or receipt signing/verification implementation (DeepSeek + human approval);
- security threat-model and independent test oracle (MiniMax);
- `apps/dashboard/` (Gemini);
- canonical `packages/workflo-schema/` receipt/lifecycle/assignment semantics without explicit owner reservation;
- production secrets, live deployments, production database administration or customer data.

## 4. Existing backend code to preserve

Audit and preserve:
- FastAPI app and route registration;
- existing OAuth device authorization, token refresh and revoke flows;
- current user/project scope;
- SQLAlchemy organization/project/user/run models;
- transactional TestRun + RunAttempt + DispatchOutbox creation;
- current attempt/lease/heartbeat/expiry recovery primitives where correct;
- current production startup guards;
- existing project-scoped RLS foundations;
- V1 run API behavior and current receipt schemas.

Do not infer missing code exists. The current run route is API-key based, there is no registered runner API router, and the current dispatch path invokes legacy `SandboxExecutor`; none of these is already the requested M1 Firecracker workflow. Verify each observation against the exact base before changing code.

## 5. M1 non-negotiable architecture

1. FastAPI remains Python.
2. M1 uses additive versioned API operations; V1 remains compatible.
3. Human CLI auth, runner auth and GitHub source auth are distinct principals.
4. User/project/tenant scope is resolved server-side from persisted identity, never trusted from submitted org/project IDs.
5. Run + attempt + outbox are committed atomically.
6. Idempotency key is required for production admission; same key/same payload returns original intent; same key/different payload conflicts.
7. No synchronous request runs tests.
8. Runner assignment is leased and fenced; stale/duplicate attempt cannot execute.
9. Strict M1 dispatch uses the existing Firecracker host adapter, not `SandboxExecutor`.
10. Guest cannot assert host teardown or sign the receipt.
11. Existing Receipt V5/DSSE and eight MicroVM teardown checks remain canonical.
12. No provider/AI call is needed for M1 core.

## 6. Work packages

### L-M1-01 — Source and backend audit · D1

Map exact files/symbols for:
- main app/router registration;
- OAuth/device auth and user dependency;
- project authorization;
- runs route and schema;
- TestRun/RunAttempt/DispatchOutbox models/services;
- dispatcher and legacy SandboxExecutor;
- worker host API/assignment/lease;
- artifact/receipt handling;
- migration/RLS/startup guards.

Deliver a sequence diagram and gap table with current behavior, required delta, owner, test and blocker.

**Acceptance:** exact source references, no unverified assumptions, all V1 contracts identified.

### L-M1-02 — OpenAPI and interface freeze · D2

With DeepSeek/GLM/MiniMax:
- publish operation list and exact route names;
- define principal/scope for every operation;
- define request/response, enum, error envelope and size limits;
- define idempotency semantics and uniqueness scope;
- define runner lease/fencing lifecycle;
- define evidence/receipt metadata and immutable byte handling;
- derive/generated Go client fixture path;
- map operation to current schema/model.

**Acceptance:** human-approved semantic contract; OpenAPI lint; generated client and fixtures compile; no consumer has invented field names. Canonical schema/receipt changes are separately approved.

### L-M1-03 — Human principal and project authorization · D3–D5

- Adapt existing device-flow bearer principal to the additive M1 API.
- Use existing user/project association and server-side authorization.
- Do not return refresh/access tokens in responses after issuance or logs.
- Keep V1 API-key authentication intact.
- Fail closed for absent, revoked, expired or unrelated project identity.
- Do not fabricate a personal workspace/member model.

**Acceptance:** CLI device auth completes against real control plane; valid user can operate only authorized project; unauthorized direct IDs fail; token redaction tests pass.

### L-M1-04 — Idempotent run admission/status/cancel · D5–D7

- Additive run creation and status operations.
- Require `Idempotency-Key` in production M1.
- Persist run + attempt + dispatch outbox atomically in PostgreSQL.
- Same key/same request returns stable original run; same key/different request returns conflict.
- Validate full GitHub object ID and the one approved profile/policy.
- Cancellation is a request and does not assert termination.

**Acceptance:** transaction failure leaves no partial dispatch; replay produces one intent; V1 suite green; auth/project tests pass.

### L-M1-05 — Runner enrollment and heartbeat · D7–D8

- One-time enrollment proof, expiration and replay protection.
- Persist distinct runner identity and project/pool scope.
- Short-lived renewable runner credential/certificate; revoke path.
- Heartbeat carries bounded host version, OS/arch, KVM eligibility, Firecracker/guest profile capabilities and capacity.
- No human token or GitHub token is reused.

**Acceptance:** enrollment replay, expiry, stale heartbeat and revocation tests; secret values never returned/logged.

### L-M1-06 — Runner claim, lease, fencing and completion · D8–D10

- Claim only work authorized for the runner.
- Reserve one eligible attempt and issue integrity-protected assignment.
- Lease has server authority and bounded expiry.
- Use fencing version/token so a late old runner cannot complete or publish.
- Completion accepts bounded host state and evidence references; guest values are untrusted.
- Retry creates a new attempt ID and fresh VM.

**Acceptance:** two-runner race, lease expiry, late completion, duplicate claim, restart recovery and cross-project negative tests pass.

### L-M1-07 — Strict dispatch adapter · D9–D12

- Bridge outbox to the existing `worker/src/workflo_worker_host/` Firecracker host implementation.
- Reuse existing lifecycle and teardown code; no second VM manager.
- Explicitly separate M1 strict path from legacy `SandboxExecutor`.
- Ensure outbox retries cannot double-start a VMM.
- Handle runner offline/restart, lease expiry and failure transitions.
- Add observability for queue/attempt/lease transitions.

**Acceptance:** integration test proves M1 strict run invokes the existing Firecracker host adapter and never the legacy executor; real KVM run uses one fresh VM per attempt.

### L-M1-08 — Evidence and receipt metadata · D14–D17

- Register bounded evidence manifest metadata with size/hash validation.
- Preserve signed canonical receipt bytes unchanged.
- Provide authorized receipt/evidence retrieval to CLI.
- Do not interpret untrusted guest result as verified teardown.
- Keep execution, QA and trust separate.

**Acceptance:** tampered/oversized/wrong-attempt artifacts rejected; retrieval is project-scoped; receipt bytes round-trip exactly.

### L-M1-09 — PostgreSQL/RLS/auth/recovery tests · D18–D22

- Use PostgreSQL integration environment.
- Verify the actual M1 project-level RLS path with an application role that is not owner, superuser or BYPASSRLS.
- Verify transaction-local scope and pooled-connection cleanup.
- Exercise API restart, DB restart, duplicate submission, competing claim, late completion, lease expiry and cancellation.
- Keep dev SQLite clearly separated from production acceptance.

**Acceptance:** reproducible CI or documented integration report with exact DB role/settings; no cross-project IDOR; no lost committed outbox intent or duplicate active attempt.

### L-M1-10 — Handoff and post-M1 backlog · D23–D25

Deliver:
- source OpenAPI and generated client;
- route/principal/scope matrix;
- DB model and migration diagram;
- run/outbox/attempt/lease state diagrams;
- test matrix/commands/results;
- dispatcher-to-host proof;
- operational readiness/metrics, recovery and rollback;
- known limitations and post-M1 backlog.

**Acceptance:** DeepSeek/GLM can consume the contract without private explanation; human owner can reproduce M1 test path from the handoff.

## 7. Explicitly deferred Luna work

Do not implement or make M1 depend on:
- organization creation/memberships/invitations and Owner/Admin/Developer/Viewer roles;
- broad org-wide tenancy/RLS redesign beyond the current project scope needed for M1;
- provider profile/secret CRUD, BYOK, consent and inference business logic;
- GitHub webhook delivery and PR/check publishing (minimum read access/source broker only if required);
- dashboard overview, project, member, analytics or usage APIs;
- 15-user/45-submission performance target, fair multi-runner scheduler or hosted fleet;
- billing, marketplace or broad admin console.

Create a separate post-M1 plan with owners and acceptance tests after M1 scope is frozen.

## 8. How to work and review

1. Audit first; preserve existing useful transactional and auth foundations.
2. Freeze OpenAPI and protocol semantics with all consumers before implementation.
3. Implement one route/resource family per PR.
4. Keep migrations additive, reversible where possible and independently tested.
5. Do not run a migration against production.
6. Require independent review for identity, RLS, secrets and runner authorization.
7. Test against PostgreSQL before claiming production posture.
8. Keep generated API clients generated; do not hand-edit generated code.
9. Rebase daily and expose blockers immediately.
10. Attach exact request/response fixtures and pass/fail/skip counts.

## 9. Do not

- rewrite FastAPI in Go;
- force org memberships into the M1 path;
- retrofit runner semantics into legacy V1 completion/log routes;
- route strict execution through SandboxExecutor;
- trust client org/project identifiers;
- mix human, runner and GitHub credentials;
- put raw source in control-plane logs or provider requests;
- accept guest-reported teardown as truth;
- mutate signed receipt bytes;
- make hosted inference or dashboard APIs a CLI dependency;
- bypass RLS or weaken startup guards to get CI green;
- deploy or change production secrets.

## 10. Luna daily handoff fields

API/OpenAPI commit, base SHA, routes/models touched, migration ID, request fixtures, exact test commands, PostgreSQL role/RLS settings, concurrency/recovery results, security impact, generated client hash, known limitations and next dependency.
