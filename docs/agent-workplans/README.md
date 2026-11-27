# Workflo — Five-Agent Delivery Programme

**Planning baseline:** 27 November 2026  
**Target:** 30-day controlled technical beta  
**Repository:** `Kshitij-Tripathi87/workflo`  
**Status:** Proposed execution plan; tasks become active after the owner confirms the current release commit and dependency gates.

This pack assigns five model agents to bounded engineering workstreams in one Workflo monorepo. It is designed for parallel delivery without parallel architectural authority.

## 1. Release objective

Ship one honest, repeatable Workflo workflow:

1. A developer submits a local or GitHub repository at an exact commit.
2. The control plane authenticates and admits a policy-bound run.
3. An eligible customer-controlled runner provisions a fresh Firecracker/KVM microVM.
4. The approved guest executes deterministic checks; AI-assisted exploration is optional and separately gated.
5. Workflo collects evidence, evaluates execution/QA/trust independently, verifies teardown and signs a receipt.
6. The CLI verifies the receipt offline; the dashboard presents the actual run and evidence.

The launch is a **controlled technical beta**, not a general-availability declaration. A feature that has not passed its real acceptance gate remains disabled, experimental or explicitly unavailable.

## 2. Repository facts that constrain the plan

The current repository is a historical monorepo. The current product-boundary document identifies the Workflo Trust MVP as CLI-first, GitHub-first and based on the Python execution lineage plus `apps/dashboard`.

Active implementation surfaces include:

- `apps/workflo-cli/` — CLI.
- `apps/control-plane/` — FastAPI admission, auth and dispatch.
- `worker/` — Firecracker/KVM host and guest lifecycle.
- `apps/worker-engine/` — guest-side worker execution.
- `packages/workflo-schema/` — canonical contracts and JSON Schema.
- `packages/sandbox-runtime/` — development/CI isolation only.
- `workflo-ai-integration/` — local model integration work to be consolidated into the worker.
- `apps/dashboard/` — Workflo Next.js dashboard shell.
- `docs/adr/`, `docs/reconciliation/` and `P4_ACCEPTANCE.md` — governing decisions and release gates.

Do not extend the adjacent Cortex Autopilot `backend/` or `frontend/` for Workflo product functionality. Do not create a second Firecracker host implementation. Do not move or rename large source directories during this 30-day programme.

Read first:

- [Product boundaries](../../PRODUCT_BOUNDARIES.md)
- [ADR-0022: Firecracker/KVM production boundary](../../docs/adr/ADR-0022-microvm-boundary.md)
- [Phase 0 reconciliation](../../docs/reconciliation/PHASE_0_WORKFLO_TRUST.md)
- [P4 acceptance](../../P4_ACCEPTANCE.md)
- [Repository README](../../README.md)

## 3. Benchmark-informed allocation

Benchmark source material was checked on **27 November 2026**. These are published model/provider results, not a controlled head-to-head Workflo evaluation. The numbers below are task-routing signals, not accuracy guarantees.

| Model | Published relevant result | Best-supported assignment |
|---|---|---|
| DeepSeek V4.1 Flash-1017 | DeepSWE v1.1 77.0; Automation-Bench v1.0.6 60.5; Terminal-Bench 4.0 42.3 | Core execution, control-plane/runner integration and complex repository fixes |
| MiniMax M3.1 Flash | DeepSWE v1.1 73.7; CyberGym 82%; AutomationBench-AA 62.2 | Security review, inference/privacy enforcement and adversarial test development |
| GLM-5.3-Flash | Toolathlon Verified 78.4; Terminal Bench 2.1 84.3; DeepSWE v1.1 63.4 | CLI orchestration, connector workflows and structured API/tool integration |
| Gemini 4 Hydrogen | AutomationBench-AA 76.1; OSWorld-2.1 offline 77.6; Agents' Last Exam v1.1 71.6; SWE-sweep 13.5; Terminal-Bench 4.1 57.0 | Dashboard/product UX, browser-based workflow validation and visual/UI iteration |
| GPT-6 Luna | DeepSWE v1.1 66.6 at max effort; OpenAI reports substantially lower cost per task than its compared Opus/Fable models | Cross-repo QA implementation, regression analysis, contract/test traceability and release evidence |

### Benchmark interpretation rules

1. **Do not rank unlike benchmarks.** SWE-sweep, DeepSWE, Terminal-Bench 2.1, Terminal-Bench 4.0/4.1, Toolathlon, CyberGym and OSWorld test different tasks and harnesses.
2. **Do not compare vendor scores as if they were one lab run.** DeepSeek reports Mini-SWE-V2 harness for DeepSWE and Claude Code harness for Terminal-Bench. MiniMax and GLM publish their own model evaluations; OpenAI and Google publish their own evaluations.
3. **Do not overclaim the Gemini coding score.** Gemini 4 Hydrogen's published SWE-sweep result is not its strongest evidence. Its assignment uses its published automation, computer-use, multimodal and web-development positioning.
4. **Do not treat CyberGym as a security certification.** MiniMax's reported 82% supports assigning it security-analysis tasks; only independent human-reviewed exploitability evidence and Workflo test gates can establish a security result.
5. **Do not treat GPT-6 Luna as a final approver.** Its coding score supports test and integration work; it does not establish that its own review is independent.
6. Benchmark harness, reasoning effort, context, tools, cost caps and version must be logged whenever Workflo performs an internal bake-off.

