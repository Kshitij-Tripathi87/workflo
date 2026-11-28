# Workflo five-agent engineering workspace

**Version:** v2 — CLI-first beta plan  
**Baseline:** main at 373b02918a87854efe4427b1f4e4ae79905457e8 (2026-11-28)

This workspace coordinates five AI coding agents building Workflo itself. These models are engineering tools. They are not customer-facing Workflo QA models. Workflo does not sell, host or provide customer API models or API credits.

## Product-owner decisions

| Area | Decision |
|---|---|
| Beta users | 10–15 concurrent users, each able to submit multiple runs |
| Execution | Support customer-controlled and managed execution modes architecturally; customer-controlled is the beta default |
| Budget | Zero Workflo-owned runtime spend; customer-owned compute and customer BYOK |
| CLI/runtime | Rebuild in Rust or Go; Rust is the current recommendation pending a measured spike |
| Client OS | Linux, macOS and Windows |
| Launch languages | Python, Node.js, Go and Java |
| Inference | Customer BYOK; hosted prompts are metadata-only and require explicit consent |
| Testing | Core, Deep AI and Security are separate gates |
| Integrations | GitHub, private repositories and pull-request checks |
| Web app | API contracts designed now; substantial web implementation after the CLI gate |
| Identity | Individual accounts and organization/team workspaces |
| Release | No fixed deadline; release only when all required gates pass |

## Read order

1. [06 — CLI-first beta blueprint](06_CLI_FIRST_BETA_BLUEPRINT.md): target architecture, CLI contract, runtime boundary, phases and release gates.
2. [00 — Workspace restructuring](00_WORKSPACE_RESTRUCTURE.md): current repository map, incremental Rust migration and source-move restrictions.
3. [01 — Model benchmark routing](01_MODEL_BENCHMARKS_AND_ROUTING.md): exact-model evidence, model assignment and Workflo bake-off.
4. [02 — Agent operating protocol](02_AGENT_OPERATING_PROTOCOL.md): concurrency, permissions, branch/worktree rules and handoffs.
5. [03 — Task contract and handoff](03_TASK_CONTRACT_AND_HANDOFF.md): required ticket format and definition of done.
6. [04 — Quality gates and enterprise controls](04_QUALITY_GATES_AND_ENTERPRISE_CONTROLS.md): security, privacy, tenant isolation, testing and release evidence.
7. [05 — Path ownership matrix](05_PATH_OWNERSHIP_MATRIX.md): allowed writes and protected directories.
8. [07 — API contracts and account model](07_API_CONTRACTS_AND_ACCOUNT_MODEL.md): API-first account, membership and run contract.
9. [Coordination task board](coordination/TASK_BOARD.md): dependency-ordered execution backlog.
10. Individual model plans under agents/.

## Five-agent allocation

| Agent | Exact model | Primary responsibility |
|---|---|---|
| Architect | Gemini 4 Hydrogen | Repository mapping, architecture, ADR proposals, cross-platform design and integration review |
| Systems engineer | DeepSeek V4.1 Flash-1017 | Rust CLI, local daemon/client runtime, typed protocol and execution lifecycle integration |
| Integration engineer | MiniMax M3.1 Flash | GitHub/private-repository workflow, PR checks, CI, npm/pnpm/Bun and native distribution |
| API and verification engineer | GPT-6 Luna | OpenAPI, individual/team accounts, tenant model, contract tests and independent acceptance review |
| Developer-experience engineer | GLM-5.3 Flash | CLI UX specification, documentation, examples and dashboard only after the CLI/API gates |

## Non-negotiable product and engineering boundaries

- One repository, one product architecture and one canonical contract authority.
- One implementation owner and one writer per task/path set.
- Parallel agents use separate branches and Git worktrees. Shared workspace means a common repository and shared plans, not five writers in one mutable checkout.
- Rust migration is incremental. Keep the existing Python CLI available until parity, compatibility, rollback and clean-machine installation gates pass.
- The existing worker/ path remains the unique Firecracker host lineage. Do not create another production host in a different directory.
- Firecracker/KVM is the only approved production boundary for untrusted code under ADR-0022. Docker, bwrap and namespace paths are development/CI only and are never silent production fallbacks.
- Linux/macOS/Windows CLI support does not mean strict local sandboxing on all three operating systems. Beta strict execution is on customer-controlled Linux/KVM; macOS and Windows clients connect to that runner.
- The beta has no Workflo-funded runner fleet. A future managed-runner adapter may be designed, but it is not offered or promised by this zero-budget plan.
- Source code, diffs, snippets, environment variables, credentials and raw logs are forbidden in hosted model prompts. Hosted prompts are disabled by default. Explicit consent permits only schema-allowlisted metadata; consent cannot widen that data boundary.
- Core, Deep AI and Security outcomes remain independently visible. A skipped required gate cannot be treated as a pass.
- AI output is a hypothesis, not evidence. No model self-certifies its own code, tests, findings or security boundary.
- No coding agent receives production secrets, private signing keys, customer credentials or unrestricted customer repository access.
- These five models are development agents only. Customer inference remains BYOK/local; Workflo does not provide API models.

## Status vocabulary

Use only NOT_STARTED, READY, IN_PROGRESS, BLOCKED, IMPLEMENTED_UNVERIFIED, VERIFIED, ACCEPTED, DEFERRED or REJECTED. Implemented is not verified; verified is not accepted; accepted is not automatically production-ready.
