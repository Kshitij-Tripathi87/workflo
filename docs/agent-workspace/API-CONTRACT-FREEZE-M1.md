# M1 Control-Plane Contract Freeze — Minimal V2 Surface and Implementation Order

**Status:** semantic freeze for owner approval; OpenAPI generated from source after D2 contract review  
**Scope:** M1 native CLI and one customer-controlled Linux/KVM runner  
**Control plane:** existing FastAPI/Python implementation  
**Compatibility:** preserve existing V1 routes, authentication and canonical receipt contracts  
**Owners:** GPT-6 Luna (OpenAPI/backend), DeepSeek (CLI/runner client), GLM (CLI/source connector), MiniMax (security review), human owner (canonical contract/security approval)

> This is an implementation contract boundary, not a claim that the proposed V2 runner operations already exist. Wire-level names and field shapes must be confirmed against the current source tree, Pydantic schema and database models before they are frozen in OpenAPI.

## 1. Verified source baseline and implications

The existing control plane already has FastAPI routes for health, runs, keys, artifacts, audit, organizations, auth, inference and OAuth-related flows. The current runs API is V1 and its primary submission path authenticates through an API key. The OAuth device-flow bearer principal is not yet a drop-in replacement for the current V1 run submission dependency.

The existing outbox service atomically persists a run, first attempt and dispatch outbox record. Preserve this; do not create a second queue abstraction.

The current dispatcher `dispatch_service.execute_payload` invokes legacy `workflo_executor.SandboxExecutor`. This is **not** the customer Firecracker path. The Firecracker/jailer lifecycle and guest protocol foundation exists separately under `worker/src/workflo_worker_host/`, but is not connected to a registered runner API/dispatch path.

The current user model holds a direct organization/project association. There is no complete membership/role model and no invitation flow. Existing project-scoped RLS foundations exist, but production acceptance must use a realistic non-owner/non-superuser application role without BYPASSRLS.

The canonical schema includes RunSpec V1, SourceSpec V1 and Receipt V5/DSSE semantics. SourceSpec currently permits abbreviated commit-like values broader than the M1 full-object-identity requirement. Do not silently tighten V1 and break existing consumers. M1 CLI and additive API validation must require a full repository object ID. Any schema evolution is versioned and reviewed.

## 2. M1 scope decision

Luna owns only the backend work necessary for this single-run vertical slice:

1. existing device-flow human principal accepted by the additive M1 run API;
2. server-resolved current user/project authorization;
3. idempotent run admission using existing TestRun/RunAttempt/DispatchOutbox;
4. separate customer-runner principal and one-time enrollment;
5. runner heartbeat, claim/lease, fencing, state/completion and revoke;
6. strict run dispatch to the existing Python Firecracker host adapter;
7. run status and bounded evidence/receipt metadata for the CLI;
8. PostgreSQL-backed integration/RLS/auth/recovery tests;
9. OpenAPI, generated client fixtures and operator handoff.

**M1 exclusions:** org membership/invitations/roles, broad multi-tenant redesign, GitHub App webhook/check publishing, hosted inference or BYOK, provider consent APIs, dashboard aggregates, analytics/usage, fair multi-runner scheduler, 15-user/45-submission test and production operations beyond what one enrolled runner requires.

The current project-scoped model is the M1 scope boundary. Client-supplied `org_id` or `project_id` is never trusted as authority. If existing auth cannot resolve an authorized project, stop and propose a compatible migration; do not invent a personal workspace object or mock authorization.

## 3. Principal model

| Principal | Authentication | M1 authority |
|---|---|---|
| Human CLI user | Existing device authorization access/refresh lifecycle, adapted additively | Submit, inspect and cancel own authorized project runs |
| Customer runner | Distinct enrolled identity with one-time enrollment proof and renewable short-lived credential/certificate | Heartbeat, claim eligible attempt, report host-observed lifecycle and bounded evidence |
| GitHub source broker | Short-lived installation/repository-scoped read token held on runner side | Read only selected repository/ref; never expose token to guest |
| Guest | Attempt-scoped protocol nonce/capability | Execute fixed profile and return bounded structured result; no authority to provision, authorize or verify teardown |

