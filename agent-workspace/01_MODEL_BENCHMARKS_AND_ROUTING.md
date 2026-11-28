# Development-agent benchmark evidence and task routing

**Assessment date:** 2026-11-28  
**Scope:** the five models used to build Workflo. These are not customer-facing Workflo QA models. Workflo does not supply API models or API credits.

## 1. Exact identities

| User-provided name | Normalized identity | Rule |
|---|---|---|
| Gemini 4 Hydrogen | Google DeepMind Gemini 4 Hydrogen | Do not transfer results from another Gemini 4 variant |
| DeepSeek V4.1 Flash-1017 | deepseek-ai/DeepSeek-V4.1-Flash-1017 | Keep this checkpoint distinct from other V4.1 Flash snapshots |
| MiniMax M3.1 | MiniMax M3.1 Flash | This plan assumes the exact Flash variant |
| GLM-5.3 Flash (user typed 5.33) | GLM-5.3-Flash | Never substitute base GLM-5.3 scores |
| GPT-6 Luna | GPT-6 Luna | Use Luna-specific evidence, not Sol evidence |

Always record the actual model identifier used by the coding harness. A marketing name or alias is not enough for a reproducible internal benchmark.

## 2. Published benchmark snapshot

These are model/vendor-published scores drawn from different harnesses and dates. They are not one controlled head-to-head. In particular, Terminal-Bench 2.1, 4.0 and 4.1 are different benchmark versions and must not be combined into a single ranking.

| Model | Evaluation | Published result | Practical signal |
|---|---|---:|---|
| Gemini 4 Hydrogen | SWE-sweep | 13.5% | Agentic software task signal |
| Gemini 4 Hydrogen | Terminal-Bench 4.1 | 57.0% | Terminal work; version 4.1 only |
| Gemini 4 Hydrogen | AutomationBench-AA | 76.1% | Multi-step automation |
| Gemini 4 Hydrogen | Agents' Last Exam v1.1 | 71.6 | Broad knowledge-work reasoning, not coding pass rate |
| Gemini 4 Hydrogen | OSWorld-2.1 offline | 77.6% | Computer-use workflow |
| DeepSeek V4.1 Flash-1017 | Terminal-Bench 4.0 | 42.3% | Terminal and repository work |
| DeepSeek V4.1 Flash-1017 | DeepSWE v1.1 | 77.0% | Repository-level software engineering |
| DeepSeek V4.1 Flash-1017 | NL2Repo-Bench | 68.2% | Repository task understanding |
| DeepSeek V4.1 Flash-1017 | Automation-Bench v1.0.6 | 60.5% | Automation workflow |
| DeepSeek V4.1 Flash-1017 | Agents' Last Exam | 35.4 | Separate evaluation; not comparable to Gemini's v1.1 row |
| MiniMax M3.1 Flash | Terminal-Bench 4.0 | 38.1% | Terminal execution |
| MiniMax M3.1 Flash | DeepSWE v1.1 | 73.7% | Repository-level coding |
| MiniMax M3.1 Flash | CyberGym | 82.2% | Security-analysis benchmark; not security approval |
| MiniMax M3.1 Flash | OSWorld 2.0 | 61.7 | Computer-use workflow |
| MiniMax M3.1 Flash | Automation-Bench v1.0.6 | 62.8 | Published automation comparison |
| MiniMax M3.1 Flash | AutomationBench-AA | 62.2 | Different published automation variant; do not conflate |
| GLM-5.3-Flash | Terminal-Bench 2.1 | 84.3% | Tool/terminal signal; not comparable with 4.0/4.1 |
| GLM-5.3-Flash | DeepSWE v1.1 | 63.4% | Repository-level coding |
| GLM-5.3-Flash | NL2Repo | 56.3 | Repository task signal |
| GLM-5.3-Flash | AutomationBench v1.0.6 | 48.8 | Workflow automation |
| GLM-5.3-Flash | Toolathlon Verified | 78.4 | Tool-use performance |
| GLM-5.3-Flash | OSWorld 2.0 | 59.1 | Computer-use workflow |
| GPT-6 Luna | DeepSWE v1.1, max effort | 66.6% | OpenAI-reported repository coding result |

### Primary sources

- Gemini 4 Hydrogen model card: https://deepmind.google/models/model-cards/gemini-4-hydrogen/
- DeepSeek V4.1 Flash-1017 model card: https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash-1017
- MiniMax M3.1 Flash release/model card: https://code.minimax.io/tools/m3.1-flash and https://build.nvidia.com/minimaxai/minimax-m3.1-flash/modelcard
- GLM-5.3-Flash benchmark report: https://z.ai/blog/glm-5.3-flash
- OpenAI GPT-6 Sol/Luna release: https://openai.com/index/introducing-gpt-6-sol-and-luna/
- GPT-6 Luna model documentation: https://developers.openai.com/api/docs/models/gpt-6-luna

