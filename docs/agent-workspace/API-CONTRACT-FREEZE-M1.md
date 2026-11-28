# M1 Control-Plane Contract Freeze — Audit, Gaps and Proposed Wire Boundary

**Baseline:** `main` at `7a20dfe8ea01dcff2ba94932626f3dcfbc857d1d`  
**Status:** M1 interface proposal; existing V1 contracts remain unchanged  
**Purpose:** Freeze the minimum CLI ↔ control-plane ↔ customer-runner boundary required for Milestone 1.  
**Owners:** GPT-6 Luna workstream (backend contract proposal), DeepSeek (runner client), GLM (CLI consumer), MiniMax (security review), human owner (approval of canonical/security changes).

> This document is based on the current source tree. It does not claim that the new runner APIs or Firecracker integration already exist. Existing V1 endpoints and schema are preserved while the M1 boundary is implemented as a separately versioned contract.

## 1. Current-state audit — verified against source

### 1.1 Existing control-plane API

The current `apps/control-plane/app/main.py` registers health, runs, keys, artifacts, audit, orgs, auth, key provisioning, inference, voice and OAuth routes. There is no registered runner or worker API router.

The current `apps/control-plane/app/api/v1/runs.py` exposes:
- `POST /v1/runs` and `GET /v1/runs/{run_id}` as the primary documented V1 interface;
- legacy list, proof, complete, logs and cancel endpoints retained for compatibility.

`POST /v1/runs` accepts `workflo_schema.api.RunRequest`, validates/translates it to the legacy sandbox spec, and authenticates through `require_api_key`. It does not accept the OAuth device-flow bearer principal directly. Production configuration can require `Idempotency-Key`; development can generate a key when omitted.

The current outbox service atomically creates a `TestRun`, a `RunAttempt` and a `DispatchOutbox` row. This is useful durable admission infrastructure and should be preserved.

### 1.2 Current execution path is not Firecracker dispatch

`apps/control-plane/app/services/dispatch_service.py::execute_payload` currently imports and invokes `workflo_executor.SandboxExecutor`. The dispatcher/outbox loop therefore does not yet dispatch a signed assignment to an enrolled customer Firecracker runner.

The separate `worker/src/workflo_worker_host/` package contains Firecracker/jailer lifecycle, assignment, admission, network, guest protocol, vsock and teardown code. It is not currently reachable through a registered control-plane runner API.

**Implication:** durable run admission exists, and a Firecracker host foundation exists, but the end-to-end bridge between them is missing. A passing control-plane unit test or Firecracker worker unit test cannot establish the complete M1 workflow.

### 1.3 Current identity and organization model

The control plane has OAuth device code, access-token, refresh and revoke paths. It also retains a development-only demo-token path.

The current `User` model has one `org_id` and one `project_id`. The ORM tree contains no organization membership/role model. The current `orgs.py` router exposes export and delete, not organization creation, invitation, membership listing or role changes.

**Implication:** individual identity/device login has foundations, but the requested multi-user organization/team role model is not complete. Do not design the CLI or dashboard around a membership API that is not implemented.

### 1.4 Current tenant isolation and production posture

`apps/control-plane/db/rls/001_tenant_rls.sql` enables and forces project-scoped RLS on projects, API keys, test runs, run attempts, test results, artifacts and audit events. Application database context is currently project-oriented.

`startup_guards.py` already rejects production startup when required JWT strength, RLS enablement, credential encryption, dispatcher enablement or idempotency requirements are absent. The config defaults are intentionally permissive for development (SQLite, RLS disabled, dispatcher disabled, etc.). Production must use the guarded path and a PostgreSQL application role without bypass privileges.

### 1.5 Current source and receipt contracts

- `packages/workflo-schema/.../contracts/runspec.py` defines immutable RunSpec V1 and SourceSpec V1. SourceSpec's commit pattern currently accepts 7–64 lowercase hex characters, despite describing the value as an exact revision. That is broader than the M1 full-object-ID requirement.
- `snapshot_digest` is optional in SourceSpec V1, populated after snapshot materialization.
- Receipt V5 uses a DSSE-style envelope and an explicit host teardown record. MicroVM teardown requires eight unique checks: VMM exited, VM stopped, cgroups removed, netns removed, disk destroyed, sockets closed, capabilities expired and process scope empty.
- Namespace/dev teardown has a distinct three-check schema and must not be confused with MicroVM trust evidence.

**Implication:** the first native client must reject abbreviated GitHub commit identifiers before admission. Any canonical schema tightening or a new source snapshot binding must be versioned and reviewed; do not silently change V1.

