# Product boundaries — what is active, what is legacy

This repository is a historical monorepo: several products, prototypes and
one-off integrations accumulated in one tree, and nothing in the code said which
was which. That ambiguity is expensive — contributors have to guess what is
load-bearing, and "the repo is broken" reports mix an active service with a
2024 prototype.

This document records what is maintained and what belongs to the Workflo Trust
MVP. It builds on the [2026-10 stabilization pass](CODE_REVIEW.md) and the
[Phase 0 reconciliation](docs/reconciliation/PHASE_0_WORKFLO_TRUST.md).
Maintenance status below is not production readiness or architecture approval.

Status values:

- **Active** — maintained product surface or development path. Keep CI green;
  passing CI alone does not qualify a path for production.
- **Supporting** — library/package consumed by an active surface. Not deployed
  on its own.
- **Legacy** — kept for reference or migration only; not built, tested or
  deployed by CI. Do not extend it.
- **Quarantine** — unreferenced or duplicated; scheduled for removal once an
  owner confirms nothing depends on it.

---

## Workflo Trust MVP ownership (under review)

Workflo verifies a declared policy against an exact revision and returns
separate execution, QA, and trust results with verifiable evidence. For this
MVP, keep Workflo features on the Python execution lineage and the
`apps/dashboard` Next.js app. Do not extend the adjacent Cortex Autopilot
`backend/` or `frontend/`, or build another Workflo dashboard there.

| Responsibility | Target owner | Current boundary |
| --- | --- | --- |
| Contracts | `packages/workflo-schema` | Versioned Pydantic models and generated JSON Schema. `packages/contracts` mirrors lifecycle and outcomes; its original TS rebuild contracts remain compatibility types. |
| Admission and dispatch | `apps/control-plane` | FastAPI and PostgreSQL outbox. Existing `/v1` statuses are a wire projection, not the new lifecycle. SQLite and in-memory queues are development/test only. |
| CLI and web UI | `apps/workflo-cli`, `apps/dashboard` | The dashboard is a shell; no new screens until the evidence workflow is stable. |
| Customer runner | `worker/` | Initial Firecracker/KVM host and guest-supervisor implementation; not wired end to end and Gate B has not passed. Do not start a second Firecracker host in `apps/sandbox-executor`. |
| Guest execution | `apps/worker-engine` | Deterministic checks; bounded agent and local model features are later increments. |
| Development execution | `apps/sandbox-executor`, `supervisor/`, `packages/sandbox-runtime` | Docker and namespace runs are useful for development and CI only. Neither is a fallback for strict production runs. |
| Inference | Worker-owned local llama.cpp; authorized metadata-only gateway for future hosted BYOK | Direct inference routes have not been reconciled. Do not claim hosted source privacy or add new routes until enforcement is proven. |

The scope is CLI-first with GitHub as the first integration. No autonomous
merge/deploy, dashboard expansion, new orchestration services, or hosted GPU
fleet in Phase 0. The approved production isolation requirement is
[ADR-0022](docs/adr/ADR-0022-microvm-boundary.md); ownership choices in
[ADR-0015](docs/adr/ADR-0015-canonical-contracts-home.md) still require ratification.

## Maintained surfaces

| Path | What it is | Evidence it is live |
| --- | --- | --- |
| `apps/control-plane/` | Workflo control plane (FastAPI): auth, dispatch, envelope encryption, RLS, transparency log | `control-plane.yml` runs API, dispatch, and tenant-isolation tests |
| `apps/workflo-cli/` | The `workflo` CLI (`workflo --version` → 1.1.1) | `workflo-cli.yml` runs 119 tests + a dry-run matrix; `install.sh`/`setup.sh` install it |
| `apps/sandbox-executor/` | Docker development executor | installed by `scripts/linux/setup_env.sh`; covered by control-plane and CLI compatibility tests |
| `apps/worker-engine/` | Guest-side run engine | `worker.yml` unit and integration-style tests |
| `backend/` | **Cortex Autopilot** API: DataHub impact analysis, scenario/what-if engine, receipts, write-back | `ci.yml` (ruff, mypy, 170 tests); `frontend/` consumes it; its own Dockerfile |
| `frontend/` | Next.js UI for Cortex Autopilot | `ci.yml` nextjs matrix (tsc + `next build`) |
| `supervisor/` | Development namespace supervisor used by the CLI | `supervisor/` has 12 IPC tests wired into CI; imported by `apps/workflo-cli` |

## Supporting libraries (consumed by the surfaces above)

| Path | Notes |
| --- | --- |
| `packages/sandbox-runtime/` | Development namespace runtime: bwrap/cgroups/netns/Landlock. The real integration suite in `linux-gate.yml` gates this profile only, not Gate B |
| `packages/sandbox-isolation/`, `packages/probe-engine/`, `packages/cortex-auth/` | Installed by `setup_env.sh`; used by the sandbox stack |
| `packages/workflo-schema/`, `packages/workflo-utils/` | Schemas/utils shared by control plane + CLI |
| `packages/npm-workflo/` | npm distribution of the CLI (`file:` dependency of the root project) |
| `workflo-ai-integration/` | Local model router + safety gate (llama.cpp path) destined for the sandbox worker. Disposition **MERGE** — see the disposition table below |
| `bench/model-serving/` | Model-serving benchmark harness (throughput + unit economics). Runs against any OpenAI-compatible endpoint; its stub-server test runs in `linux-gate.yml` |

## Marketing / product sites

| Path | Status | Notes |
| --- | --- | --- |
| `website/` | Active (content) | Next.js marketing site, 5 static routes. Now covered by the `nextjs` CI matrix — it previously had **no** CI, which is how broken JSX shipped in it |
| `apps/dashboard/` | Active (content) | Next.js dashboard shell; now covered by the `nextjs` CI matrix |

