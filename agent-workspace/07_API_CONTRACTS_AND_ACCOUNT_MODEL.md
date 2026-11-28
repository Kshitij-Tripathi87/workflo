# API contracts and individual/team account model

**Design owner:** GPT-6 Luna  
**Architecture reviewer:** Gemini 4 Hydrogen  
**Status:** proposed contract; not frozen until existing routes are reconciled and owner accepts the relevant ADRs.

## 1. API-first objective

Design the control-plane contract now so the native CLI and customer runner can be implemented against it. The dashboard must later consume exactly the same API. Do not build a second backend or let UI state define run lifecycle.

Existing FastAPI service and PostgreSQL schema under apps/control-plane/ are the starting point. packages/workflo-schema/ remains the proposed canonical typed contract home pending ADR-0015 owner ratification. packages/contracts/ is a compatibility/mirror surface, not a separate authority.

## 2. Core resources

| Resource | Purpose | Tenant scope |
|---|---|---|
| User | Authenticated person and identity-provider subject | Global identity, no direct project/run privileges |
| Workspace | Individual or organization container | Root tenant boundary |
| Membership | User, workspace, role, state, invitation and timestamps | Belongs to workspace |
| Project | Workflo project and configuration | One workspace |
| SourceConnection | GitHub installation/repository reference and secret pointer | One workspace/project |
| Runner | Customer runner identity, capabilities, labels, health and lease | Registered to workspace or explicitly shared by policy |
| RunSpec | Immutable run request, source identity, profiles, gates, policy and privacy | One workspace/project |
| Run | Stable run aggregate | One workspace |
| Attempt | Individual execution attempt with runner/resource binding | One run |
| GateResult | Core/Deep/Security gate result and evidence refs | One run/attempt |
| Finding | Candidate, reproduced, accepted or rejected observation | One run/project |
| EvidenceObject | Digest, type, provenance, size and retention class | One workspace/run |
| Receipt | Signed claims over exact run/evidence facts | One run |
| GitHubCheck | Check-run and webhook delivery mapping | One repository/project |
| AuditEvent | Identity, policy, source, runner, gate and membership changes | One workspace |

## 3. Individual and organization workspaces

A personal account should own a personal workspace. An organization is a separate workspace type with multiple memberships. A user can belong to multiple organizations and switch the active context.

Proposed roles:
- Owner: workspace ownership, transfer, policy, membership and integrations.
- Admin: manage members, projects, runners and integrations, except owner transfer.
- Developer: connect projects, submit/cancel permitted runs and inspect evidence.
- Viewer: read-only project, run and evidence access.

Roles are defaults for the action matrix, not sufficient on their own. Define explicit permissions for create/list/read/update/delete/invite/revoke/connect/submit/cancel/retry/export/manage-runner/manage-policy/manage-secret. Never rely only on hiding UI actions.

## 4. Candidate API domains

Final route names are subject to the current route inventory; do not add duplicate endpoints.

| Domain | Proposed operations |
|---|---|
| Identity | current user, current sessions, list and switch workspaces |
| Workspaces | create individual/organization workspace, get/update, archive policy |
| Membership | list members, invite, accept, change role, suspend, remove |
| Projects | create/list/get/update/archive |
| Sources | connect GitHub, list, inspect, disconnect, rotate/revoke credential |
| Runners | enroll, heartbeat, report capabilities, drain, revoke, inspect lease |
| Runs | preview/admit, create, list, get, cancel, retry |
| Gates | get separate Core/Deep/Security result and artifact references |
| Findings | list, detail, triage and reproduction state |
| Evidence | manifest, metadata, authorized download and verification |
| Receipts | fetch, verify status and verification provenance |
| GitHub | installation callback, webhook, check-run update |
| Audit | list/export authorized workspace events |

## 5. API behavior rules

- OpenAPI 3.1 is the published API contract.
- One canonical schema source; generated clients and JSON Schema must be checked for drift.
- Every request/response carries correlation/request ID.
- Structured errors distinguish validation, authentication, authorization, policy denial, conflict, rate limit, infrastructure failure and incomplete evidence.
- List endpoints define cursor pagination and stable ordering.
- Mutating/retryable calls accept idempotency keys and have documented replay semantics.
- Use conditional updates/ETags for settings that can race.
- Historical run/evidence facts are immutable; corrections append a new event or new version.
- No boolean success field hides execution, QA, trust and gate dimensions.
- Server authorization is derived from verified membership; caller-supplied workspace IDs are selectors, never authority.
- BYOK write endpoints return only a masked secret reference; raw key is never readable after write.
- Never expose runner filesystem paths, guest protocol internals or raw source to normal API responses.

## 6. Multi-tenant authorization and persistence

- Every tenant-owned resource has workspace_id and an ownership relationship validated at write time.
- API service-layer checks and PostgreSQL row-level security both apply.
- Every query is scoped by an authenticated membership context.
- Service-to-service runner identity is distinct from a human user.
- Member removal and role downgrade revoke refresh/session access and force queued runs to revalidate authorization.
- Cross-tenant tests attempt list/get/update/delete/export/cancel/retry, source access, runner actions, findings, evidence downloads, receipts and audit reads.
- Test for IDOR, predictable IDs, stale caches, alternate endpoints and webhook cross-binding.
- Membership, role, source, runner and policy mutations generate append-only audit events.
- Break-glass access is not in beta unless separately designed and audited.

## 7. Run and gate lifecycle

Separate three dimensions:
- Execution: queued, admitted, assigned, running, completed, failed, cancelled, timed out or infrastructure error.
- QA outcome: pass, fail, inconclusive, blocked or not requested.
- Trust outcome: verified, invalid, incomplete or not verified.

Each attempt records runtime profile, commit, source digest, policy digest, runner identity and evidence completeness. Each of Core, Deep AI and Security has an independent status and artifacts. Required skipped gates cannot aggregate to QA pass. Receipt signature validity is separate from QA verdict.

## 8. BYOK and metadata-only hosted prompts

- Customer provides provider credentials; Workflo does not sell model/API access.
- Secret write is encrypted and audited; read operation never returns the value.
- Hosted prompt is disabled by default and requires workspace-level policy plus explicit per-run consent.
- Payload is a typed allowlist of metadata, such as aggregate statuses, duration, categorical result code or coverage count.
- Unknown/free-form metadata is rejected.
- Source file content, diff, snippets, raw logs, traces containing source, environment values, credentials and customer PII cannot be represented in hosted payloads.
- Consent cannot expand the payload schema.
- Log provider, endpoint class, schema version, consent ID and request result, but not sensitive prompt contents.
- Canary tests must prove source and secret values are blocked before network egress.

## 9. Dashboard readiness criteria

Substantial dashboard development begins only after:
1. Existing FastAPI routes and schema compatibility are mapped.
2. OpenAPI has stable request/response, error, pagination and idempotency semantics.
3. Individual/team membership and action-level roles are specified.
4. RLS and cross-tenant negative tests pass.
5. Run, attempt, three gates, findings, evidence, receipt and audit contracts are stable.
6. CLI core workflow and customer runner integration gates pass.
7. API load behavior, rate limits, retention and audit access are specified.

Before then, GLM may create wireframes, UX flows and static prototypes only.
