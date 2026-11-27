# Workflo Trust MVP — File-Level Engineering Backlog v1

**Status:** Proposed implementation plan  
**Branch:** architecture/workflo-trust-mvp-v1  
**Rule:** Architecture changes only in this branch. No production code has been modified by this plan.

This backlog maps each capability to its current repository location. “Create” paths are proposed new files; “change” means inspect and modify only after tests capture current behavior.

---

## 1. Contract and schema authority

| File/path | Action | Work |
|---|---|---|
| packages/workflo-schema/src/workflo_schema/contracts/lifecycle.py | Change/create | Implement frozen ADR-0017 lifecycle and transition authority matrix |
| packages/workflo-schema/src/workflo_schema/contracts/outcomes.py | Change/create | Separate execution status, QA verdict, trust status, clean-success predicates |
| packages/workflo-schema/src/workflo_schema/contracts/canonical.py | Create | Canonical JSON profile from ADR-0016; reject floats in hashed payloads |
| packages/workflo-schema/src/workflo_schema/contracts/events.py | Change/create | RunEventV1 envelope, producer trust classes, event registry, no-CoT rejection |
| packages/workflo-schema/src/workflo_schema/contracts/findings.py | Change/create | FindingV1 categories and deterministic verified-failure stamp |
| packages/workflo-schema/src/workflo_schema/contracts/evidence.py | Change/create | EvidenceArtifactV1/ManifestV1, scope assertions, digest rules |
| packages/workflo-schema/src/workflo_schema/contracts/policy.py | Change/create | Immutable 12-component ExecutionPolicyBundleV1 and digest validation |
| packages/workflo-schema/src/workflo_schema/contracts/receipt.py | Change/create | Receipt v5 payload and DSSE-style envelope; preserve v1-v4 verifier |
| packages/workflo-schema/src/workflo_schema/contracts/patch.py | Change/create | Exact-byte proposal/approval models and path-safety validator; no auto-apply in MVP |
| packages/workflo-schema/schemas/v1/ | Create/export | Commit JSON Schema generated from Pydantic contracts |
| packages/workflo-schema/tests/ | Change | Lifecycle/property tests, canonical fixtures, legacy receipt compatibility, schema export |
| packages/contracts/src/run.ts | Change | Replace incompatible product lifecycle with Zod mirror of canonical export |
| packages/contracts/src/agent-events.ts | Change | Mirror RunEventV1; no parallel event authority |
| packages/contracts/src/receipt.ts | Change | Mirror current receipt metadata contract; do not sign in TS |
| packages/contracts/src/tool-gateway.ts | Change | Mirror tool/action schemas and capability identifiers |
| packages/contracts/tests/ | Change | Cross-language fixtures must match exported Python JSON Schema |
| .github/workflows/ci.yml | Change | Add schema drift test and contract test matrix |

**Acceptance:** a Python-generated schema fixture validates in TypeScript; the lifecycle implementation and API enums cannot drift; receipt v1-v4 verification tests remain unchanged and green.

---

## 2. Control plane