## 2. M1 contract decision

Use a separately versioned **M1 Runner Protocol V1** and **M1 CLI API surface**. Keep current `/v1/runs` and its API-key behavior compatible. Do not retrofit runner semantics into legacy `/complete` or `/logs` endpoints.

M1 has three principals:
1. **Human/CLI principal:** user access token from the device authorization flow, scoped to a selected personal workspace/project.
2. **Runner principal:** enrolled customer runner identity with a short-lived renewable credential or client certificate, distinct from a human user and API key.
3. **GitHub source principal:** short-lived, repository-scoped read access held only by the customer runner's source-acquisition broker; never passed to the guest or written to receipts/logs.

No endpoint accepts a client-supplied `organization_id` as proof of authority. The server resolves project and organization scope from the authenticated principal and validates project membership.

## 3. Proposed M1 endpoints

The paths below are proposed new endpoints. They are not present in the current main source tree.

| Endpoint | Principal | Purpose | Idempotency / fencing |
|---|---|---|---|
| `POST /v2/runs` | CLI user | Admit exact source SHA, profile, policy and runner selection | Required `Idempotency-Key`; unique within resolved project |
| `GET /v2/runs/{run_id}` | CLI user | Read own run and three outcome axes | Project-scoped 404 on unauthorized ID |
| `POST /v2/runners/enroll` | One-time enrollment proof | Enroll customer runner and exchange for runner identity | One-time, expiring enrollment token |
| `GET /v2/runners/me` | Runner | Read its own identity, assigned pool, eligibility and capability limits | Runner-scoped |
| `POST /v2/runner/claims` | Runner | Claim one eligible queued attempt | Lease and attempt fencing; bounded wait |
| `POST /v2/attempts/{attempt_id}/heartbeat` | Runner | Renew the current attempt lease | Must include claim generation/fencing token |
| `POST /v2/attempts/{attempt_id}/events` | Runner | Append typed lifecycle/evidence metadata events | Monotonic sequence; duplicate event idempotent |
| `POST /v2/attempts/{attempt_id}/complete` | Runner | Submit execution result, evidence manifest and host teardown record | Only current lease holder; immutable terminal transition |
| `POST /v2/attempts/{attempt_id}/fail` | Runner | Submit classified infrastructure failure and evidence | Only current lease holder; classified retry creates a new attempt |
| `POST /v2/runners/me/drain` | Runner / authorized operator | Stop receiving new work | Idempotent |
| `POST /v2/runners/me/revoke` | Authorized operator | Revoke runner identity | Immediate denial of future claims/heartbeats |

All mutations return a correlation ID and stable error envelope. The control plane records caller identity, tenant/project scope, run/attempt, policy version and action outcome in its audit trail.

The CLI also requires:
- `GET /v2/me` and `GET /v2/projects` (or an equivalent existing identity/workspace selection contract);
- `GET /v2/runs/{id}/receipt` and bounded evidence metadata access after completion.

These identity/project resources must not be invented client-side. If the current auth service cannot supply them without breaking its existing contract, freeze a compatible additive endpoint before implementation.

## 4. Request/response contract requirements

### 4.1 Run admission

`POST /v2/runs` request semantics:
- `source.provider = github`;
- canonical repository identity and HTTPS clone URL;
- full immutable commit object ID (no branch/tag accepted as final admitted identity);
- profile ID + pinned profile version;
- policy ID + digest;
- guest runtime image digest;
- explicit runner ID or authorized runner-pool selector;
- bounded resource profile;
- required capability set;
- inference mode disabled for M1;
- idempotency key in header, echoed in admission metadata.

The API resolves/validates the selected GitHub repository against the user's authorized installation/repository grant. A branch/tag may be supplied as a convenience selection field, but server-side resolution must record the resulting full object ID before creating the admitted RunSpec. The CLI displays that full ID. If the ref moves afterward, the admitted commit does not change.

**Full-object-ID rule:** M1 GitHub SHA-1 repositories require 40 lowercase hex characters. Do not treat a 7-character short SHA as immutable. If SHA-256 object format is deliberately supported later, the algorithm and full identifier length must be explicit in a new compatible contract; do not infer the format from arbitrary string length.

Admission response:
- run ID, attempt ID, selected project ID;
- resolved repository and full source commit ID;
- accepted policy/profile/runtime digests;
- state = queued/admitted (never running unless a runner has actually claimed it);
- idempotency key digest/reference;
- correlation ID.

No source archive or repository file contents are included in the control-plane request or response.

### 4.2 Runner enrollment and claim

