# Five-Agent Operating Model — Permissions, Delivery and Integration

## 1. Purpose

Five models work in one Workflo monorepo with independent ownership, isolated Git worktrees and one integration authority. This is not five equal co-CTOs. Each agent has a bounded workstream and an explicit scope.

## 2. Authority hierarchy

1. Human product owner: product scope, priorities, architecture ratification, provider/infra budget and final release decision.
2. Accepted ADRs and canonical contracts: binding architecture requirements.
3. Workstream owner: implements only within assigned paths and accepted interfaces.
4. Reviewer: independently checks tests, scope and risk.
5. CI and release gate: evidence for tested behavior; it does not grant authority to weaken the architecture.

No model may accept its own security-sensitive PR or override a failed gate.

## 3. Workstream table

| Agent | Owns | Main dependency | Review |
|---|---|---|---|
| DeepSeek V4.1 Flash-1017 | Go CLI core, Go runner, Firecracker host migration | API/protocol contracts | MiniMax + GPT-6 |
| GLM-5.3-Flash | CLI commands, GitHub/local connectors, language profiles, npm/native packaging | CLI core interfaces and GitHub API contract | DeepSeek + GPT-6 |
| MiniMax M3.1 Flash | Policy engine, threat model, sandbox/privacy adversarial suites | Runtime interfaces and data-flow access | DeepSeek + human security owner |
| Gemini 4 Hydrogen | Dashboard IA/design/frontend/browser tests | API contract and CLI gate | GPT-6 + human product owner |
| GPT-6 Luna | FastAPI control plane, API, tenancy, DB, RLS and backend | Canonical contracts and runner protocol | MiniMax + DeepSeek + human owner |

## 4. Stage gates

### Gate 0 — Task readiness
A task cannot start until it has:
- ID and outcome;
- owner;
- allowed directories/files;
- explicit no-touch list;
- dependency version/contract;
- test/acceptance command;
- security/data impact;
- merge/reviewer plan.

### Gate 1 — Audit
Each agent audits existing code first. It may not replace a component merely because it prefers another structure.

### Gate 2 — Contract agreement
API, protocol, lifecycle, receipt or policy changes require written proposal and human decision before implementation.

### Gate 3 — Implementation
Small PRs; tests for behavior; no unrelated mass format/move.

### Gate 4 — Independent review
A different agent or human checks diff, tests, ownership, security/data flows and compatibility. Security-sensitive change requires human reviewer.

### Gate 5 — Integration
Integrator updates branches and runs relevant suites in the canonical checkout.

### Gate 6 — Acceptance
Work is accepted only after the evidence state reaches the required gate: mocked, integration or real environment as specified.

## 5. Required agent daily report

~~~text
Agent/model:
Plan ID:
Branch:
Base SHA:
Current commit SHA:
Completed behavior:
Files changed:
Tests run (exact commands):
Test results (pass/fail/skip):
Real or mocked environment:
API/schema impact:
Security/privacy impact:
Open defects:
Blocked by:
Next deliverable:
~~~

A report without exact test commands and pass/fail/skip counts is incomplete.

## 6. PR requirements

Every PR must contain:
- linked plan/task IDs;
- summary and reasoning;
- changed-file inventory;
- compatibility impact;
- API/schema changes;
- success and negative tests;
- exact commands and counts;
- known limitations;
- security/privacy assessment;
- screenshots/transcripts for UX where relevant;
- no false claims about mocked or skipped gates.

PRs should be small enough to review. A broad rewrite must be split into staged migrations with a verified rollback point.

## 7. Agent permission tiers

### Tier 0 — Read/audit
All agents begin with read-only repository audit.

### Tier 1 — Documentation/tests
May write owned docs and synthetic tests/fixtures.

### Tier 2 — Bounded implementation
Granted for owned paths after task contract and calibration pass.

### Tier 3 — Sensitive implementation
Firecracker, credential, tenant, privacy, policy, crypto and receipt code requires human approval before write and human review after.

### Never granted to coding agents by default
- production secret access;
- prod deployment;
- destructive production database actions;
- GitHub organization administration;
- production runner SSH/shell;
- permission to remove security checks;
- authority to sign release or make security claims.

## 8. Shared-file reservation

The following files/areas require a reservation and human approval:
- packages/workflo-schema canonical contracts;
- receipt signing and verifier semantics;
- lifecycle/outcome enum;
- runner assignment protocol;
- guest/host message types;
- API OpenAPI contract consumed by multiple owners;
- auth/RBAC and RLS policy;
- default network/capability policy;
- package name/version/release workflow;
- root Go workspace and CI merge gates.

Only one agent writes a shared file at a time. The owner announces a reservation, creates an interface PR, and releases it after integration.

## 9. Calibration and routing

Before Tier 2:
- each model completes common audit, bug fix and regression-test tasks;
- specialization tests match assigned work;
- same repo SHA and test harness used for comparable tasks;
- hard disqualification for source/secret leakage, scope violations or weakened gates;
- correctness dominates speed/cost;
- score and reviewer evidence saved in docs/agent-workspace/model-calibration-results.md.

## 10. Integration cadence

- Daily: check blockers and merge small reviewed slices.
- Every 2–3 days: demonstrate the product vertical slice.
- Weekly: review architecture risks, quality trend, capacity evidence and open security findings.
- Never wait until the end to discover the runner protocol, schema or CLI packaging does not work.

## 11. Escalation

Stop implementation and raise a decision when:
- accepted ADR appears inconsistent with code;
- an API/contract field is missing;
- a security gate cannot be run;
- model proposes an unapproved capability expansion;
- source or secret must leave customer boundary;
- requested feature needs more GitHub permissions;
- Windows/macOS strict execution is being implied without a real backend;
- a change would break old receipts or user config;
- cost exceeds zero-budget assumptions.


## 12. Canonical runbook authority

The detailed model-specific plans are authoritative for each workstream:
- DeepSeek: `docs/agent-workspace/agents/01-deepseek-native-cli-runner.md`
- GLM: `docs/agent-workspace/agents/02-glm-cli-connectors-distribution.md`
- MiniMax: `docs/agent-workspace/agents/03-minimax-sandbox-security-qa.md`
- Gemini: `docs/agent-workspace/agents/04-gemini-web-frontend.md`
- GPT-6 Luna: `docs/agent-workspace/agents/05-gpt6-luna-backend-platform.md`

The plans follow the accepted workstream split: three CLI agents (DeepSeek, GLM, MiniMax) and two platform agents (Gemini frontend, GPT-6 backend). Agent assignments in older root-level `agent-workspace/agents/*/PLAN.md` files are superseded; those files must redirect to the canonical plans.

ADR-0024 is Accepted and selects Go for the native CLI and incremental customer-runner migration. No agent may open a Rust-versus-Go implementation debate or create a parallel Rust CLI without a new owner-approved ADR.

Before each task: reserve the exact paths, freeze the interface/version, record base SHA, create an isolated worktree, run baseline tests, and define a second reviewer. Never grant two agents simultaneous write access to the same files. A change touching shared contracts, receipt/trust semantics, auth/RLS, sandbox policy, Firecracker lifecycle or hosted-prompt data flow requires a human-approved task.