| File/path | Action | Work |
|---|---|---|
| apps/control-plane/app/main.py | Change | Remove duplicate router import; register project, policy, event, and runner routers; keep startup guards |
| apps/control-plane/app/api/v1/runs.py | Change | Canonical lifecycle mapping, outcomes, idempotency, list filters, run/event/finding/receipt reads |
| apps/control-plane/app/api/v1/orgs.py | Change | Tenant membership and role enforcement |
| apps/control-plane/app/api/v1/auth.py | Change | Scope enforcement, session rotation, secure cookie behavior, CSRF integration |
| apps/control-plane/app/api/v1/keys.py | Change | One-time display, hash-only storage, scoped keys, rotation/revocation |
| apps/control-plane/app/api/v1/projects.py | Create | Project CRUD and repository identity binding |
| apps/control-plane/app/api/v1/policies.py | Create | Read/validate/version policy profiles; immutable policy per run |
| apps/control-plane/app/api/v1/events.py | Create | Authenticated cursor-based event replay |
| apps/control-plane/app/api/v1/findings.py | Create | Scoped finding list/detail and evidence reference reads |
| apps/control-plane/app/api/v1/runner.py | Create | Runner registration, lease claim, heartbeat, event/artifact/complete endpoints |
| apps/control-plane/app/api/v1/receipts.py | Create or extend artifacts.py | Receipt metadata and verify endpoint; avoid duplicate artifact APIs |
| apps/control-plane/app/services/admission_service.py | Create | Authorization -> policy resolution -> validation -> durable admission |
| apps/control-plane/app/services/policy_service.py | Create | Build, hash, store, validate immutable policy bundle |
| apps/control-plane/app/services/runner_service.py | Create | Runner identity, claims, leases, fencing token and heartbeat |
| apps/control-plane/app/services/event_service.py | Create | Append event, enforce scope/sequence, update ledger |
| apps/control-plane/app/services/evidence_service.py | Create | Validate evidence metadata and attempt scoping |
| apps/control-plane/app/services/receipt_service.py | Create | Validate evidence/outcomes/teardown before signing |
| apps/control-plane/app/services/dispatch_service.py | Change | Preserve transactional outbox, leases and bounded retries; do not treat in-process execution as hosted worker |
| apps/control-plane/app/db/durable.py | Change | Add stale lease recovery, fencing tokens, terminal transition guards |
| apps/control-plane/app/db/models.py | Change | Organization-scoped project/run/attempt/policy/event/finding/artifact/receipt/runner models |
| apps/control-plane/app/db/queue.py | Restrict | Mark old in-memory/Redis list queue dev-only; no production list queue |
| apps/control-plane/app/core/security.py | Change | Distinct user/runner/API-key auth dependencies and scopes |
| apps/control-plane/app/core/startup_guards.py | Change | Require Postgres/RLS/non-owner role, secure auth config, signing profile, supported runtime |
| apps/control-plane/alembic/versions/ | Create migrations | Tables, tenant keys, RLS, FORCE RLS, grants, indexes, outbox |
| apps/control-plane/tests/test_tenant_isolation.py | Create | Cross-tenant CRUD/join/export/IDOR tests |
| apps/control-plane/tests/test_admission.py | Create | Invalid policy, missing permission, duplicate idempotency, cap and deny tests |
| apps/control-plane/tests/test_runner_leases.py | Create | Expiry, replay, stale fencing token, heartbeat and retry tests |
| apps/control-plane/tests/test_event_replay.py | Create | Idempotent append, sequence gaps, cursor replay, malformed event |
| apps/control-plane/tests/test_receipt_gate.py | Create | Missing evidence/teardown prevents signature |

**Acceptance:** every public route performs server-side authorization; every tenant-owned query uses a tenant-scoped transaction; runner endpoints reject user tokens; production startup fails with SQLite, owner-role RLS, weak secret, or development signer.

---

## 3. Runner host, sandbox, and lifecycle

| File/path | Action | Work |
|---|---|---|
| apps/sandbox-executor/src/workflo_executor/runtime.py | Change | Runtime strategy interface: customer-microvm vs local-development; no silent fallback |
| apps/sandbox-executor/src/workflo_executor/executor.py | Change | Orchestrate provision -> source -> guest -> collect -> teardown -> verify |
| apps/sandbox-executor/src/workflo_executor/docker_runner.py | Restrict | Keep Docker as dev/test mode, label runtime_type; never claim production isolation |
| apps/sandbox-executor/src/workflo_executor/firecracker_runner.py | Create | Firecracker/jailer lifecycle, immutable config, resource limits, vsock |
| apps/sandbox-executor/src/workflo_executor/source_snapshot.py | Create | Host-side repo acquisition, commit pinning, source snapshot digest, no token to guest |
| apps/sandbox-executor/src/workflo_executor/network_policy.py | Create | Default-deny egress, proxy allowlist, DNS/IP and redirect protections |
| apps/sandbox-executor/src/workflo_executor/host_evidence.py | Create | Host-observed process, mount, network, VM and cleanup evidence |
| apps/sandbox-executor/src/workflo_executor/teardown_verifier.py | Create | Independent teardown checks with explicit outcomes |
| apps/sandbox-executor/src/workflo_executor/vsock_protocol.py | Create | Strict typed protocol; version, sequence, attempt binding, size caps |
| apps/sandbox-executor/tests/ | Change | Runtime selection, isolation failures, timeout, kill, teardown, no fallback |
| packages/sandbox-runtime/ | Restrict | Existing bwrap/namespace runtime for development/CI regression only |
| packages/sandbox-runtime/tests/ | Change | Keep negative tests; clearly report dev runtime identity |
| supervisor/src/workflo_supervisor/daemon.py | Change | Trusted host supervisor owns lifecycle and stage transitions |
| supervisor/src/workflo_supervisor/ipc.py | Change | Typed host/guest messages; reject unknown messages and stale attempt IDs |
| supervisor/src/workflo_supervisor/evidence.py | Create | Host evidence collection and ledger append integration |
| supervisor/tests/ | Change | Lifecycle state, IPC replay, crash recovery, evidence chain |