Enrollment:
- one-time token, single use and short expiry;
- runner identity and public key/certificate enrollment;
- operator-selected project or runner pool scope;
- no human access token reuse as runner identity.

Runner capability report:
- host OS/architecture/kernel;
- KVM availability and /dev/kvm access;
- pinned Firecracker and jailer identities;
- approved guest image digests;
- available CPU, memory and disk after reservations;
- runner software version and protocol versions;
- health, drain/revocation state.

Claim response:
- signed, immutable assignment;
- run ID, attempt ID, sandbox ID, project ID;
- source repository identity, full commit object ID and acquisition method;
- profile and runtime/guest image digests;
- policy digest, capability list and resource ceilings;
- network policy and egress class;
- claim generation, lease expiry and fencing token;
- protocol version and nonce;
- maximum output/evidence budget.

Claim must return no assignment when runner is ineligible, has insufficient reserved capacity, or the assignment's profile/image/policy is not present and approved. No strict-to-dev fallback.

### 4.3 Heartbeat and completion

Heartbeat must bind:
- runner identity;
- run ID and attempt ID;
- claim generation/fencing token;
- monotonic heartbeat sequence;
- current execution checkpoint;
- bounded resource/health observations.

The control plane rejects heartbeats for a stale attempt/claim generation, revoked runner, expired lease or already-terminal attempt.

Completion must include:
- final independent host-side teardown verification record;
- guest test report as an untrusted input, distinctly labelled;
- host-observed lifecycle evidence;
- source manifest digest and artifact hashes;
- runtime image/kernel/rootfs/Firecracker/jailer digests;
- policy and assignment digests;
- three independent outcomes (execution, QA, trust);
- signed receipt envelope and signer identity/fingerprint.

A guest message or guest-reported “shutdown success” cannot establish teardown. If any required host teardown check is absent, unknown or failed, the trust outcome cannot be VERIFIED_CLEAN. The control plane stores and serves the receipt as an immutable artifact after validation; it must not rewrite signed receipt bytes.

## 5. Stable error envelope

All M1 endpoints use one shape:

```json
{
  "error": {
    "code": "RUNNER_INELIGIBLE",
    "message": "No eligible strict runner is available for this profile.",
    "retryable": true,
    "correlation_id": "corr_..."
  }
}
```

Required error families:
- `UNAUTHENTICATED`, `FORBIDDEN`, `RESOURCE_NOT_FOUND`;
- `INVALID_REQUEST`, `INVALID_COMMIT_ID`, `SCHEMA_VERSION_UNSUPPORTED`;
- `IDEMPOTENCY_CONFLICT`, `QUOTA_EXCEEDED`, `RATE_LIMITED`;
- `RUNNER_INELIGIBLE`, `RUNNER_REVOKED`, `NO_CAPACITY`;
- `LEASE_EXPIRED`, `STALE_ATTEMPT`, `FENCING_TOKEN_INVALID`;
- `PROFILE_NOT_APPROVED`, `IMAGE_DIGEST_NOT_APPROVED`, `POLICY_REJECTED`;
- `EVIDENCE_INVALID`, `RECEIPT_INVALID`, `TEARDOWN_NOT_VERIFIED`;
- `INTERNAL_ERROR`.

Do not return internal exception text, secret values, GitHub credential material or guest-controlled unbounded strings in public error messages.

## 6. Data and tenancy requirements before multi-user expansion

M1 can use a project-scoped authorization model if one user/project is the explicit supported mode and is accurately documented. The 10–15-user organization/team target requires a separate membership model before beta.

Required data entities:
- User;
- Organization;
- Membership (user_id, organization_id, role, status, invitation metadata);
- Project (organization_id);
- ProjectMembership or an explicit inherited-role rule;
- GitHubInstallation and RepositoryGrant;
- RunnerPool, Runner, RunnerCredentialMetadata;
- Run, RunAttempt, DispatchOutbox;
- LifecycleEvent, EvidenceManifest, Receipt;
- PolicyVersion, ProfileVersion, AuditEvent.

Initial roles: Owner, Admin, Developer, Viewer. Define a permission matrix before adding the membership table. A user's single `org_id` is not sufficient to represent multiple team memberships.

RLS:
- keep project-level policies as the current defense-in-depth baseline;
- add organization/membership policies only alongside schema/authorization implementation;
- all API authorization remains mandatory even with RLS;
- test with a non-owner/non-superuser role without BYPASSRLS;
- context must be transaction-local and cleared on pool return;
- add explicit tests for guessed IDs, cross-org projects, cross-project runner selection and stale membership.

