# Control-Plane API and Web Application Contract Plan

## 1. Sequence

API design begins immediately because the native CLI, runner and dashboard need stable interfaces. Substantial dashboard implementation remains behind the CLI/runner acceptance gate.

The control plane is also a product dependency of the CLI; it cannot wait until the dashboard is complete. The intended schedule is:
- GPT-6 Luna designs versioned API contracts and data model first.
- Implement the API slices required for CLI auth, project selection, run admission and runner dispatch in parallel with the CLI.
- Complete dashboard-specific list/detail/runner/settings APIs as CLI contract stabilizes.
- Gemini implements substantial web UI after the CLI/run/receipt vertical slice passes.

## 2. API design principles

- OpenAPI is the HTTP contract source generated from FastAPI/Pydantic canonical models.
- Canonical lifecycle, policy, evidence and receipt contracts remain in packages/workflo-schema initially and require human approval to change.
- Keep legacy /v1 surfaces as compatibility; do not silently rename lifecycle statuses in place.
- Add new versioned endpoints only where the current contract cannot represent the approved workflow.
- Use consistent error envelopes, correlation IDs and pagination.
- Mutating requests require idempotency keys where duplicate action is harmful.
- Every route derives org/project membership from authenticated principal context; never trust a client org_id to authorize access.
- Use explicit request size/time limits and schema validation.
- Web client and CLI consume the same APIs, not separate backend paths.

## 3. Required API resources

### Identity
- POST /auth/device/start and /auth/device/poll (or the accepted OIDC/device authorization flow).
- POST /auth/refresh and /auth/logout.
- GET /me and GET /me/workspaces.
- Organization membership and role management.

### Workspaces and projects
- GET/POST /orgs.
- GET/POST /orgs/{org_id}/members.
- GET/PATCH /orgs/{org_id}/projects.
- GET/PATCH /projects/{project_id}.
- Project deletion/archive must be soft/controlled and auditable.

### GitHub integration
- GET/POST /integrations/github/installations.
- GET /integrations/github/repositories.
- POST /integrations/github/disconnect.
- Webhook receiver with signature verification, delivery ID deduplication and replay controls.
- Installation tokens are short-lived and repository-scoped.
- GitHub App secret is server-only; never passed to CLI or guest.

Permissions should be minimal:
- repository metadata read;
- contents read;
- checks write only for PR/commit check publication;
- pull request read only if needed for association.
No contents write, admin or actions write for the initial connector.

### Runner registry
- POST /runners/enroll (one-time, expiring enrollment).
- GET /runners and GET /runners/{id}.
- POST /runners/{id}/heartbeat.
- POST /runners/{id}/capabilities.
- POST /runners/{id}/drain and /revoke.
- GET /runner-pools and bounded pool capacity status.
Runner identity requires short-lived credentials, cert/key rotation and revocation.

### Run admission and lifecycle
- POST /runs with idempotency key.
- GET /runs and GET /runs/{id}.
- POST /runs/{id}/cancel.
- GET /runs/{id}/events (bounded pagination/streaming).
- GET /runs/{id}/attempts.
- POST /attempts/{id}/claim, heartbeat, complete and fail are runner-authenticated endpoints, not user-client authority.
Do not accept a runner's self-reported teardown as trusted completion without independent host verification.

### Findings, evidence and receipts
- GET /runs/{id}/findings.
- GET /runs/{id}/evidence.
- GET /runs/{id}/receipt.
- POST /receipts/verify is optional for server-side convenience; offline CLI verify remains authoritative.
- Artifacts use short-lived scoped download grants or customer-owned object storage. Do not expose broad bucket credentials.

### Policies and provider profiles
- GET/POST /projects/{id}/policies.
- GET/POST /provider-profiles.
- Provider secret material is write-only and never returned by GET.
- API returns provider alias, model identifier, scope, test/health state and key rotation metadata, not the secret.
- Metadata inference consent recorded at organization/project and per-run level with policy version and data categories.

### Dashboard APIs
Dashboard uses the same resources:
- overview summary (query-only, no synthetic values);
- projects and source connections;
- run list/detail/timeline;
- runner list/detail/capacity;
- evidence and receipt;
- team roles and audit log;
- provider/privacy settings;
- usage/quotas and retention.

