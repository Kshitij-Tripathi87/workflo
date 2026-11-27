<!-- BEGIN:turborepo-agent-rules -->

# This is NOT the Turborepo you know

Turborepo configuration, task behavior, and CLI commands can vary between installed versions and may differ from your training data. Resolve the `turbo` package from this file's directory or relevant workspace; in monorepos, it may not be visible from the repository root. For example, run `node -p "require.resolve('turbo/package.json')"` from a workspace that depends on `turbo`.

Read `docs/README.md` inside that installed package first, then read the relevant pages from its `docs/` directory before changing Turborepo configuration or commands. Heed deprecation notices. These bundled docs match the installed package version and are available without network access.

This block is written and re-added by `turbo` before repository-scoped commands when an AI agent is detected. In the Turborepo source repository, its template is defined in `crates/turborepo-cli/src/cli/agent_guidance.rs`. Removing the managed block while updates are enabled means a later qualifying invocation will add it again. Set `"agentGuidance": false` in the root `turbo.json` or `turbo.jsonc` to opt out; this does not remove an existing block. Keep the block committed with your work to avoid an uncommitted change on the next agent invocation.
<!-- END:turborepo-agent-rules -->

# Workflo multi-agent engineering rules

Before any Workflo code change, read:
- agent-workspace/README.md
- agent-workspace/00_WORKSPACE_RESTRUCTURE.md
- agent-workspace/01_MODEL_BENCHMARKS_AND_ROUTING.md
- agent-workspace/02_AGENT_OPERATING_PROTOCOL.md
- agent-workspace/03_TASK_CONTRACT_AND_HANDOFF.md
- agent-workspace/04_QUALITY_GATES_AND_ENTERPRISE_CONTROLS.md
- agent-workspace/05_PATH_OWNERSHIP_MATRIX.md
- the assigned agent plan and task-board entry

These rules supplement the Turborepo-managed block above; do not remove or edit that block.

## Mandatory repository rules

1. Workflo product boundaries in PRODUCT_BOUNDARIES.md and accepted ADRs take precedence over model suggestions.
2. One task has one implementation owner and one path allowlist. Use a separate branch/worktree per concurrent task.
3. Do not move, rename or delete source directories as workspace cleanup. Require a migration manifest, dependency/CI impact analysis and owner approval.
4. The production execution boundary is Firecracker/KVM per ADR-0022. Docker and bwrap/namespace execution is development/CI only. No fallback.
5. Canonical contract authority and ADRs 0015–0021 are owner decisions. Do not silently treat proposed ADRs as ratified.
6. Never expose secrets, customer data, signing key material or credential stores to an agent or external model provider.
7. Do not disable, skip, soften or mark continue-on-error for mandatory security or release gates.
8. A model-generated claim is not test evidence. Record actual commands, exit codes, pass/fail/skip counts and artifact identities.
9. A model cannot approve its own implementation, receipt, signature or security claim.
10. Every implementation PR must use the task contract and meet the quality gates in agent-workspace/.

## Scope and status honesty

Distinguish IMPLEMENTED_UNVERIFIED, VERIFIED and ACCEPTED. Never describe a development namespace run as production microVM proof. Never describe a signed receipt as proof of defect-free code or complete security unless the evidence and verifier establish the specific claim.
