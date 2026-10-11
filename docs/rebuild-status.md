# Workflo — Rebuild Status

**Started:** 2026-09-30
**Mode:** Execution line (strangler rebuild)
**Packages green:** `@workflo/contracts` (40) · `@workflo/db` (27) · `@workflo/events` (23) · `@workflo/sandbox` (34)

---

## Day 0 — Freeze and Inventory

| Component | Status | Notes |
|-----------|--------|-------|
| Docker sandbox (legacy) | ✅ Working | `--network none`, tmpfs, canary, Ed25519 receipts (Python) |
| CLI (`workflo`) | ✅ Working | Python shim via npm package `@cortexstudio/workflo` |
| Ed25519 receipts | ✅ Working | v1.x, offline verify works |
| Web dashboard (legacy) | ✅ Built | Marketing + docs pages, trial signup (Express) |
| GitHub Action | ✅ Exists | `Cortex Autopilot Impact Gate` (Docker) |
| Linux primitives sandbox | ❌ Missing | Need `bwrap`/`netns`/`cgroups`/`seccomp`/`Landlock` |
| Real-model Explorer | ❌ Missing | Need qwen3-4b-4bit integration via OpenAI-compatible gateway |
| Control Plane API | ❌ Missing | No orgs/projects/missions/runs/receipts endpoints |
| Multi-tenant DB | ❌ Missing | Postgres + RLS not present |
| Event ledger/hash chain | ❌ Missing | Needed for tamper-evidence |
| Trust Plane (transparency) | ⚠️ Partial | Receipts signed but no Merkle log |

**Latest baseline:** Docker sandbox + Python receipts works (legacy).
**Green:** Docker sandbox, Ed25519 receipts, offline verify, CLI, web marketing.
**Fragile:** None observed (legacy is stable).
**Missing:** Linux-native sandbox, control plane, event ledger, real-model Explorer, Merkle transparency, live runs, multi-tenant API, real CI hardening.

**Gate:** ✅ Inventory doc exists.

---

## Day 1 — Monorepo Skeleton and Quality Gate

**Deliverables:**
- ✅ Root workspace (`pnpm-workspace.yaml`, `turbo.json`, `package.json`)
- ✅ TypeScript strict mode (`tsconfig.base.json`: `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`)
- ✅ Lint via ESLint 9 flat config + TypeScript parser
- ✅ Scripts: `check.sh`, `bootstrap.sh`, `baseline.sh`, Makefile
- ✅ Empty package folders per spec
- ✅ `.env.example`, `.gitignore`

**Gate:** `pnpm check` passes ✅

---

## Day 2 — Contracts First

**Deliverables:**
- ✅ `packages/contracts` package with Zod schemas:
  - `ids.ts` — UUID schemas for all ID types
  - `run.ts` — run lifecycle states (CREATED → COMPLETED/FAILED)
  - `agent-events.ts` — `PublicAgentEventSchema` (8 roles × 20 kinds × 5 statuses, strict, no CoT)
  - `explorer.ts` — `ExplorerProposalSchema` (3 tools, relative paths only, no `//`, no CoT fields)
  - `tool-gateway.ts` — `GatewayResultSchema` (`authorized|denied` only, strict)
  - `judge.ts` — `JudgeDecisionSchema` (CONFIRMED/UNCONFIRMED/INSUFFICIENT_CONTROL/ERROR)
  - `receipt.ts` — `ReceiptV4Schema` (with repo provenance, inference provenance, transparency proof, sandbox proofs)
- ✅ Tests: 40 passing in 4 files
  - `explorer.test.ts` — 12 tests (relative paths, scheme-relative rejection, CoT rejection, tail limits, unknown tools, missing fields, length caps)
  - `agent-events.test.ts` — 13 tests (valid event, denied status, optional fields, CoT rejection ×3, length caps, invalid role/kind/UUID, parentEventId)
  - `tool-gateway.test.ts` — 6 tests (authorized, denied with reason/policy, structurally representable denials, invalid decision, length caps, strict mode)
  - `receipt.test.ts` — 9 tests (valid receipt, wrong version, wrong provider, invalid URL, negative tokens, negative checkpoint, tamper detection, missing transparency, missing sandbox keys)