Human access token, runner credentials and GitHub installation credentials are non-interchangeable. Secrets are never returned in API payloads or logs.

## 4. Required V2 operation families

Exact route spelling and JSON property names are frozen by Luna in generated OpenAPI after source audit. Minimum operations:

| Operation | Caller | Required behavior | Key controls |
|---|---|---|---|
| Run create | Human CLI | Persist one authorized run + attempt + outbox transaction | Required idempotency key; full source identity; server project resolution |
| Run get/list | Human CLI | Return authorized run state and three outcome axes | Project-scoped authorization; no IDOR |
| Run cancel | Human CLI | Record cancellation request and signal runner | Request is not proof of termination |
| Runner enroll | One-time enrollment client | Bind unique runner identity to authorized project/pool | Single-use, expiry, replay prevention, audit |
| Runner heartbeat | Enrolled runner | Update bounded health, version and KVM capability | Runner principal only; freshness checks |
| Runner claim/lease | Enrolled runner | Reserve one eligible attempt | Fencing token, expiry, capacity reservation, duplicate claim prevention |
| Runner state/complete | Enrolled runner | Monotonic attempt-bound event/result update | Reject stale/wrong attempt, bounded payload |
| Evidence/receipt metadata | Runner/CLI under authorized scopes | Register immutable manifest and retrieve authorized evidence | Size limits, hash validation, immutable signed receipt bytes |

Expected additive route family (illustrative; generated OpenAPI is authoritative once approved):
- `/v2/runs`
- `/v2/runs/{run_id}`
- `/v2/runs/{run_id}/cancel`
- `/v2/runners/enroll`
- `/v2/runners/heartbeat`
- runner claim/lease operation
- runner attempt state/completion operation
- evidence/receipt metadata operation

Do not retrofit runner semantics into legacy V1 `/complete`, `/logs` or `SandboxExecutor` code.

## 5. Run admission contract

Run request semantics require:
- canonical GitHub repository identity;
- full immutable object ID (40 hex for SHA-1; SHA-256 only if explicitly supported by the repository/API contract);
- pinned profile ID/version (M1: Python + pytest);
- policy version/digest;
- eligible runner ID or server-resolved authorized selection;
- required `Idempotency-Key`;
- bounded request and metadata size;
- authenticated user/project context resolved server-side.

Admission semantics:
1. validate human principal and project authorization;
2. validate full source identity and profile/policy availability;
3. resolve runner eligibility or reject/queue with explicit state;
4. transactionally persist run + first attempt + dispatch outbox;
5. make repeated same-key/same-payload requests return the original intent;
6. reject same key with materially different payload;
7. never provision a VM in the synchronous HTTP request.

A rejected admission must not leave an executable partial outbox record. Existing V1 request/response behavior stays unchanged.

## 6. Runner assignment and fencing

The assignment must be integrity-protected and include equivalents of:
- protocol version;
- run, attempt and sandbox IDs;
- unique lease ID/expiry and fencing version;
- source repository/full commit and source digest after acquisition;
- pinned profile and policy version/digest;
- Firecracker/jailer/kernel/rootfs artifact identities;
- CPU/RAM/disk/PID/time/output ceilings;
- network/egress policy;
- explicit capability allowlist;
- nonce/sequence/replay metadata;
- assignment issuer/key identity.

A runner executes only a currently leased, authorized assignment. A stale, replayed, cross-attempt or over-capability message fails closed. A retry creates a new attempt and a new VM. Heartbeat does not extend a lease beyond the server-approved policy.

## 7. Dispatch integration decision

M1 strict runs must flow from the existing durable outbox into the runner adapter that invokes the existing Firecracker host package. They must **not** flow through `workflo_executor.SandboxExecutor`.

Luna owns admission/dispatch and the runner API. DeepSeek owns the host-client and the narrow adapter integration. The current Python Firecracker host remains the M1 reference under ADR-0024. Do not write a second Firecracker lifecycle implementation in Go during this milestone.

