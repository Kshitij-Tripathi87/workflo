# ADR-0015 — Canonical contracts home and stack ownership

**Status:** Proposed (pending project-owner ratification) · 2026-11-11
**Context:** `docs/reconciliation/BASELINE_2026-11-11.md` §5–6

## Context

The checkout holds two contract homes and two execution stacks:

- **Python lineage (shipping):** `packages/workflo-schema` (Pydantic), `apps/workflo-cli`, `apps/control-plane`, `apps/worker-engine`, `apps/sandbox-executor`, `supervisor/`, `packages/sandbox-runtime`. Declared "single source of truth" for the API contract (`docs/api_contract.md`).
- **TypeScript strangler rebuild (Day 0–6):** `packages/contracts` (Zod), `packages/db` (SQL: RLS, append-only ledger, DB-enforced state graph), `packages/events` (hash chain), `packages/sandbox` (bwrap primitives), `packages/ingestor`, `packages/executor`.

The brief's target stack (ADR-014: Next.js + FastAPI + PostgreSQL) and target layout (`apps/control-plane`, `orchestrator/`, `worker/`, `evidence-service/`, `guest-runtime/`) match the Python lineage. The microVM mandate (ADR-001/ADR-0022) replaces *both* current execution boundaries, so the Docker-vs-bwrap split does not survive as a production boundary.

## Decision

1. **Canonical product contracts are authored in `packages/workflo-schema`** as versioned Pydantic v2 modules (`workflo_schema.contracts`, schema version "1"). This is the only authority for RunSpec, lifecycle, outcomes, events, findings, evidence, policy, receipt, and patch contracts.
2. **JSON Schema artifacts are exported from the Python models** and committed (`packages/workflo-schema/schemas/v1/`) for language-neutral validation. `packages/contracts` (Zod) is maintained as a **validated mirror** for the web layer only — it is not a second authority, and a CI check must fail when it diverges from the exported schemas.
3. **The TypeScript SQL and ledger discipline is adopted**: `packages/db` migrations (RLS + FORCE, tenant-local GUCs, `SECURITY DEFINER` transition function, append-only triggers, advisory-lock ledger append, checksum-tracked migrations) are the reference for the canonical PostgreSQL schema, extended to the brief's lifecycle.
4. **TS runtime packages (`sandbox`, `ingestor`, `executor`) are frozen**: no new capability investment, keep CI green, retire only after the Firecracker path passes Gate B. They are not the production boundary.
5. **Cortex Autopilot (`backend/`, `frontend/`) stays an adjacent product**; no Workflo-brief work targets it.

## Consequences

- One authored contract; web consumes exported JSON Schema / mirrored Zod; Python services consume the Pydantic modules directly.
- Existing legacy models (`RunSpec`, `SandboxSpec`, `SignedReceipt` v1–v4, `api.py` v1 wire contract) are **not deleted**: receipt v1–v4 verification must keep working for previously issued receipts. New runs use the frozen contracts.
- The Python lineage carries the critical path (microVM worker, orchestrator, evidence service).

## Alternatives considered

- **TS-canonical:** contradicts ADR-014 and the brief's target layout; would force rewriting the CLI/worker/control-plane/guest runtime in TypeScript.
- **Language-neutral JSON Schema as authored source:** strongest neutrality, but adds codegen tooling on day one; deferred — the export path in decision 2 delivers most of the benefit with no new runtime dependency.