**Acceptance:** an actual KVM test run proves guest/host separation. If KVM or jailer is unavailable, the strict profile is rejected; it cannot silently execute under Docker.

---

## 4. Guest worker and agent runtime

| File/path | Action | Work |
|---|---|---|
| apps/worker-engine/src/workflo_worker/main.py | Change | Guest entry point only; no fake idle-queue behavior; strict run assignment parsing |
| apps/worker-engine/src/workflo_worker/executor.py | Change | Deterministic test/build/security stage orchestration and bounded output |
| apps/worker-engine/src/workflo_worker/agent_runner.py | Change | Strict plan schema, sequence/nonce, budget limits, no policy mutation |
| apps/worker-engine/src/workflo_worker/agent_tools.py | Change | Policy-derived allowlist; path canonicalization, symlink defenses, SSRF defense in depth |
| apps/worker-engine/src/workflo_worker/agent_planner.py | Create | Host-side test-plan proposal interface; typed outputs only |
| apps/worker-engine/src/workflo_worker/evaluator.py | Create | Deterministic finding classification and reproducibility checks |
| apps/worker-engine/src/workflo_worker/model/cloud_llm.py | Restrict/refactor | Remove direct guest-to-hosted calls; route only through host privacy gateway |
| apps/worker-engine/src/workflo_worker/model/llamacpp_runtime.py | Change | Canonical local model runtime with pinned identity, loopback binding and cleanup |
| apps/worker-engine/src/workflo_worker/model/model_server.py | Reconcile | Resolve Ollama vs llama.cpp divergence; release path follows approved GGUF/llama.cpp decision only |
| apps/worker-engine/src/workflo_worker/model/privacy_gateway.py | Create | Host-side schema allowlist and redaction; deny source-bearing hosted payloads |
| apps/worker-engine/src/workflo_worker/model/probe_adapter.py | Change | Strict parse, semantic validation, candidate-only model output |
| apps/worker-engine/src/workflo_worker/security/stage.py | Change | Apply immutable policy and deterministic security stage |
| apps/worker-engine/tests/ | Change | Prompt injection, tool argument abuse, output schema, budget, redaction, cross-run context tests |

**Acceptance:** the worker cannot reach public model providers directly; all model traffic passes the policy router; model output cannot directly execute commands or produce verified findings.

---

## 5. Model integration consolidation

| File/path | Action | Work |
|---|---|---|
| workflo-ai-integration/src/workflo_ai_integration/model_router.py | Migrate | Move model routing into worker model module after interface and tests are agreed |
| workflo-ai-integration/src/workflo_ai_integration/artifact_registry.py | Migrate | Preserve fail-closed artifact manifest and SHA-256 verification |
| workflo-ai-integration/src/workflo_ai_integration/safety_gate.py | Migrate | Preserve schema/AST/compile and generated-path checks |
| workflo-ai-integration/src/workflo_ai_integration/schemas.py | Migrate | Reconcile with canonical workflo-schema contracts |
| workflo-ai-integration/src/workflo_ai_integration/service.py | Reassess | Do not run a second inference API unless needed; keep only if the worker consumes it safely |
| workflo-ai-integration/tests/ | Migrate/preserve | Keep contract, artifact tamper, and fail-closed tests in worker suite |
| workflo-ai-integration/README.md | Change | Mark migration state and exact release dependencies |
| apps/worker-engine/Dockerfile.deep | Change | Pin immutable llama.cpp/GGUF identities, no mutable model tag, no Ollama fallback |
| P4_ACCEPTANCE.md | Change | Reconcile real-artifact and protected-run blockers with final MVP Gate B/Gate D |

