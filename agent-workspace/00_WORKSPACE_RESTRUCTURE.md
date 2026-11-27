# Workflo workspace restructuring plan

**Audit date:** 2026-11-27  
**Reviewed main commit:** 25e83ec7b3316b630520bbdba8092d0e591cc3de  
**Repository:** Kshitij-Tripathi87/workflo

## 1. Audit findings

The current repository is a historical monorepo, not a single-purpose runtime folder. Its recursive Git tree contained 1,586 entries. The top-level tree includes:

- Product and execution applications: apps/, worker/, supervisor/, apps/control-plane/, apps/workflo-cli/, apps/worker-engine/, apps/sandbox-executor/, apps/dashboard/.
- Shared and supporting packages: packages/, including workflo-schema, workflo-utils, sandbox-runtime, sandbox-isolation, probe-engine, cortex-auth and npm-workflo.
- Additional TypeScript service and runtime lineage: packages/contracts, packages/db, packages/events, packages/sandbox, packages/ingestor and packages/executor.
- Adjacent product surfaces: backend/ and frontend/ for Cortex Autopilot.
- Workflo marketing surface: website/.
- Build, deployment and CI assets: .github/, scripts/, deploy/, infra/, bench/.
- Historical or explicitly legacy surfaces: client/, server/, shared/, drizzle/, action/, examples/ and ci-templates/.

Root documentation already contains a product-boundary decision. The agent workspace must enforce that decision rather than replace it with a model-centric directory arrangement.

## 2. Canonical Workflo Trust MVP boundaries

Use the following as the working product map, cross-checking the source documents before each implementation tranche.

| Responsibility | Canonical path | Boundary |
|---|---|---|
| Canonical typed contracts | packages/workflo-schema/ | Pydantic v2 source of truth, subject to ADR-0015 ratification; JSON Schema exports feed consumers |
| TypeScript contract mirror | packages/contracts/ | Validated mirror/compatibility surface; never a competing authority |
| Control plane, admission and dispatch | apps/control-plane/ | FastAPI + PostgreSQL durable dispatch/outbox; preserve auth, RLS and audit invariants |
| CLI | apps/workflo-cli/ | Canonical developer CLI |
| Dashboard | apps/dashboard/ | Workflo dashboard shell; do not expand before evidence workflow stabilizes |
| Production worker host | worker/ | Firecracker/KVM host and admission boundary; Gate B is not yet proven |
| Guest workload execution | apps/worker-engine/ | Guest-side deterministic checks and later bounded agent features |
| Development execution | apps/sandbox-executor/, supervisor/, packages/sandbox-runtime/ | Docker/namespace profiles for development and CI only |
| Supporting security and test libraries | packages/sandbox-isolation/, packages/probe-engine/, packages/workflo-utils/, packages/cortex-auth/ | Supporting code; do not create parallel implementations |
| npm packaging | packages/npm-workflo/ | CLI distribution wrapper |
| Marketing site | website/ | Workflo content; redesign comes after stabilization |
| Model-serving benchmark harness | bench/model-serving/ | Benchmarking only; no product provider decisions in this development-agent plan |

The exact current status is documented in PRODUCT_BOUNDARIES.md, docs/implementation/BLUEPRINT_STATUS.md, docs/reconciliation/BASELINE_2026-11-11.md and ADR-0015 through ADR-0022.

## 3. Explicitly out of bounds for new Workflo Trust MVP features

- backend/ and frontend/ belong to the adjacent Cortex Autopilot product. Do not extend them for Workflo Trust MVP.
- packages/sandbox/, packages/ingestor/ and packages/executor/ are the TypeScript runtime rebuild lineage. The repository decision freezes new capability investment there until the Firecracker path passes Gate B; retain CI and compatibility as documented.
- client/, server/, shared/, drizzle/ and the root Vite/Express trial-signup surface are archived legacy. Keep only what existing checks require until a separately approved removal.
- action/, examples/ and ci-templates/ are archived unless explicitly re-adopted.
- infra/ contains reference manifests that are not currently validated by CI. Do not deploy or treat them as authoritative without an explicit owner.
- Do not cite docs/benchmark_results_2026.md as measured evidence; PRODUCT_BOUNDARIES.md labels those values synthetic.
- apps/agent-cli and apps/validation-cli are present in the tree but are not assigned a new canonical role by this workspace. Treat their disposition as unresolved until the owner reconciles imports, CLI entry points and CI use. Do not silently delete or extend them.

