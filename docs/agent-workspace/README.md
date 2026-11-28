# Workflo Engineering Agent Programme

**Current milestone:** M1 — native Go CLI → customer Firecracker/KVM → independently verified receipt  
**25-day target:** 23 December 2026 (programme starts 29 November 2026)  
**Repository:** `Kshitij-Tripathi87/workflo`  
**Planning state:** execution documents; implementation and M1 acceptance are not claimed

This is the single source of truth for the five-model Workflo engineering programme. These models are development agents used to build Workflo; they are not customer-facing inference providers in the Workflo product.

## 1. The first result

One exact GitHub commit must be submitted by the native Go CLI, admitted idempotently through the existing FastAPI control plane, claimed by a separately enrolled customer Linux/KVM runner, executed inside a fresh Firecracker microVM using one pinned pytest profile, independently torn down, signed into the canonical receipt and verified offline on a clean disconnected machine.

The first milestone is **not** five agent plans, five PRs, a mock runner or a dashboard prototype.

## 2. Binding architecture decisions

| Area | M1 decision |
|---|---|
| CLI | Native Go binary; no Python/Node/model runtime dependency |
| Backend | Existing FastAPI/Python, additive versioned M1 API; V1 compatibility retained |
| Runner host | Existing Python Firecracker host under `worker/` remains M1 reference behind a narrow adapter |
| Go runner | Target migration is incremental per accepted ADR-0024; full Go runner parity is post-M1 |
| Guest | Existing guest engine; one pinned Python/pytest profile |
| Isolation | Fresh Firecracker/KVM microVM per attempt; no fallback |
| Identity | Existing device-flow human identity and server-resolved project; separate runner identity |
| Receipt | Existing canonical Receipt V5/DSSE and MicroVM teardown contract |
| AI | No model/provider required for M1 core |
| Web | Gemini design preparation only until signed M1 acceptance |

Read the accepted [ADR-0024](../adr/ADR-0024-native-go-cli-and-runner.md). Do not reinterpret “incremental Go runner migration” as a requirement to rewrite the Firecracker host before proving the existing host path.

## 3. Workstream assignments

| Agent | Primary work | Explicit boundary |
|---|---|---|
| **DeepSeek V4.1 Flash-1017** | Go CLI core, typed API/auth client, host adapter integration, guest protocol client, receipt handoff and offline verifier | Does not own FastAPI, canonical contracts or security approval; no second Firecracker manager |
| **GLM-5.3 Flash** | Command tree/handlers, UX/output/exit codes, GitHub SHA connector, M1 profile metadata and distribution design | Does not own CLI entrypoint/core transport, backend, host or package publishing in M1 |
| **MiniMax M3.1 Flash** | Threat model, deterministic policy tests, synthetic adversarial fixtures, independent source/network/resource/protocol/teardown/receipt review | Does not own Firecracker implementation or final security sign-off |
| **Gemini 4 Hydrogen** | Dashboard IA, design tokens, component contracts, synthetic prototype and browser/accessibility plan | No production dashboard/API integration before M1 acceptance |
| **GPT-6 Luna** | FastAPI M1 OpenAPI/API, project auth scope, durable run admission/outbox, runner enrollment/lease/dispatch, evidence metadata and PostgreSQL tests | No M1 dependency on org membership, role system, inference, analytics, dashboard APIs or 45-submission scale test |

Agent task IDs, file ownership, exact steps, acceptance checks, exclusions, reporting and capability boundaries are specified in each runbook.

## 4. Programme documents — use in this order

### Governing plan and interfaces
1. [25-day M1 execution plan](M1-25-DAY-EXECUTION-PLAN.md)
2. [M1 interface registry](M1-INTERFACE-REGISTRY.md)
3. [M1 milestone acceptance specification](MILESTONE-01-NATIVE-CLI-FIRECRACKER-RECEIPT.md)
4. [M1 API contract freeze](API-CONTRACT-FREEZE-M1.md)
5. [Dependency-gated delivery roadmap](DELIVERY-ROADMAP.md)
6. [Five-agent operating model](AGENT-OPERATING-MODEL.md)

### Agent runbooks
- [DeepSeek — Go CLI and runtime integration](agents/01-deepseek-native-cli-runner.md)
- [GLM — CLI commands and GitHub source connector](agents/02-glm-cli-connectors-distribution.md)
- [MiniMax — sandbox security and adversarial QA](agents/03-minimax-sandbox-security-qa.md)
- [Gemini — dashboard IA and design preparation](agents/04-gemini-web-frontend.md)
- [GPT-6 Luna — M1 control plane and runner APIs](agents/05-gpt6-luna-backend-platform.md)

### Calibration and design
- [Model calibration protocol](MODEL-CALIBRATION-PROTOCOL.md)
- [Calibration evidence ledger](model-calibration-results.md)
- [Dashboard design-system preparation](DASHBOARD-DESIGN-SYSTEM-PREPARATION.md)

## 5. 25-day delivery cadence

- D1–D2: source audit, environment confirmation, actual model IDs/calibration, interface freeze.
- D3–D8: native CLI, command contract, auth, idempotent admission and runner identity.
- D9–D17: Firecracker host integration, immutable source, guest protocol, limits, evidence, teardown, receipt and offline verifier.
- D18–D22: end-to-end proof, negative tests, clean machine/recovery and backend acceptance.
- D23–D25: independent review, evidence packet, release candidate and human go/no-go.

The full day-by-day plan and exit evidence are in the [25-day plan](M1-25-DAY-EXECUTION-PLAN.md). If a real KVM/signing dependency is missing, report BLOCKED; do not change test classification.

## 6. M1 scope exclusions

No full Go runner rewrite, local-folder connector, four-language expansion, deep AI/BYOK, org/team roles, GitHub webhook/check publishing, public package publishing, feature-complete dashboard, hosted execution fleet, or 15-user/45-submission capacity claim. These are post-M1 epics.

## 7. Current state discipline

The documents describe what to build and how to accept it. They do not claim that:
- Workflo-specific model calibration has run;
- local worktrees exist on the user's machine;
- Go CLI or Go runner exists;
- runner APIs are implemented;
- V2 dispatch reaches Firecracker;
- real KVM, teardown or offline receipt gates have passed.

Those states change only with repository commits and attached test evidence. The human owner retains architecture, security, merge and release authority.
