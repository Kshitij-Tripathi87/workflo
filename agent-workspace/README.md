# Workflo agent workspace

**Purpose:** one shared, version-controlled operating area for the five development agents building Workflo. This workspace governs development of Workflo itself. It does not define or select model providers for Workflo's future customer-facing QA agents.

**Baseline reviewed:** repository main at 25e83ec7b3316b630520bbdba8092d0e591cc3de (2026-11-23). The repository tree contained 1,586 entries when audited on 2026-11-27. This is a documentation and coordination baseline, not a claim that the latest code has been executed and re-tested.

## Read in this order

1. 00_WORKSPACE_RESTRUCTURE.md — repository reality, canonical product boundaries and safe workspace structure.
2. 01_MODEL_BENCHMARKS_AND_ROUTING.md — exact model versions, benchmark evidence, limitations and task routing.
3. 02_AGENT_OPERATING_PROTOCOL.md — shared-folder concurrency, Git worktrees, ownership, permissions and handoffs.
4. 03_TASK_CONTRACT_AND_HANDOFF.md — mandatory task definition and definition of done.
5. 04_QUALITY_GATES_AND_ENTERPRISE_CONTROLS.md — security, testing, release and compliance-readiness requirements.
6. 05_PATH_OWNERSHIP_MATRIX.md — canonical directories, owners and forbidden overlap.
7. coordination/TASK_BOARD.md — prioritized starting backlog.
8. The individual plan under agents/<agent-id>/PLAN.md.

## The five agents

| Agent | Role | Primary responsibility |
|---|---|---|
| Gemini 4 Hydrogen | Principal architect | Architecture, system decomposition, ADRs, cross-module reasoning and design review |
| DeepSeek V4.1 Flash-1017 | Systems implementation lead | Runtime, worker, sandbox, daemon, Linux and backend implementation |
| MiniMax M3.1 Flash | Integration and automation lead | Control-plane integration, GitHub, CI/CD, packaging and release automation |
| GPT-6 Luna | Independent QA and verification engineer | Test strategy, acceptance tests, regression, code review and evidence checks |
| GLM-5.3-Flash | Developer experience engineer | CLI UX, dashboard after stabilization, documentation and bounded frontend/tooling work |

The model version is part of the assignment. Do not silently substitute a preview, predecessor, non-Flash sibling or newer alias and carry the old benchmark claims forward.

## Operating principles

- One repository and one product architecture; five agents do not create five parallel architectures.
- One implementation owner per task and one active writer per path set.
- Use separate Git branches/worktrees for parallel source changes. Shared workspace means shared repository and common plan, not concurrent writes into one mutable checkout.
- The main branch is an integration target, not an agent scratchpad.
- Product boundaries and accepted ADRs outrank model suggestions.
- The canonical contract authority is intended to be packages/workflo-schema; ADR-0015 remains proposed and requires owner ratification before dependent architecture is treated as frozen.
- Firecracker/KVM is the only approved production execution boundary. Docker and bwrap are development/CI profiles and are never production fallbacks.
- A model may propose, implement, test or review. It cannot self-certify a security property, sign its own evidence or approve its own merge.
- No model receives signing keys, production secrets, customer data or unrestricted production access.
- Do not relocate source code as a workspace-cleanup exercise. Any future source move requires a dependency/import/CI impact plan and a separate owner-approved migration task.

## Immediate use

The coordinator assigns a task from coordination/TASK_BOARD.md, copies the template in 03_TASK_CONTRACT_AND_HANDOFF.md, names the implementation owner, reviewer and exact path allowlist, and creates a branch/worktree. The agent returns code plus test output, changed-file inventory, evidence and unresolved risks. The reviewer checks the output from a separate model and the CI system runs the authoritative gates. A human approves merge.

## Status vocabulary

Use only these statuses:

- NOT_STARTED
- READY
- IN_PROGRESS
- BLOCKED
- IMPLEMENTED_UNVERIFIED
- VERIFIED
- ACCEPTED
- DEFERRED
- REJECTED

“Implemented” is not “verified”; “verified” is not “accepted”; “accepted” is not “production-ready”.