### Sources (vendor/model primary sources unless stated otherwise)

- DeepSeek model card and technical report: https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash-1017
- MiniMax M3.1 Flash GA and benchmark notes: https://code.minimax.io/tools/m3.1-flash
- Z.ai GLM-5.3-Flash benchmark announcement: https://z.ai/blog/glm-5.3-flash
- Google DeepMind Gemini 4 Hydrogen model card: https://deepmind.google/models/model-cards/gemini-4-hydrogen/
- OpenAI GPT-6 Sol and Luna announcement: https://openai.com/index/introducing-gpt-6-sol-and-luna/
- Independent SWE-Bench Pro V2 protocol/leaderboard context: https://labs.scale.com/leaderboard/swe_bench_pro_public_v2

## 4. Agent ownership at a glance

| Agent | Primary ownership | Explicitly excluded |
|---|---|---|
| GLM-5.3-Flash | CLI workflow, GitHub connector client/integration, developer integration ergonomics | Firecracker host, inference privacy policy, dashboard |
| DeepSeek V4.1 Flash-1017 | Control-plane dispatch, customer runner, Firecracker host/guest integration | CLI UX, dashboard, direct model-provider policy |
| MiniMax M3.1 Flash | Inference gateway, local model integration security, privacy enforcement and adversarial tests | Independent security sign-off; Firecracker lifecycle ownership |
| Gemini 4 Hydrogen | Next.js dashboard and browser/user-flow validation | Control-plane lifecycle changes, schema authority, runner host |
| GPT-6 Luna | Cross-system test suites, CI gates, traceability, release evidence and independent integration review | Owning implementation code of another agent; overriding failed gates |

The detailed instructions are in:

- [Workspace structure and collaboration rules](WORKSPACE-STRUCTURE.md)
- [GLM — CLI and connectors](01-glm-cli-connectors.md)
- [DeepSeek — execution platform](02-deepseek-execution-platform.md)
- [MiniMax — security and inference](03-minimax-security-inference.md)
- [Gemini — dashboard and product UX](04-gemini-dashboard.md)
- [GPT-6 Luna — QA and release](05-gpt6-luna-qa-release.md)

## 5. Dependency order

The work is parallel, but the integration sequence is not arbitrary:

```text
Canonical schemas + release boundary
             |
      +------+------+
      |             |
   CLI/connector  Dashboard shell
      |             |
      +------Control-plane API------+
                     |
             Runner claim/lease
                     |
             Firecracker worker
                     |
              Guest workload
                     |
             Evidence + teardown
                     |
             Receipt verification
                     |
        Dashboard actual run detail

Inference/privacy is a gated optional branch:
guest observations -> approved privacy boundary -> inference gateway -> schema-validated plan -> governed ToolGateway
```

The first complete vertical slice is deterministic and does not depend on a hosted LLM. AI inference is enabled only after the relevant P4 real-artifact and protected-staging gates pass.

## 6. Release gates

- **G0 — Scope/contracts:** accepted run lifecycle, RunSpec, policy, event, evidence and receipt contract versions; generated schema checks pass.
- **G1 — KVM admission:** strict runs reject hosts without KVM and approved pinned runtime artifacts.
- **G2 — Real Firecracker:** real microVM boot, guest workload, resource enforcement, egress controls, negative host-access tests, crash handling and independent teardown evidence.
- **G3 — Runner/dispatch:** durable claim/lease/heartbeat/cancel/recovery path; real PostgreSQL RLS with non-owner application role.
- **G4 — Privacy:** direct hosted inference bypass disabled in the strict profile; only explicit allowlisted observations can leave the runner; outbound payload tests prove source/secrets are not transmitted.
- **G5 — Model:** exact real GGUF/model/image artifacts, immutable identities and protected P4 acceptance workflow pass. If not, keep AI mode disabled or experimental.
- **G6 — CLI/GitHub:** clean install, repository pinning, auth, run/status/verify and least-privilege GitHub integration pass.
- **G7 — Dashboard:** authenticated tenant-scoped projects/runs/runners/receipt views use real API data.
- **G8 — QA/release:** adversarial, tenant, chaos, regression, install/upgrade, SBOM and release-evidence checks pass.

A skip is not a pass. A mock is not real KVM or real-model evidence. The product must never silently downgrade strict execution to a development sandbox.

## 7. Day-30 acceptance

A release candidate is ready only if a clean machine can install the CLI, authenticate, submit a pinned repository revision, get it admitted to an eligible customer runner, execute deterministic checks in a real microVM, verify teardown independently, generate a signed receipt, verify that receipt offline and see the same actual result in the dashboard.

No unresolved critical/high trust-boundary issue is acceptable. If a gate cannot be satisfied, narrow the beta scope and label the capability honestly rather than changing the security claim.
