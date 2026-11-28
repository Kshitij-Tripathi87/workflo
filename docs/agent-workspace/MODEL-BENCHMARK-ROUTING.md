# Model Benchmark Analysis and Agent Task Routing

**Research date:** 28 November 2026  
**Purpose:** assign the five development models to Workflo engineering work according to their strongest relevant published evidence.

## 1. Important scope clarification

The five models below are the coding, testing and development agents used by the Workflo team. They are **not** models offered to Workflo customers. Workflo's customer-facing AI feature is BYOK: customers configure their own provider/API credentials. Never put one of the development-agent credentials into Workflo runtime configuration.

Research focuses on terminal coding, long-horizon software engineering, automation/tool use, cybersecurity, computer use and web development. Prefer the exact model's primary model card or release note. Scores are lab-reported unless a cited source explicitly says otherwise.

## 2. Benchmark summary

| Model | Terminal/CLI evidence | Repo/SWE evidence | Automation/tool evidence | Security evidence | UI/browser evidence |
|---|---|---|---|---|---|
| DeepSeek V4.1 Flash-1017 | Terminal-Bench 4.0: **42.3** | DeepSWE v1.1: **77.0**; NL2Repo-Bench: **68.2** | Automation-Bench v1.0.6: **60.5** | No CyberGym result in this model card | Chartography w/tools: 83.0; visual evidence is not a frontend benchmark |
| MiniMax M3.1 Flash | Terminal-Bench 4.0: **38.1** | DeepSWE v1.1: **73.7**; NL2Repo-Bench: **61.2** | Automation-Bench v1.0.6: **62.8** | CyberGym: **82.2** | OSWorld 2.0: 61.7 |
| GLM-5.3-Flash | Terminal-Bench 2.1: **84.3** | DeepSWE v1.1: **63.4**; NL2Repo: 56.3 | Toolathlon Verified: **78.4**; AutomationBench v1.0.6: **48.8** | No directly comparable cyber benchmark result found in the cited primary source | OfficeQA Pro/Chartography results are document/chart tasks, not frontend UX |
| Gemini 4 Hydrogen | Terminal-Bench 4.1 cheating-adjusted: **57.0%** | SWE-sweep: **13.5%** | AutomationBench-AA: **76.1%** | No directly comparable CyberGym result in this model card | OSWorld-2.1 offline subset: **77.6%**; vendor explicitly lists web development as intended use |
| GPT-6 Luna | No directly comparable Terminal-Bench result stated in the cited release | DeepSWE v1.1: **66.6% at max effort** | No directly comparable AutomationBench result in the cited release | No directly comparable CyberGym result | OpenAI reports Luna max exceeds GPT-5.6 Sol medium on OSWorld 2.0 at about one-tenth the cost; no exact Luna score is stated there |

## 3. What the numbers do and do not mean


### MiniMax Automation-Bench score discrepancy

The MiniMax official model card currently reports **62.8** for Automation-Bench v1.0.6 in its comparative table. A secondary measured-score index reports **62.2** for MiniMax M3.1 Flash as of 12 November 2026, while another secondary November 8 table also reported 62.8. The available sources do not explain whether this reflects a score revision, task-set/configuration difference or tracker snapshot. For routing, quote the primary model-card value as **vendor-reported 62.8**, record the secondary 62.2 discrepancy, and do not treat a 0.6-point margin over DeepSeek as decisive. Workflo's same-harness calibration must decide the practical assignment.

Sources:
- Primary model card: https://huggingface.co/MiniMaxAI/MiniMax-M3.1-Flash
- Secondary measured index snapshot: https://benchgap.net/b/automationbench/current
- Secondary November snapshot: https://aicost.tools/benchmarks/automationbench/

### Terminal benchmarks are version-specific

- DeepSeek reports Terminal-Bench **4.0** under the Claude Code harness.
- MiniMax reports Terminal-Bench **4.0** under Codex 0.149.1.
- Gemini reports Terminal-Bench **4.1**, with a cheating-adjusted result.
- GLM reports Terminal-Bench **2.1**.

Do not compare 84.3 on Terminal-Bench 2.1 with 42.3 on Terminal-Bench 4.0 as if they were on the same test. The benchmark version, tasks, harness, tooling and scoring are different.