## 4. Tenant/data model

The required conceptual entities:
- User
- Organization
- Membership
- Role/Permission
- Project
- RepositoryConnection
- GitHubInstallation
- RunnerPool
- Runner
- RunnerCredential/CertificateMetadata
- PolicyVersion
- Run
- RunAttempt
- DispatchOutbox
- LifecycleEvent
- Finding
- EvidenceManifest
- Receipt
- ProviderProfile
- ConsentRecord
- AuditEvent
- UsageReservation/Quota

Every tenant-owned table includes organization scope; project-scoped tables include project identity. Indexes must support organization/project filters and run timeline queries.

Database rules:
- PostgreSQL in production.
- RLS enabled and forced on tenant tables where feasible.
- Application DB role is non-owner, non-superuser and lacks BYPASSRLS.
- Set org context transaction-locally and clear it on connection return.
- Application authorization and RLS are independent layers.
- Test tenant A cannot read/write tenant B even when querying IDs directly.
- No SQLite/in-memory queue fallback in production.
- Migrations are forward-only or have documented rollback; backup before destructive migrations.

## 5. Queue/dispatch and fairness

- Run + first RunAttempt + DispatchOutbox commit atomically.
- Runner claims are leased and attempt-fenced.
- Heartbeats extend leases; stale lease recovery creates a new attempt only after previous attempt is fenced/terminated.
- Run creation idempotency is scoped to org/project/user as defined by the contract.
- Scheduler chooses runners by profile eligibility and available CPU/memory/disk slots.
- Fair queueing prevents one organization from monopolizing all runner capacity.
- Per-user/org/project submission rate and outstanding-run quotas.
- Cancel is an intent until the runner confirms termination and cleanup.
- API responses must never claim that an execution began merely because admission succeeded.

## 6. 10–15 concurrent user acceptance

Load test:
- 15 concurrent authenticated users, across multiple orgs and projects.
- Each user submits 3 runs within a controlled burst (45 total submissions).
- Duplicate/retried submissions with same idempotency key.
- Some requests time out after DB commit and retry.
- Runner pools deliberately constrained to test backpressure.
- One org sends a burst while another submits steady runs to test fairness.
- Two users attempt cross-tenant IDs.
- Runner heartbeat drops and lease recovery occurs during the burst.

Assertions:
- 45 unique run intents at most, with duplicate requests returning the same run for same idempotency key.
- no admitted run disappears on API restart;
- no duplicate active VM for one attempt;
- no cross-tenant data exposure;
- no runner exceeds configured resource reservation;
- queued work remains visible/cancellable;
- no client timeout creates an untracked duplicate;
- API remains responsive and produces bounded errors.

Do not interpret 45 submitted requests as 45 simultaneous VM executions. Runner capacity is measured and admission is backpressured.

## 7. Auth and authorization

Support individual accounts and org/team workspace:
- Individual personal workspace is created at first sign-in.
- Organization membership maps user to org and project permissions.
- Initial roles: Owner, Admin, Developer, Viewer (permission matrix documented and tested).
- Project/repository and runner scope required for run creation.
- Runner service principal is distinct from a human user.
- Token scopes are narrow and time-limited.
- OIDC/device flow uses secure state/PKCE or equivalent documented mechanism.
- Session expiry, refresh rotation and revocation tested.
- Audit high-impact membership, connector, runner, policy and provider-secret operations.

## 8. Web security and UX integration

- Same-site secure session/cookie pattern; CSRF protection for cookie-authenticated mutations.
- Strict CORS allowlist; no wildcard with credentials.
- Content Security Policy and secure headers.
- No provider/GitHub secret returned to frontend.
- Log/artifact rendering escapes untrusted output and disallows active HTML.
- Frontend uses API contract-generated TypeScript client.
- UI shows loading, empty, partial, queued, rejected, execution failed, QA failed, trust failed and verified states.
- Dashboard never presents mock data as actual production state.

## 9. What is deliberately deferred

- Billing/subscriptions.
- Public plugin marketplace.
- SSO/SAML/SCIM.
- Multi-cloud hosted runner fleet.
- Analytics warehouse.
- Autonomous merge/deployment.
- Arbitrary webhook actions.
- General-purpose shell console in dashboard.

Design extension points, but do not build these during the CLI-first phase.