## 4. Workspace layout

This change introduces one checked-in coordination folder:

    agent-workspace/
      README.md
      00_WORKSPACE_RESTRUCTURE.md
      01_MODEL_BENCHMARKS_AND_ROUTING.md
      02_AGENT_OPERATING_PROTOCOL.md
      03_TASK_CONTRACT_AND_HANDOFF.md
      04_QUALITY_GATES_AND_ENTERPRISE_CONTROLS.md
      05_PATH_OWNERSHIP_MATRIX.md
      coordination/
        TASK_BOARD.md
      agents/
        gemini-4-hydrogen/PLAN.md
        deepseek-v4-1-flash-1017/PLAN.md
        minimax-m3-1-flash/PLAN.md
        glm-5-3-flash/PLAN.md
        gpt-6-luna/PLAN.md

The folder is the shared source of truth for agent roles and task coordination. Product source code remains in its canonical locations listed above.

## 5. How five agents share one project workspace safely

All five agents work against the same repository and the same agent-workspace documentation. They must not all write concurrently into the same mutable working tree.

Use one branch and one Git worktree per implementation task. Worktrees should be siblings of the primary checkout under the user's common workspace directory, not nested in a tracked product source directory. Every branch starts from an explicitly recorded base SHA. A single task has one implementation owner. Reviewers are read-only unless separately assigned a test-only task. Merge through a pull request after the gates pass.

Recommended branch names:

- agent/gemini/<task-id>-<slug>
- agent/deepseek/<task-id>-<slug>
- agent/minimax/<task-id>-<slug>
- agent/glm/<task-id>-<slug>
- agent/gpt6/<task-id>-<slug>

Never put worktrees, generated model traces, local credentials, .env files, customer data or test databases into Git.

## 6. Source restructuring policy

This is a safe, additive workspace restructure. It intentionally does not move or rename product source directories.

A source-tree consolidation may happen only after:

1. Every directory has a named product owner and lifecycle status.
2. Import, entry-point, package, deployment and test dependencies are inventoried.
3. CI workflows and release/install scripts are mapped to source paths.
4. Each proposed move has an old-path → new-path manifest.
5. A compatibility/deprecation window is documented.
6. One move batch is implemented in a dedicated branch.
7. Full import, test, build and release checks pass.
8. The owner approves deletion of obsolete paths.

Do not attempt a big-bang monorepo rewrite. Preserve historical receipt verification, command compatibility, package names and customer-facing paths unless a versioned migration explicitly changes them.

## 7. Current blockers to carry forward

The implementation tracker reports:
- Phase 0: canonical ADR ratification is owner-blocked; current baseline, receipt-v5 writer reconciliation, inference egress inventory and runtime profile labels remain incomplete.
- Phase 1: resolved run plan/policy digest, source snapshot builder, complete guest flow, host evidence completeness and run/run-dev unification remain partial or not started.
- Phase 2: Firecracker Gate B still requires real KVM boot evidence, pinned artifacts, vsock wiring, guest supervisor, actual cgroup/network enforcement, crash recovery and adversarial tests.
- Phase 3/4: provider privacy schemas and parts of the agent/evidence workflow remain incomplete; these are not prerequisites for the five coding agents to build the core runtime unless the task board explicitly says so.

These are statuses recorded in docs/implementation/BLUEPRINT_STATUS.md and the November 11 reconciliation. Revalidate against the current checkout and CI before marking any task ready.

## 8. Structural acceptance criteria

- All five plans exist under this folder.
- Each plan has model-specific benchmark rationale, scope, path ownership, out-of-scope work, first tasks, dependencies, test requirements and a handoff format.
- The common task contract and quality gates are mandatory.
- Root AGENTS.md points agents to this workspace without removing the Turborepo-managed instructions.
- No product source code or package path is moved by this documentation change.
- No legacy surface is reclassified without evidence and owner approval.