**Day 2 Gate:**
- ✅ invalid proposals rejected (absolute URL, scheme-relative, bad tool, oversized rationale)
- ✅ hidden CoT fields rejected (`thought`, `reasoning`, `internal`)
- ✅ absolute URLs rejected (regex + `//` refinement)
- ✅ denied events structurally representable (`GatewayResultSchema` with `decision: "denied"` and reason/policyId)

**Gate:** ✅ All contract tests pass (40/40)

---

## Day 3 — Database and Multi-Tenancy ✅

**Deliverables (`packages/db`):**
- ✅ `migrations/0001_init.sql` — complete schema, all 12 domain areas:
  organizations, users, memberships, projects, github_connections, missions,
  runs, evidence_events, findings, receipts, audit_logs, inference_usage
- ✅ PG enums mirrored 1:1 from frozen contracts (run_state 9 states,
  agent_role 8, agent_event_kind 20, agent_event_status 5, finding_status,
  finding_severity, judge_confidence, audit_outcome, member_role, …)
- ✅ RLS enabled + FORCE on all 12 tables; tenant context via transaction-local
  GUCs (`app.current_org_id`, `app.current_user_id`); missing context fails closed
- ✅ `transition_run_state()` SECURITY DEFINER — legal transition graph only;
  app role has NO UPDATE on runs; cross-tenant + missing-context raise
- ✅ `judge_finding()` SECURITY DEFINER — verdict only from PROPOSED;
  evidence_refs MUST reference ledger events of the same run;
  judged findings immutable via trigger
- ✅ Append-only at DB layer: revoked UPDATE/DELETE from `workflo_app` +
  `reject_mutation()` triggers on evidence_events, audit_logs,
  inference_usage, receipts
- ✅ Receipts immutable, `UNIQUE(run_id)`, payload validated against
  ReceiptV4Schema before INSERT, `payload_sha256` computed at write
- ✅ github_connections: credential_ref pattern-locked to
  `vault|kms|sm|file://` and explicitly rejects `ghp_`/`gho_`/`github_pat_`
- ✅ AuditLog module on dedicated pool — caller ROLLBACK cannot erase
  denied/failed security operations
- ✅ `Db.withTenant()` — transaction-local GUC binding; per-statement
  SAVEPOINT so expected policy denials don't poison the transaction
- ✅ `migrate()` — checksum-tracked, refuses drifted re-application
- ✅ Test harness: `embedded-postgres` boots real PostgreSQL 18.4 in
  vitest globalSetup (RLS/policies/SECURITY DEFINER tested for real)

**Test results (27/27, 8 files):**
| File | Tests | Gates |
|------|-------|-------|
| migrations.test.ts | 4 | empty-DB apply, idempotency, checksum tamper detection, 12 tables + org columns, RLS+FORCE everywhere |
| rls.test.ts | 4 | A→B deny across 9 tables, missing-context fail-closed, cross-tenant INSERT denied, user visibility |
| append-only.test.ts | 3 | app-role privilege denial ×8, owner-level trigger denial ×8, seq/hash-chain fields |
| run-lifecycle.test.ts | 4 | legal chain to COMPLETED, illegal skip/backward/terminal, direct UPDATE blocked, cross-tenant transition denied |
| findings.test.ts | 3 | propose→CONFIRMED, judged immutability, cross-run evidence rejected, no ai_says_confirmed column |
| receipts.test.ts | 3 | store + one-per-run, no UPDATE/DELETE, contract validation at insert |
| github-connections.test.ts | 3 | vault:// accepted, raw ghp_/gho_/pat/sk rejected, no token columns |
| inference-audit-evidence.test.ts | 3 | telemetry constraints, audit survives rollback, contract limits on events |