Before merge, tests must prove:
- V2 run persisted once;
- one eligible runner claims it;
- host adapter receives the exact assignment;
- no legacy SandboxExecutor call occurs;
- lease expiry fences the old attempt;
- runner restart/retry cannot create two active VMs.

## 8. Source, guest and receipt compatibility

- M1 requires a full Git object ID, not abbreviated SHA.
- The runner-side source broker acquires exactly that object and calculates canonical inventory/digest.
- GitHub access is short-lived and scoped to the selected repository; token never enters guest, RunSpec, logs, receipt or evidence.
- Guest receives an immutable snapshot, not a mutable host checkout mount.
- Guest/host messages remain typed, versioned, run/attempt/sandbox-bound, nonce/sequence checked and size-limited.
- No generic host shell/exec tool is added.
- Reuse canonical Receipt V5/DSSE and the existing eight MicroVM teardown checks. Do not alter signed bytes after signing.
- A missing, unknown or failed teardown check cannot result in VERIFIED_CLEAN.
- CLI offline verification checks trust anchor, signature, canonical encoding, evidence hashes and binding to run/attempt/source/policy/runtime.

## 9. Production database requirements

M1 local unit tests may use SQLite if clearly marked as local tests. Integration acceptance must exercise PostgreSQL and the actual M1 project-scoped access path. Production startup must retain existing fail-closed guards. The RLS test role must not be database owner, superuser or BYPASSRLS; test transaction context cleanup and pooled connection reuse. Do not broaden to organization memberships during M1 merely to make a future schema look complete.

## 10. Luna's ordered implementation plan

| Step | Deliverable | Depends on | Acceptance |
|---|---|---|---|
| L-M1-01 | Source audit: auth, project scope, outbox, dispatcher, attempt/lease, host package, artifact endpoints | None | Exact file map, current test status and reuse plan |
| L-M1-02 | OpenAPI + error/idempotency/protocol proposal | L-M1-01 | Owner-approved contract; generated fixture compiles |
| L-M1-03 | Additive human API auth adapter + project authorization | L-M1-02 | Existing device flow works; unauthorized project denied |
| L-M1-04 | Idempotent run create/read/cancel over existing outbox | L-M1-03 | PostgreSQL test proves atomic run/attempt/outbox and duplicate behavior |
| L-M1-05 | Runner enroll/heartbeat/revoke | L-M1-02 | One-time enrollment, expiry, replay and revoke tests |
| L-M1-06 | Runner claim/lease/fencing/state/complete | L-M1-05 | Competing runners, stale attempt and expiry tests |
| L-M1-07 | V2 outbox dispatcher → existing host adapter | L-M1-04 + L-M1-06 | Integration test proves strict V2 path never reaches SandboxExecutor |
| L-M1-08 | Evidence/receipt metadata endpoints | L-M1-07 | Hash/size validation, immutable receipt, auth-scoped retrieval |
| L-M1-09 | PostgreSQL/auth/RLS/restart integration suite | L-M1-03..08 | Non-owner RLS test, DB restart, retry and no duplicate attempt |
| L-M1-10 | OpenAPI/client generation and handoff | L-M1-02..09 | Spec lint, generated client compile, exact examples, known limitations |

## 11. Explicitly deferred Luna work

Post-M1 only:
- org membership/invitations and Owner/Admin/Developer/Viewer roles;
- organization-level RLS model redesign;
- provider profiles, key CRUD, consent and inference routes;
- GitHub installation lifecycle, webhook verification and check publishing if not already required by M1 source acquisition;
- dashboard overview/project/team/usage/analytics APIs;
- fair multi-runner scheduler and 15-user/45-submission load test;
- broad operations, billing, quota and audit dashboards.

Keep this work in a post-M1 epic. It must not be a hidden prerequisite for the M1 critical path.

## 12. Required Luna handoff

- OpenAPI source and generated client artifacts;
- auth principal and project-scope diagram;
- DB/run/attempt/outbox/runner data diagram;
- state and lease transition diagrams;
- route-to-test matrix;
- PostgreSQL/RLS test evidence;
- dispatch-path proof and no-SandboxExecutor test;
- migration/rollback notes;
- operational logs/metrics and limitations;
- exact commit SHA and CI evidence.
