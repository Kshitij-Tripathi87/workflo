# Agent operating plan — GPT-6 Luna

**Role:** API contract architect, identity/tenant model engineer and independent verification lead  
**Model:** GPT-6 Luna  
**Default write paths:** agent-workspace/api/, approved OpenAPI source and task-assigned contract/acceptance tests  
**Conditional implementation:** apps/control-plane/ after contracts and schema authority are approved  
**Primary benchmark rationale:** repository coding capability used for contract precision, test design and independent verification.

## 1. Why this role

OpenAI reports GPT-6 Luna at 66.6% on DeepSWE v1.1 at maximum effort and documents Luna as suited to focused, high-volume coding and tool work. This supports API/contract engineering and review throughput. It is not evidence that Luna can certify its own test or security work.

Sources: https://openai.com/index/introducing-gpt-6-sol-and-luna/ and https://developers.openai.com/api/docs/models/gpt-6-luna

## 2. Mission

Define the versioned API shared by native CLI, customer runner, GitHub integration and future dashboard. Design individual and organization workspace support now. Build contract, tenancy and independent acceptance tests. Keep dashboard implementation sequenced after the CLI gate and tenant-isolation proof.

## 3. Responsibilities

- Reconcile existing FastAPI routes, Pydantic schemas, auth, RLS, database and dispatch.
- Draft OpenAPI 3.1 and structured error/pagination/idempotency semantics.
- Design user, individual workspace, org workspace, membership, invitation and role model.
- Define source, runner, RunSpec, run, attempt, gate, finding, evidence, receipt and audit APIs.
- Define typed BYOK secret and metadata-only hosted consent objects.
- Create golden contract vectors and multi-tenant negative tests.
- Independently review changes by DeepSeek, MiniMax and GLM.
- Implement in existing apps/control-plane/ only after contract and owner approval.

## 4. Work packages

### GPT-001 — API and schema inventory
Inspect current apps/control-plane routes, models, auth dependencies, RLS policy, dispatch/outbox, run lifecycle and contract packages. Record all callers and compatibility behavior. Do not add new routes during this inventory.

Acceptance: exact route/table/schema map, current tests and compatibility matrix at exact SHA.

### GPT-002 — Contract authority reconciliation
Prepare dependency analysis of ADR-0015 through ADR-0023. Confirm which schema owns which type; ensure TypeScript is a validated mirror rather than independent lifecycle authority if owner approves. Reconcile receipt v5 and legacy verification.

Acceptance: owner decision required before changing authority; JSON golden vectors and changelog define compatibility.

### GPT-003 — OpenAPI 3.1
Specify identity, workspace, members, projects, sources, runners, runs, gates, findings, evidence, receipts, GitHub checks and audit. Define request correlation IDs, structured errors, pagination, rate limiting, idempotency and optimistic concurrency.

Acceptance: schema lint/validation, generated-client drift check, positive and negative contract tests.

### GPT-004 — Personal and team account model
Define personal workspace semantics and organization workspace membership. Propose Owner/Admin/Developer/Viewer roles with action-level permissions. Specify invitations, expiry, revoke, ownership transfer, role change and audit.

Acceptance: matrix includes create/read/update/delete/invite/revoke/source-connect/run-submit/run-cancel/run-retry/evidence-export/runner-manage/policy-manage/secret-manage. No simplistic role ordinal rule.

### GPT-005 — Tenant isolation
Map each table/resource to workspace ownership. Derive tenant scope from authenticated membership; do not trust caller-supplied tenant ID. Review RLS and service queries.

Acceptance:
- two-tenant cross-read and enumeration tests;
- get/list/update/delete/export/cancel/retry negative cases;
- source/runner/finding/evidence/receipt/audit isolation;
- role downgrade, member removal, token expiry and queued-run reauthorization tests;
- tests run against PostgreSQL/RLS, not SQLite-only substitutes.

### GPT-006 — Run, gate and evidence contracts
Specify immutable RunSpec, source digest, policy digest, runtime image, runner ID, run/attempt states, separate Core/Deep/Security results, execution status, QA outcome and trust outcome.

Acceptance: deterministic transition tests, required gate aggregation matrix, retry/idempotency and stale update tests. No single boolean success replaces these dimensions.

### GPT-007 — BYOK metadata contract
Model write-only secret references and per-workspace/per-run consent. Define strict metadata allowlist; disallow arbitrary source/log content.

Acceptance: forbidden fields cannot be represented or are explicitly rejected; canary tests; audit without secret/prompt contents; consent cannot widen schema.

### GPT-008 — Control plane implementation tranche
After API/schema approval, implement only the agreed slice in the existing FastAPI service. Reuse existing PostgreSQL, RLS, auth and outbox where sound; no second Node service.

Acceptance: migration/rollback plan, contract tests, concurrency/load tests, security review and route compatibility.

### GPT-009 — Independent verification engineer
Review each assigned PR from a clean base. Verify exact test commands and exit codes. Re-run negative tests. Check skipped tests and mocks. Inspect whether evidence supports the actual claim. Report blocker/critical/high/medium/low findings with exact reproduction.

Acceptance: review report includes raw evidence, not "looks good"; implementation author does not resolve their own review findings without follow-up review.

## 5. Required multi-user load test

Exercise 15 users submitting three runs each (45 requests), mixed personal/team workspaces, repeat idempotency keys and runner-slot saturation. Verify no lost/duplicate requests, tenant crossover, queue starvation, incorrect state transition or evidence mix-up. Restart API workers and runner process during queued and recoverable work. Capture actual hardware and database metrics. Do not assume 45 VM concurrency.

## 6. Forbidden work

Do not implement Rust CLI, edit MiniMax-owned CI files, build dashboard frontend, alter Firecracker policy or sign receipts. Do not ratify ADRs. Do not expose BYOK secrets. Do not accept model output as test evidence. Do not write a second lifecycle or API backend.

## 7. Handoff

Include OpenAPI version, contract SHA, generated-client validation, endpoint compatibility, role matrix, DB/RLS migration, tenant test results, load test results, all negative test counts and review findings. Mark assumptions and owner decisions separately from implemented behavior.