**Acceptance:** one serving path, one artifact manifest, no unverified model fallback, and actual inference acceptance—not mock-only tests.

---

## 6. CLI and developer entry points

| File/path | Action | Work |
|---|---|---|
| apps/workflo-cli/ | Change | Preserve canonical command name; add inspect, verify, export-evidence, doctor, and runner profile flags where missing |
| apps/workflo-cli/commands/ | Change | Keep command behavior typed and compatible with current API contract |
| apps/agent-cli/ | Reassess/freeze | Avoid a second user-facing CLI unless this is explicitly an internal agent utility |
| packages/npm-workflo/ | Change | Ensure npm wrapper delegates to canonical CLI behavior and documents supported platforms |
| .github/workflows/workflo-cli.yml | Change | CLI install/run/receipt verification matrix |
| docs/install.md | Change | Clear local-development vs strict customer-microvm install instructions |
| docs/tutorial.md | Change | First PR verification workflow with exact policy and runtime profile |
| docs/api_contract.md | Change | Add only versioned public API behavior; keep old v1 clients compatible |

**Acceptance:** one install path, one command name, reproducible local fixture, and independently verified receipt from a clean workspace.

---

## 7. Dashboard

The canonical UI is apps/dashboard. Do not build product pages in frontend/.

| New or existing path | Action | Work |
|---|---|---|
| apps/dashboard/app/layout.tsx | Change | Workflo app shell, auth boundary, metadata and navigation |
| apps/dashboard/app/page.tsx | Change | Redirect authenticated user to overview; no Tenant Shield placeholder |
| apps/dashboard/app/(auth)/login/page.tsx | Create | Login/device authorization entry |
| apps/dashboard/app/(app)/layout.tsx | Create | Authenticated application shell |
| apps/dashboard/app/(app)/overview/page.tsx | Create | Recent runs, quick start, runner readiness |
| apps/dashboard/app/(app)/projects/page.tsx | Create | Project list |
| apps/dashboard/app/(app)/projects/new/page.tsx | Create | Connect repository / GitHub Actions instructions |
| apps/dashboard/app/(app)/projects/[projectId]/page.tsx | Create | Project overview |
| apps/dashboard/app/(app)/runs/page.tsx | Create | Run list and filters |
| apps/dashboard/app/(app)/runs/[runId]/page.tsx | Create | Outcomes, findings, timeline |
| apps/dashboard/app/(app)/runs/[runId]/evidence/page.tsx | Create | Receipt and artifact verification |
| apps/dashboard/app/(app)/policies/page.tsx | Create | Policy list and read-only details |
| apps/dashboard/app/(app)/integrations/github/page.tsx | Create | CLI/Actions setup |
| apps/dashboard/app/(app)/settings/page.tsx | Create | Members, keys, runner setup |
| apps/dashboard/components/app-shell.tsx | Create | Navigation and org context |
| apps/dashboard/components/run-table.tsx | Create | Typed run list |
| apps/dashboard/components/outcome-summary.tsx | Create | Three independent outcome displays |
| apps/dashboard/components/run-timeline.tsx | Create | Cursor-based event timeline |
| apps/dashboard/components/finding-list.tsx | Create | Verified/candidate/inconclusive distinction |
| apps/dashboard/components/evidence-viewer.tsx | Create | Evidence metadata and digest |
| apps/dashboard/components/receipt-status.tsx | Create | Signature vs factual validation distinction |
| apps/dashboard/lib/api.ts | Create | Typed server-side API client |
| apps/dashboard/lib/auth.ts | Create | Secure session and server authorization helpers |
| apps/dashboard/lib/contracts.ts | Create/generated | JSON Schema/Zod mirror |
| apps/dashboard/lib/query.ts | Create | Shared query keys and typed filters only if React Query is used |
| apps/dashboard/tests/ | Create | Route auth, no mock fallback, tenant context, status display |