**Gate:** ✅ `pnpm check` green (lint + typecheck + 67 tests)

---

## Day 4 — Event Ledger + Hash Chain ✅

**Architecture decision:** the atomic write path lives in the DB — a
`SECURITY DEFINER` function `append_evidence_event(jsonb)` that takes a
per-run advisory lock (`pg_advisory_xact_lock`, no UPDATE privilege needed),
validates chain linkage (prev_hash + run_seq), and inserts — all atomically.
The app role's direct INSERT on `evidence_events` is REVOKED; the ledger
function is the only write path. TS computes hashes; DB is the authority on
chain structure.

**Deliverables (`packages/db` migration 0002):**
- ✅ `evidence_events.run_seq` + partial `UNIQUE(run_id, run_seq)` (per-run chains)
- ✅ `append_evidence_event()` — advisory lock → tenant check → head verify →
  seq allocation → INSERT; chain conflicts raise and the TS ledger retries
  with a fresh locked read
- ✅ `consumer_offsets` (PK `(consumer_id, event_id)`) + `run_projections`
  (rebuildable, DELETE-able derived state)

**Deliverables (`packages/events`):**
- ✅ `hash-chain.ts` — RFC-8785-subset canonical JSON (sorted keys, finite
  numbers, ISO dates) + bound record hashing: v, event_id, org/project/run,
  run_seq, type, role, status, parent, request, action, summary, rationale,
  observation, policy, payload, occurred_at, **prev_hash**. Genesis pinned to
  `sha256("workflo:evidence:genesis:v1")` and TEE-tested against the SQL
  migration literal.
- ✅ `bus.ts` — transport-neutral `EventBus` (delivery-only); publish errors
  never unwrite the ledger; replay recovers consumers
- ✅ `ledger.ts` — `appendEvent` (contract-validated, locked, hashed, fn-written,
  committed → published), `getEvent/getRunEvents/getLatest`,
  `verifyRunChain(…, { expectedHeadHash? })` with structured `ChainVerification`
- ✅ `consumer.ts` — `processOnce()` idempotent via `(consumer_id, event_id)`
  offsets, handler runs in the same tx as the mark (effectively-once)
- ✅ `projection.ts` — pure reducer + `rebuildRunProjection()` (drop the row,
  replay the ledger, identical state)

**Adversarial test matrix (events suite, 23 tests):**
| # | Attack | Result |
|---|--------|--------|
| 1 | normal 3-event chain | VALID, linkage verified |
| 2 | payload byte-level tamper | INVALID at that event (hash mismatch) |
| 3 | event_type metadata tamper | INVALID (hash mismatch) |
| 4 | sequence tamper | INVALID (sequence/linkage) |
| 5 | prev_hash tamper | INVALID (linkage broken, event identified) |
| 6 | middle event deleted | INVALID (gap) |
| 7 | reordered events | INVALID |
| 8a | forged append, garbage link | INVALID (recompute) |
| 8b | forged tail, attacker recomputes hash | passes chain math, **caught by head anchor** (`expectedHeadHash` = receipt ledger_root — the Day 8/9 interface) |
| 9 | cross-tenant read/append/verify | READ: 0 rows; APPEND: rejected; tenant A sees empty world |
| — | mismatched prevHash append | writes nothing (atomic) |
| — | 12 concurrent appends, same run | serialize to sequences 1..12, chain VALID |
| — | bus publish failure | ledger intact, replay recovers |
| — | duplicate consumer delivery | dedup via `(consumer_id, event_id)` |
| — | dropped projection | replay rebuilds identical state |
| — | reducer purity | same events → same projection |

**Honest trust note documented:** pure per-run chain math can't detect a
self-consistent forged tail by itself; the external anchor (receipt
`ledger_root` / transparency checkpoint, Days 8–9) closes that, and
`verifyRunChain` already accepts the anchor parameter.