## 3. What the benchmark evidence justifies

### DeepSeek V4.1 Flash-1017 — systems implementation lead

The 77.0% DeepSWE v1.1, 68.2 NL2Repo and 42.3 Terminal-Bench 4.0 results support assigning the most terminal- and codebase-intensive implementation stream to DeepSeek. Its remit is Rust CLI and client/runtime integration, typed protocol handling, process/daemon behavior and carefully scoped Linux runner/guest tasks. Its benchmark result does not permit autonomous security decisions or broad unrestricted repository writes.

### Gemini 4 Hydrogen — architect and system integrator

The AutomationBench-AA, Agents' Last Exam and OSWorld results provide useful signals for multi-step synthesis, architecture and tool-driven planning. Gemini owns the repository/dependency map, architecture options, ADR decision packs, cross-platform runner design, API/data-flow reviews and integration analysis. It does not silently ratify ADRs or become a second implementation owner.

### MiniMax M3.1 Flash — integrations and release automation

The published automation, OSWorld and repository-coding results support GitHub workflow integration, private-source lifecycle, webhook/check-run automation, CI, native packaging and release manifests. CyberGym is a benchmark signal for security-analysis assistance, not proof of security or permission to approve Gate B.

### GPT-6 Luna — API design, test engineering and independent verification

The DeepSWE v1.1 result at max effort supports serious repository and contract work. Luna owns OpenAPI design, user/workspace/role model, cross-tenant negative tests, gate aggregation contract and independent review of the other agents. It must reproduce evidence; it does not replace CI or human acceptance.

### GLM-5.3 Flash — developer experience and bounded frontend work

The Toolathlon and repository-level results support bounded tool tasks, help/diagnostic UX, examples, install documentation and later dashboard components. The 84.3 Terminal-Bench 2.1 result is version-specific; it does not outrank or compare directly with other models' Terminal-Bench 4.0/4.1 results. GLM does not own the canonical API, runtime or security boundary.

## 4. Routing matrix

| Task class | Primary | Independent reviewer |
|---|---|---|
| Architecture, ADR proposal, dependency map | Gemini | GPT-6 |
| Rust-vs-Go decision criteria and system design | Gemini | GPT-6 |
| Rust CLI and native runtime | DeepSeek | GPT-6; Gemini architecture review |
| RunSpec and runner protocol implementation | DeepSeek | GPT-6 |
| Firecracker/KVM narrow implementation tasks | DeepSeek with explicit ticket | GPT-6 adversarial tests, Gemini design review, human owner |
| GitHub App/private source/PR checks | MiniMax | GPT-6 |
| CI, npm wrapper, native package and release automation | MiniMax | GPT-6 |
| OpenAPI, accounts, workspace and permissions | GPT-6 | Gemini |
| Tenant isolation and contract test suites | GPT-6 | Gemini plus CI |
| CLI copy, diagnostics, docs and examples | GLM | GPT-6 checks behavior |
| Dashboard IA/prototype | GLM | Gemini |
| Dashboard implementation after API gate | GLM | GPT-6 contract review |
| Security threat/data-flow model | Gemini | GPT-6 and human |
| Gate outcome model, regression and acceptance tests | GPT-6 | Gemini |
| Product security signoff | Human owner with independent evidence | No model self-approval |

## 5. Workflo-specific bake-off before permanent routing

Vendor scores are priors. Run an internal benchmark against the same exact commit and harness:
- 8 repository navigation and impact tasks;
- 8 implementation tasks across Rust/Python/TypeScript;
- 8 terminal debugging tasks;
- 8 test design and failure-analysis tasks;
- 8 architecture/privacy/security reasoning tasks.

Use the same task prompt, context size, tools, permissions, time limit, branch/base SHA and hidden acceptance tests. Run at least three attempts per task where quota permits. Record model ID, effort setting, harness version, command transcript, exit codes, completion, tests passed, regression, scope violation, unsupported claim, policy violation and reviewer effort.

A critical privacy, security or scope violation is a hard failure, not a small score penalty. Report category scores, variance and raw failures. Do not calculate a blended score that hides a critical violation. Repeat when the model version or harness changes.

## 6. Evidence limitations

- Vendor/model-card scores are not necessarily independently audited.
- Different task sets, pass@k methods, judging setups and agent harnesses are not interchangeable.
- Terminal-Bench 2.1, 4.0 and 4.1 must not be directly ranked together.
- Agent benchmark results do not measure Workflo path discipline, privacy compliance, reliability under its tool policy or security-boundary correctness.
- Do not infer results from a base model for a Flash model.
- A benchmark score never replaces task-level acceptance tests.