**Acceptance:** all shown data comes from authenticated APIs; no production mock fallback; routes deny cross-tenant identifiers.

---

## 8. Communication and integration

| File/path | Action | Work |
|---|---|---|
| apps/control-plane/app/db/durable.py | Change | Transactional outbox, leases, fencing, bounded retries |
| apps/control-plane/app/services/event_service.py | Create | Append-only RunEventV1, sequence checks, replay |
| apps/control-plane/app/api/v1/events.py | Create | Authenticated cursor API |
| apps/control-plane/app/api/v1/runner.py | Create | Runner claim/heartbeat/event/artifact APIs |
| packages/events/src/bus.ts | Restrict | In-memory dev/test bus only |
| packages/events/src/ledger.ts | Align | Mirror ledger semantics; no second canonical hash format |
| packages/events/src/hash-chain.ts | Align | Test against exported canonical fixtures; preserve only if it exactly matches ADR-0016 |
| packages/ingestor/src/ | Freeze or mirror | No parallel production ingestion runtime; retain only after ownership is clarified |
| action/ | Keep archived initially | Use CLI in GitHub Actions; re-adopt only after action package tests/permissions are reviewed |
| .github/workflows/ | Change | GitHub Actions CI entry point uses read-only repository context and scoped Workflo credential |
| docs/connectors.md | Change | GitHub Actions first; document future GitHub App, Slack/Teams and MCP boundaries |

**Acceptance:** events are durable before notification, replayable, idempotent, tenant-scoped, and cannot transition lifecycle when emitted by a guest.

---

## 9. Security and CI files

| File/path | Action | Work |
|---|---|---|
| .github/workflows/ci.yml | Change | Contract, type, tenant, security, worker and dashboard tests |
| .github/workflows/linux-gate.yml | Change | Real runtime negative tests; missing capability fails rather than skips |
| .github/workflows/worker.yml | Change | Worker path and model privacy/security tests |
| .github/workflows/control-plane.yml | Change | RLS and API authorization matrix |
| .github/workflows/dashboard.yml | Change | Typecheck, lint, production build, auth-route tests |
| .github/dependabot.yml | Create/check | Automated dependency update proposals |
| .gitleaks.toml | Create/check | Secret scanning configuration |
| SECURITY.md | Create/update | Responsible disclosure and supported security profile |
| docs/security/THREAT_MODEL.md | Create | Detailed threat model |
| docs/security/SECURITY_TEST_MATRIX.md | Create | Attack class -> control -> regression test map |
| docs/security/RUNBOOK.md | Create | Key rotation, runner compromise, teardown failure, incident response |
| docs/architecture/WORKFLO_MVP_ARCHITECTURE_V1.md | Create | This architecture |
| docs/architecture/WORKFLO_MVP_ENGINEERING_BACKLOG_V1.md | Create | This file |
| docs/architecture/WORKFLO_THREAT_MODEL_V1.md | Create | Threat and abuse cases |

**Acceptance:** every claimed control has a negative test; no workflow can succeed by skipping a required security gate.

---

## 10. Work order and merge dependencies

1. Ratify architecture ownership and contract authority.
2. Implement canonical Pydantic contracts and schema export.
3. Make admission and run lifecycle use the canonical contract.
4. Align PostgreSQL schema, RLS, outbox, event chain, and runner leases.
5. Complete local-first CLI -> executor -> guest -> evidence -> teardown -> receipt.
6. Implement strict Firecracker host path and run Gate B on KVM.
7. Complete dashboard API and user flow.
8. Add GitHub Actions entry point and PR status.
9. Consolidate model routing and privacy gateway.
10. Run design-partner pilots and measure demand.

Do not start steps 6-9 in parallel before contracts and the vertical slice are stable.

---

## 11. First implementation tickets

### WF-ARCH-001 — Canonical contracts
**Deliver:** lifecycle, outcomes, canonical JSON, events, findings, evidence, policy, receipt v5 exports.  
**Tests:** state-machine property tests; cross-language JCS fixtures; schema drift; legacy receipt compatibility.

### WF-ARCH-002 — Production admission
**Deliver:** policy resolution, digest validation, run/attempt/outbox atomic transaction, idempotency.  
**Tests:** invalid policy rejected before provisioning; duplicate key returns same run; retry creates new attempt.