### DeepSWE is not interchangeable with every SWE benchmark

DeepSWE v1.1 tests long-horizon software-engineering work in real codebases. The cited primary sources use different harnesses:
- DeepSeek: Mini-SWE-V2.
- MiniMax: mini-SWE-agent 2.4.5, 512K context.
- GLM: vendor reports DeepSWE v1.1; its public result page describes the benchmark result.
- OpenAI: DeepSWE v1.1, Luna max effort.

Do not call this SWE-bench Verified or SWE-bench Pro. The exact benchmark name must remain attached to every number.

### Automation benchmarks differ

- DeepSeek and MiniMax both report Automation-Bench v1.0.6 in the comparative table.
- GLM reports AutomationBench v1.0.6 in the Z.ai model release.
- Gemini reports AutomationBench-AA, a separate evaluation surface.

MiniMax's 62.8 and DeepSeek's 60.5 are the closest same-benchmark comparison in the available source set. MiniMax leads that published table by 2.3 points. This supports automation/tool-orchestration work, not automatic superiority in every agent task.

### CyberGym is not a security certification

MiniMax reports 82.2 on CyberGym. This is a benchmark result, not evidence that its generated security fixes are correct, safe or complete. Every Workflo security finding needs a reproducible test, independent review and a controlled authorized fixture.

### Frontend/UI evidence is limited

Gemini's model card explicitly lists web development and rapid agentic workflows as intended usage. Its OSWorld/AutomationBench results support computer-use and workflow work. They do not directly measure typography, accessibility, visual hierarchy or frontend code quality. Gemini should be calibrated on Workflo's actual dashboard tasks and screenshots/browser tests.

GPT-6 Luna's public source supports long-horizon coding and cost-efficient software-engineering tasks. The cited sources do not establish that Luna is the best backend architect or a dedicated database specialist. It is assigned backend work because it has a strong repo-engineering result; human architecture review and Workflo-specific calibration remain mandatory.

## 4. Model-specific interpretation and assignment

### DeepSeek V4.1 Flash-1017 — native CLI/runtime implementation

Why:
- DeepSWE v1.1: 77.0, the highest score among these five in the cited exact-version comparison.
- Terminal-Bench 4.0: 42.3, higher than MiniMax's 38.1 in the same MiniMax comparison table.
- Automation-Bench v1.0.6: 60.5.

Assign:
- Go CLI core and process/runtime orchestration.
- Native runner agent and lifecycle integration.
- Firecracker host integration in the existing canonical worker path.
- Cross-platform binary build/test infrastructure.
- Long-horizon multi-file migration and debugging.

Avoid:
- asking it to approve its own sandbox security;
- unreviewed changes to receipt/schema semantics;
- changing product boundaries or moving legacy trees without approval.

### GLM-5.3-Flash — CLI workflow, connectors and distribution

Why:
- Terminal-Bench 2.1: 84.3 in the Z.ai release.
- Toolathlon Verified: 78.4, reported pass@1 averaged over three independent runs.
- DeepSWE v1.1: 63.4.
- AutomationBench v1.0.6: 48.8.

This makes it a strong candidate for structured tool use, connector flows, command UX, packaging scripts and repetitive cross-platform integration. Its Terminal-Bench 2.1 score is not comparable with Terminal-Bench 4.0/4.1 values from the other labs.

Assign:
- workflo command design/handlers and help UX against the approved CLI core interface.
- GitHub App client workflow and local repository connector.
- language/framework detection profiles and test command manifests.
- npm/pnpm/Bun packaging and native distribution.
- installer, upgrade and uninstall matrix.

Avoid:
- implementing a second CLI core/runtime;
- owning Firecracker host execution or security approval;
- broad control-plane database changes.

### MiniMax M3.1 Flash — sandbox security, privacy tests and automation QA

Why:
- Automation-Bench v1.0.6: 62.8, highest among the relevant five-model scores in the cited shared table.
- CyberGym: 82.2.
- DeepSWE v1.1: 73.7.
- Terminal-Bench 4.0: 38.1.

Assign:
- threat model and policy test coverage;
- sandbox adversarial fixture corpus;
- network, filesystem, process, resource, guest/host and teardown negative tests;
- test automation harness and failure injection;
- inference privacy test suite, outbound payload assertions and prompt-injection tests;
- review of the sandbox and runner boundary implemented by DeepSeek.