> The website redesign is deliberately sequenced **after** the stabilization
> gates (clean build → clean dependency graph → green CI → fail-closed
> production config → boundaries documented). This file is that last gate.

## Legacy — do not extend

| Path | Why legacy |
| --- | --- |
| `client/`, `server/`, `shared/`, `drizzle/`, `drizzle.config.ts`, `vite.config.ts`, root `dist/` | The root Vite/Express "trial sign-up" app generated by Manus (`vite-plugin-manus-runtime`, `server/trialSignups.ts`). It overlaps the marketing site's purpose, is coupled to a specific external builder, and is unrelated to the CLI/control-plane products. The root `package.json` still ties `pnpm check` / `pnpm test` to it, so it is kept green, but no new work should target it |
| `action/` | GitHub Action wrapper (Dockerfile + `cortex.yml.example`). Depends on the legacy Cortex naming; not referenced by any workflow |
| `examples/` | Generated example artifacts + sample tests from an earlier demo pass |
| `ci-templates/` | `gitlab.yml` — the repository is GitHub Actions only |
| `infra/` | k8s/oracle/terraform/vllm manifests for deployment shapes that the CI never validates. Treat as reference material until an owner re-adopts one |
| `docs/benchmark_results_2026.md` | Synthetic benchmark numbers. **Not** a measured result; do not cite it |
| `deploy/*.env.example` | Env templates for the control plane; keep aligned with `apps/control-plane/app/core/config.py` |

## Dispositions — no item stays in limbo

Quarantine is not a destination. Every previously-ambiguous item below has an
assigned state, the evidence behind it, and what would change it. States:
**KEEP** (active, has an owner), **MERGE** (functionality belongs elsewhere),
**MIGRATE** (move required code to the canonical location), **ARCHIVE**
(preserved, no active execution), **DELETE** (confirmed dead).

| Item | State | Evidence and next action |
| --- | --- | --- |
| `workflo-ai-integration/` | **MERGE** | Its own README: *"Standalone scaffolding for the LoRA-adapter path... Meant to be merged into the real sandbox worker once adapters exist."* 24 mock-based tests, green, now run by the `ai-integration` CI job. **Action (P4):** move `src/model_router.py` + `src/safety_gate.py` into the worker's model path once adapters exist; then delete the scaffolding. The double-nested directory (bad extraction) was flattened on 2026-10-08. |
| `bench/` | **KEEP** | Was referenced by a test but absent from the tree; the harness was implemented on 2026-10-08, its stub test runs in `linux-gate.yml`, and `--gpu-hourly-usd` keeps cost figures explicitly assumed rather than invented. |
| `data/`, `backend/data/` | **KEEP** (runtime state) | Untracked and git-ignored; `WRITEBACK_DIR` keeps test runs out of them. Not a quarantine item any more — committing them again would recreate the dirty-diff problem. |
| `client/`, `server/`, `shared/`, `drizzle/`, `vite.config.ts`, root `dist/` | **ARCHIVE** | Root Vite/Express trial-signup app coupled to Manus. Kept because the root `pnpm check`/`pnpm test` scripts still cover it; **action:** once the marketing site owns trial sign-up, delete the app and the root scripts with it. |
| `action/` | **ARCHIVE** | GitHub Action wrapper on the legacy Cortex naming; no workflow references it. **Action:** re-target at the CLI or delete. |
| `examples/` | **ARCHIVE** | Generated demo artifacts from an earlier pass. `examples/generated-tests/` contains skips by design (sample output), so it is not a test suite. |
| `ci-templates/gitlab.yml` | **ARCHIVE** | Repository is GitHub-Actions only. |
| `infra/` | **ARCHIVE** | k8s/oracle/terraform/vllm manifests. `infra/vllm` documents the actual serving target for `bench/model-serving`; the rest is unreferenced and unvalidated by CI. |
| `docs/benchmark_results_2026.md` | **ARCHIVE** | Synthetic numbers — explicitly not a measurement. Never cite it as a result. |
| `deploy/*.env.example` | **ARCHIVE** | Keep aligned with `apps/control-plane/app/core/config.py`; not consumed by any workflow. |

### Rule that produced these dispositions

```
missing implementation -> the test FAILS   (never SKIP -> green)
obsolete test          -> the test is REMOVED
implemented capability -> the test RUNS
```

The benchmark harness is the worked example: its test previously skipped with
"the harness is not part of this repository", which is an implementation gap
dressed as a pass. The harness now exists, the test executes, and a missing
harness fails the suite.

## Product identity

Use **Workflo** for the Trust MVP, including the CLI, control plane and
`apps/dashboard`. *Tenant Shield* names retained in files and environment
variables are historical compatibility names, not a second MVP. **Cortex
Autopilot** (`backend/`, `frontend/`) is the adjacent data-platform product and
is not a target for Workflo Trust features. Existing protocol and package names
are not renamed by this decision record.

## Rules that follow from these boundaries

1. An **Active** surface must have CI that runs its real tests. Workflows that
   `|| true` a failing gate, or assert on a platform capability they skip, are
   false green and are treated as defects (`linux-gate.yml` could not even be
   parsed before this pass).
2. **Legacy** code is not built. If something in a legacy path breaks, the
   default answer is deletion, not repair.
3. Nothing generated at runtime (data mirrors, vector stores, build caches,
   coverage) is committed. `data/`, `*.tsbuildinfo` and `dist/` are ignored.
4. Production must not start with development defaults — see
   `apps/control-plane/app/core/startup_guards.py`.