**Gate:** ✅ `pnpm check` — 3/3 tasks, 90 tests total (40 + 27 + 23)

---

## Day 5 — Sandbox Package Restructure ✅

**Platform stance:** Linux-only execution boundary. On Windows the package
builds/lints/unit-tests; actual bwrap execution is Linux-CI-gated
(`platform.test.ts` skips off-Linux). Non-Linux yields
`PlatformUnsupportedError` with explicit reasons — never a fake sandbox.

**Deliverables (`packages/sandbox` + `infra/policies`):**
- ✅ `spec.ts` — `SandboxSpecSchema` (strict): sandboxId, runId, workspace,
  roBinds, env (cleared-then-set), network deny|allow-loopback,
  resources {cpu, memoryMb, pids, timeoutSec}, usernsRoot, policy names
- ✅ `bwrap.ts` — pure argv builder: `--unshare-all --die-with-parent
  --new-session --clearenv`, hostname, uid/gid 0 in userns, RO `/` +
  toolchain binds, tmpfs /tmp, workspace bind, optional seccomp-FD +
  landlock-helper wrapping; empty command rejected
- ✅ `cgroups.ts` — cgroup v2 layout under /sys/fs/cgroup/workflo/<id>,
  quota math (`cpu.max`, `memory.max`, `pids.max`), attach/kill writes,
  read-back verification with mismatch reporting
- ✅ `netns.ts` — `wf-<id>` create/destroy/verify plan + default-drop
  nftables ruleset (loopback only) for future allow-listed egress
- ✅ `seccomp.ts` — libseccomp-JSON profile loader + audit (forbidden
  allowlist check: ptrace, mount, bpf, io_uring, kexec, modules, ...);
  NO fake BPF compilation in TS (real compile in Linux build step)
- ✅ `landlock.ts` — ABI-v3 ruleset loader, `${workspace}` templates,
  no traversal/relative/non-normalized paths
- ✅ `process-scope.ts` — sandbox-scoped process registry, killAll/waitAll
- ✅ `provisioner.ts` — fail-closed order: platform gate → policy audit →
  plan → cgroup → spawn → attach → verify read-back → network canary
  (getent MUST fail) → IsolationAttestation. Error path kills scope and
  writes cgroup.kill.
- ✅ `teardown.ts` — kill scope → cgroup.kill → rm cgroup/workspace →
  VERIFY from outside (processes, cgroup, netns, workspace) → TeardownProof
  with `verified` = all checks pass
- ✅ `attestation.ts` — IsolationAttestation/CanaryCheck/TeardownProof
  matched to `ReceiptV4Schema.sandbox.*` slots
- ✅ `runner.ts` — exec/spawn/fs seam (Node impl + fake-injectable)
- ✅ `platform.ts` — capability detection (linux/bwrap/cgroup-v2/userns)
- ✅ Shippped policies: `infra/policies/seccomp/{default,strict}.json`
  (deny-default EPERM; strict also drops execve/clone3/socket for
  single-command runs), `infra/policies/landlock/base.json` (RO /usr,/lib,...;
  RW ${workspace},/tmp)

**Test results (34 pass + 1 Linux-gated skip, 6 files):**
bwrap argv correctness · cgroup math/verify drift · netns plan/nft ruleset ·
seccomp load+audit (incl. ptrace rejection, default-ALLOW flagging) ·
landlock templates + path hardening · provisioner happy path (limits written
+ verified, canary required-fail) · limit read-back mismatch surfaced ·
fail-closed cleanup · teardown verified/false paths · platform gating.

**Gate:** ✅ `pnpm check` — 4/4 tasks green, 124 tests passing overall.

---

## Next: Day 6 — Ingestor + Executor Restructure

Target (`packages/ingestor`, `packages/executor`): GitHub ref→SHA resolution,
pinned clone, project detection, dependency install, app startup, health
probe, test execution, teardown verification.
Gate: fixture repo reaches READY, runs tests, tears down cleanly.