### WF-ARCH-003 — Runner capability and leases
**Deliver:** runner identity, scoped credential, claim, heartbeat, expiry, fencing.  
**Tests:** stale runner cannot submit after lease replacement; wrong project/policy/attempt denied.

### WF-ARCH-004 — Trustworthy vertical slice
**Deliver:** pinned source, deterministic checks, evidence, teardown, signed development receipt, offline verification.  
**Tests:** test failure vs infra failure vs teardown failure; evidence tamper; missing teardown record blocks clean status.

### WF-ARCH-005 — MicroVM Gate B
**Deliver:** Firecracker/jailer runtime and narrow vsock protocol.  
**Tests:** host escape fixture, cross-VM isolation, resource limits, egress default deny, crash/cleanup cases.

### WF-ARCH-006 — Dashboard minimum usable product
**Deliver:** project setup, run list, run detail, evidence viewer, runner status.  
**Tests:** authentication, tenant isolation, real API data, no mock fallback.

### WF-ARCH-007 — GitHub integration
**Deliver:** GitHub Actions template, exact commit binding, idempotency, PR status.  
**Tests:** duplicate workflow dispatch, fork PR restrictions, missing token, revoked token, wrong repository.

### WF-ARCH-008 — AI probe and privacy
**Deliver:** bounded test plan, tool gateway, local model route, hosted metadata-only BYOK route.  
**Tests:** prompt injection, invalid schema, path/SSRF, hosted payload source leak, token budget.

### WF-ARCH-009 — Pilot readiness
**Deliver:** self-hosted install, runbook, support boundary, metrics, three design-partner evaluation.  
**Tests:** clean install on fresh Linux host, successful first run, offline receipt verification, recovery after runner interruption.

---

## 12. Explicit blockers and review notes

- Open draft PR #2 is based on the old p4/14-day-release branch, is marked draft, and was reported non-mergeable. Do not merge it blindly into main. Rebase or cherry-pick only after comparing each change to current main and preserving the P4 release evidence requirements.
- P4_ACCEPTANCE.md explicitly states that real llama.cpp/GGUF execution and protected staging are not proven. Keep that statement until the protected real-artifact workflows pass.
- worker-engine currently contains a direct cloud LLM client and a separate llama.cpp path; consolidate before making a source privacy claim.
- model_server.py documents an Ollama lifecycle while the P4 acceptance documents specify llama.cpp/GGUF. Resolve to one approved release path.
- apps/control-plane exposes durable dispatch, but the current in-process development dispatcher is not the final customer-runner architecture.
- apps/dashboard is the canonical Workflo shell. Integrate the existing data-platform UI and workflows from frontend/ incrementally; initially preserve its implementation behind Workflo service/API façades, map it to canonical tenant/project/asset identities, and consolidate only after route, API, authorization, and data-parity tests. Do not create competing dashboards or duplicate identity/policy/evidence stores.
- The TypeScript run schema currently has a shorter lifecycle than ADR-0017. It must become a mirror rather than a second state authority.
- Firecracker is specified in ADR-0022 but does not yet exist in the repository. This is a real implementation gate, not a documentation-only task.

---

## 13. Definition of MVP complete

MVP is complete only when all of the following are true:

1. A user can install the CLI and configure a project.
2. The CLI or GitHub Action creates a run against an exact commit.
3. An immutable policy is resolved and admitted before provisioning.
4. The supported runner executes deterministic checks in the declared runtime profile.
5. Guest tools are policy-checked, bounded, and recorded.
6. The run produces distinct execution, QA, and trust outcomes.
7. The host verifies teardown independently.
8. An independent verifier validates the signed receipt and evidence chain.
9. A dashboard displays the run and its evidence without mock data.
10. Cross-tenant, replay, tamper, prompt-injection, tool-abuse, and resource-exhaustion tests pass.
11. Strict production runs use the Firecracker profile only after Gate B is evidenced.
12. No raw source is sent to a hosted model.
13. One design partner runs the workflow against a real repository and confirms the result is useful.

Anything less is a prototype or development preview and must be labeled accordingly.