Production database:
- PostgreSQL only;
- no SQLite or in-memory dispatch fallback;
- required RLS and credential envelope encryption;
- durable outbox/dispatcher enabled;
- idempotency key mandatory;
- startup must fail closed when any required production setting is false.

## 7. Required implementation sequence

1. Keep V1 tests green and generate a baseline OpenAPI snapshot.
2. Implement a shared principal abstraction for CLI user, service runner, API key and GitHub installation; do not treat these identities as interchangeable.
3. Add `/v2/runs` with OAuth bearer authentication and project-scoped authorization; preserve `/v1/runs`.
4. Add runner enrollment, capability registration and credential revocation.
5. Add signed claim/lease/fencing protocol and attempt APIs.
6. Implement an outbox dispatcher adapter that targets eligible runner connections rather than calling `SandboxExecutor` for strict mode.
7. Connect runner claim to the existing Firecracker host package through a versioned typed adapter.
8. Require real Gate B; any unsupported/missing KVM/image/network capability remains queued or terminal infrastructure failure.
9. Add receipt/evidence validation and immutable receipt retrieval.
10. Run PostgreSQL tenancy/idempotency/runner-recovery tests and 15-user/45-submission load test.
11. Only after M1, complete membership/roles and dashboard-specific resources for the wider beta.

## 8. Contract tests that gate implementation

- OAuth user token can create/read only runs in its authorized project; API keys keep existing V1 behavior.
- A user token cannot impersonate runner identity.
- Runner cannot create a run as a user or select another tenant's project.
- Runner enrollment token is single-use and expires.
- Revoked runner cannot claim or heartbeat.
- Claim is exclusive; two runners cannot claim the same attempt.
- Lease renewal requires current fencing token; stale runner cannot complete.
- Lease expiry terminates/fences old attempt before retry creates a new attempt and fresh sandbox.
- Idempotent duplicate run submission returns original run; conflicting body under same key is rejected.
- Short commit ID and moving ref are not admitted as final source identity.
- Branch movement after admission does not alter source SHA.
- No repository contents or credential values enter control-plane request logs.
- No guest-supplied completion or teardown claim alone sets trust VERIFIED_CLEAN.
- Tampered receipt/evidence is rejected offline.
- API restart does not lose a committed outbox intent.
- PostgreSQL tenant isolation works with production-like DB role.
- No VM is created when runner admission or policy fails.
- No call to `SandboxExecutor` occurs in the strict Firecracker runner dispatch path.

## 9. Current M1 blockers

| Blocker | Current evidence | Required owner / exit |
|---|---|---|
| User OAuth cannot directly submit V1 runs | V1 route depends on `require_api_key` | GPT-6: additive v2 user-principal endpoint |
| Runner APIs absent | No runner router registered in FastAPI app | GPT-6 + DeepSeek: enrollment/claim/heartbeat/completion contract |
| Firecracker worker not wired to dispatch | Dispatcher invokes `workflo_executor.SandboxExecutor` | DeepSeek: strict dispatcher adapter; MiniMax: negative tests |
| Source commit too permissive | SourceSpec allows 7–64 hex chars | GPT-6: new v2 validator requires full object ID; no silent V1 mutation |
| Organization roles incomplete | User has one org/project; no membership model/API | GPT-6: defer to post-M1 unless multi-user beta becomes immediate |
| Real Firecracker Gate B open | ADR-0022 states mocks do not satisfy; current Linux gate workflow exercises bwrap/namespaces | DeepSeek + MiniMax: real KVM boot, isolation, teardown evidence |
| Receipt signer/trust-anchor operational design | Receipt V5 contract exists, but M1 needs a configured trusted signer and offline trust distribution | Human security owner + DeepSeek: threat model and clean-machine test |

## 10. Freeze / change control

The semantics in sections 2–5 are the proposed M1 interface contract. Before code consumes them:
- GPT-6 publishes OpenAPI and JSON Schema examples;
- DeepSeek confirms runner protocol mappings and Firecracker worker adapter requirements;
- GLM confirms the exact CLI flags, errors and output shape;
- MiniMax reviews identity, capability, replay, lease and receipt trust boundaries;
- human owner approves new canonical schema or security semantics.

After approval:
- changes are additive or versioned;
- no field changes meaning in place;
- golden request/response fixtures are checked in;
- generated clients are updated from the approved source;
- API compatibility tests run for V1 and M1 V2;
- every PR lists contract version, producer, consumers and migration plan.

No production dashboard should consume unapproved endpoints. Gemini's design system should use synthetic fixtures clearly marked as non-production until the real API schema is accepted.