Avoid:
- self-certifying security;
- unrestricted live-target scanning;
- replacing Firecracker with another backend;
- writing broad runtime code in DeepSeek-owned paths without an approved patch boundary.

### Gemini 4 Hydrogen — frontend and browser workflow

Why:
- Google explicitly lists web development, iterative repository coding/debugging and fast agentic execution as intended uses.
- AutomationBench-AA: 76.1.
- OSWorld-2.1 offline subset: 77.6.
- Terminal-Bench 4.1 cheating-adjusted: 57.0.
- SWE-sweep: 13.5%.

Assign:
- dashboard information architecture, design system and component implementation;
- Projects, Runs, Run Detail, Runner, Evidence and Settings interfaces;
- browser-driven user-journey validation;
- accessibility, responsive behavior, visual regression and error/empty/loading states.

Avoid:
- fabricating run data;
- directly calling runner hosts;
- changing backend authorization to make a screen work;
- treating OSWorld as a measure of visual design quality.

### GPT-6 Luna — control-plane/backend and system implementation

Why:
- DeepSWE v1.1: 66.6% at max effort.
- OpenAI describes Luna's result as comparable to Opus/Fable at medium effort in that evaluation, with lower cost per task.
- OpenAI reports cost-efficient computer-use improvement, but no direct backend-specific leaderboard result for Luna in the cited release.

Assign:
- API contract design and OpenAPI source of truth;
- identity, organizations, team/workspace and RBAC;
- PostgreSQL persistence, RLS, durable outbox and lease semantics;
- Projects/Runs/Runner/Connectors/Evidence/Settings APIs;
- dashboard backend integration and operational controls;
- tenant-safe pagination, filtering, audit events and retention.

Avoid:
- unilateral changes to canonical lifecycle/receipt contracts;
- accepting a benchmark score as proof of tenant isolation;
- enabling a managed compute fleet under a zero-budget assumption;
- designing an API contract without tests and examples.

## 5. Primary sources and provenance

1. DeepSeek V4.1 Flash-1017 model card and technical report:  
   https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash-1017  
   Relevant: DeepSWE v1.1, Terminal-Bench 4.0, NL2Repo-Bench, Automation-Bench v1.0.6 and stated harness details.

2. MiniMax M3.1 Flash official model card:  
   https://huggingface.co/MiniMaxAI/MiniMax-M3.1-Flash  
   Relevant: Automation-Bench v1.0.6, Terminal-Bench 4.0, DeepSWE v1.1, CyberGym and evaluation notes.

3. Z.ai GLM-5.3-Flash official announcement:  
   https://z.ai/blog/glm-5.3-flash  
   Relevant: Terminal-Bench 2.1, DeepSWE v1.1, Toolathlon Verified and AutomationBench v1.0.6. Vendor-reported results.

4. Google DeepMind Gemini 4 Hydrogen model card:  
   https://deepmind.google/models/model-cards/gemini-4-hydrogen/  
   Relevant: SWE-sweep, Terminal-Bench 4.1, AutomationBench-AA, OSWorld-2.1 and intended usage including web development.

5. OpenAI GPT-6 Sol and Luna release:  
   https://openai.com/index/introducing-gpt-6-sol-and-luna/  
   Relevant: DeepSWE v1.1, computer-use positioning and cost-per-task comparison.

6. Independent AutomationBench measured-score index (secondary cross-check; lab-reported input values):  
   https://benchgap.net/b/automationbench/current

7. Independent Terminal-Bench 2.1 leaderboard context (secondary):  
   https://llmbenchmark.ai/benchmarks/terminal-bench-2-1

## 6. Workflo-specific calibration is mandatory

Before any agent receives broad write permissions:
- run a common repository audit task;
- run a small multi-file bug fix task;
- run one test-writing task;
- run one contract-preservation task;
- run specialization tasks matching the assigned domain;
- compare results on the same SHA, same tools, same tests and same budget class;
- score functional correctness, regression safety, scope discipline, test quality and maintainability;
- disqualify any attempt that leaks secrets/source, weakens a security gate or changes protected contracts without approval.

A benchmark is only a routing prior. The Workflo calibration result decides whether a model gets a given permission level.
