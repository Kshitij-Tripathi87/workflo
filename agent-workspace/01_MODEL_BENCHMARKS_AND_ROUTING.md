# Model benchmark evidence and task routing

**Assessment date:** 2026-11-27  
**Purpose:** select which of the five available development agents should perform each class of Workflo engineering task. This is not Workflo's future customer-facing model-provider architecture.

## 1. Exact model identities

| User-provided name | Normalized model identity |
|---|---|
| Gemini 4 Hydrogen | Google DeepMind Gemini 4 Hydrogen |
| DeepSeek V4.1 Flash 1017 | DeepSeek-V4.1-Flash-1017 |
| MiniMax M3.1 | MiniMax M3.1 Flash (use this plan only when the exact Flash model is selected) |
| GLM-5.33 Flash | GLM-5.3-Flash; verify the actual UI/provider identifier before use |
| GPT-6 Luna | OpenAI GPT-6 Luna |

Do not transfer results between a base model and its Flash variant, between a release and a preview, or between model versions.

## 2. Benchmark evidence

The scores below are model/provider-published or benchmark-published results. They were not all measured in one shared run. A result from one benchmark version or harness is not interchangeable with a result from another.

| Model | Benchmark | Published result | Source and interpretation |
|---|---|---:|---|
| Gemini 4 Hydrogen | SWE-sweep | 13.5% | Google DeepMind model card; agentic coding |
| Gemini 4 Hydrogen | Terminal-Bench 4.1 | 57.0% | Google DeepMind model card; not directly comparable with Terminal-Bench 4.0 |
| Gemini 4 Hydrogen | AutomationBench-AA | 76.1% | Google DeepMind model card; strongest planning/workflow signal among its listed comparisons |
| Gemini 4 Hydrogen | Agents' Last Exam v1.1 | 71.6 | Google DeepMind model card; knowledge-work score, not coding pass rate |
| Gemini 4 Hydrogen | OSWorld-2.1 offline | 77.6% | Google DeepMind model card; computer-use capability |
| DeepSeek-V4.1-Flash-1017 | Terminal-Bench 4.0 | 42.3% | DeepSeek model card comparison |
| DeepSeek-V4.1-Flash-1017 | DeepSWE v1.1 | 77.0% | DeepSeek model card comparison |
| DeepSeek-V4.1-Flash-1017 | NL2Repo-Bench | 68.2% | DeepSeek model card comparison |
| DeepSeek-V4.1-Flash-1017 | Automation-Bench v1.0.6 | 60.5% | DeepSeek model card comparison |
| DeepSeek-V4.1-Flash-1017 | Agents' Last Exam | 35.4 | DeepSeek model card comparison |
| MiniMax M3.1 Flash | DeepSWE v1.1 | 73.7% | MiniMax official release information |
| MiniMax M3.1 Flash | CyberGym | 82% | MiniMax official release information; assisted security analysis, not security approval |
| MiniMax M3.1 Flash | OSWorld 2.0 | 61.7 | MiniMax official release information |
| MiniMax M3.1 Flash | AutomationBench-AA | 62.2 | MiniMax official integration guide; do not conflate with every AutomationBench variant |
| MiniMax M3.1 Flash | Automation-Bench v1.0.6 | 62.8 | Published comparison on the model card; benchmark capture/variant differs from the AA result above |
| GLM-5.3-Flash | Terminal-Bench 2.1 | 84.3% | Z.ai model page; version differs from Terminal-Bench 4.0/4.1 |
| GLM-5.3-Flash | DeepSWE v1.1 | 63.4% | Z.ai model page |
| GLM-5.3-Flash | NL2Repo | 56.3 | Z.ai model page |
| GLM-5.3-Flash | AutomationBench v1.0.6 | 48.8 | Z.ai model page |
| GLM-5.3-Flash | Toolathlon Verified | 78.4 | Z.ai model page; tool-use evaluation |
| GPT-6 Luna | DeepSWE v1.1, max effort | 66.6% | OpenAI's GPT-6 Sol/Luna announcement |
| GPT-6 Luna | DeepSWE v1.1, Codex CLI multi-run evaluation | 62.54% (212/339) | NVIDIA Switchyard report; three runs, different harness/configuration from the vendor result |

### Primary sources

- Google DeepMind Gemini 4 Hydrogen model card: https://deepmind.google/models/model-cards/gemini-4-hydrogen/
- Google DeepMind evaluation report: https://storage.googleapis.com/deepmind-media/gemini/gemini_4_hydrogen_model_evaluation.pdf
- DeepSeek-V4.1-Flash-1017 model card and technical report: https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash-1017
- DeepSeek API release notes: https://api-docs.deepseek.com/updates/
- MiniMax M3.1 Flash release: https://code.minimax.io/tools/m3.1-flash
- MiniMax M3.1 Flash model card: https://huggingface.co/MiniMaxAI/MiniMax-M3.1-Flash
- Z.ai GLM-5.3-Flash benchmark report: https://z.ai/blog/glm-5.3-flash
- OpenAI GPT-6 Sol and Luna release: https://openai.com/index/introducing-gpt-6-sol-and-luna/
- NVIDIA Switchyard benchmark methodology/results: https://nvidia-nemo.github.io/Switchyard/benchmarks/

## 3. What the results justify

### DeepSeek-V4.1-Flash-1017 — repository and systems implementation

It is the default implementation lead for the runtime and backend because its cited comparison is strong on repository-level work (DeepSWE 77.0%), codebase task discovery (NL2Repo 68.2%) and shell/terminal work (Terminal-Bench 4.0 42.3%). These are the closest available signals for implementing Workflo's Python services, worker and Linux integration. It must still work from a scoped contract and pass tests.

### Gemini 4 Hydrogen — architecture and high-level engineering analysis

Its published SWE-sweep, knowledge-work and AutomationBench-AA scores support assigning it cross-document synthesis, system decomposition, architecture proposals, long-horizon planning and complex review. Its Terminal-Bench 4.1 number is not evidence that it leads on Terminal-Bench 4.0. It is an architect and reviewer, not an unchecked authority.

### MiniMax M3.1 Flash — automation and integration

The published AutomationBench results and official multi-step workflow examples support GitHub/CI/release automation, cross-document integration work, build and packaging workflows. The published CyberGym result is a reason to request security-analysis support, not to delegate final security decisions to the model. No secret access or security sign-off.

### GLM-5.3-Flash — bounded implementation and developer experience

The vendor reports useful terminal, DeepSWE, Toolathlon and vision results. Relative to the other exact-model evidence available, it is best used for small, independent, reviewable units: docs, CLI messages and help, config scaffolding, frontend components after the dashboard gate, fixtures and straightforward integrations. Do not infer its results from the non-Flash GLM-5.3 model.

### GPT-6 Luna — independent QA and review

OpenAI reports 66.6% on DeepSWE v1.1 at max effort. This is useful repository-level engineering capability, but the cited DeepSeek 77.0% result is stronger in its own published evaluation. Luna is assigned to challenging specifications, test design, regression analysis and independent review to reduce same-model blind spots. It does not determine truth: test execution and security gates do.

## 4. Routing matrix

| Task type | Primary | Secondary / reviewer |
|---|---|---|
| Architecture, roadmap, ADR proposal | Gemini 4 Hydrogen | GPT-6 Luna |
| Repository-wide impact analysis | Gemini 4 Hydrogen | DeepSeek V4.1 Flash-1017 |
| Core Python/runtime implementation | DeepSeek V4.1 Flash-1017 | GPT-6 Luna |
| Linux process/isolation implementation | DeepSeek V4.1 Flash-1017 | Gemini read-only + human |
| Firecracker host / guest integration | DeepSeek V4.1 Flash-1017 | GPT-6 Luna tests; Gemini design review |
| Control-plane orchestration integration | MiniMax M3.1 Flash | DeepSeek or GPT-6 Luna |
| GitHub Actions, CI/CD, packaging | MiniMax M3.1 Flash | GPT-6 Luna |
| Test specifications / regression suites | GPT-6 Luna | Gemini review |
| Independent code review | GPT-6 Luna | Gemini for architecture impact |
| CLI UX, error text, documentation | GLM-5.3-Flash | GPT-6 Luna |
| Dashboard UI after evidence-workflow stabilization | GLM-5.3-Flash | Gemini visual/design review |
| Release checklist and release automation | MiniMax M3.1 Flash | GPT-6 Luna |
| Security threat model | Gemini 4 Hydrogen | GPT-6 Luna and human |
| Security code changes | DeepSeek only on scoped ticket | Independent test/review; human acceptance |

## 5. Evidence-quality rules

- A benchmark score is not a probability that a model will complete a Workflo task.
- The source, release identifier, benchmark version, harness, reasoning effort and number of runs must accompany a benchmark claim.
- Do not average incomparable scores into one synthetic ranking.
- The vendor's own benchmark result is a useful prior, not an independent guarantee.
- Do not cite terminal benchmark 2.1 results as if they were terminal benchmark 4.0/4.1.
- Do not use GLM-5.3 (base) scores as GLM-5.3-Flash scores.
- Do not use DeepSeek V4.1 Flash scores for the 1017 checkpoint when the 1017 result is specifically available.
- Re-run the internal benchmark after any model alias, model version, agent harness or tool-permission change.

## 6. Workflo-specific model bake-off

Before making this routing permanent, compare all five exact models on a fixed 40-task dataset: 8 repository navigation/impact tasks, 8 implementation tasks, 8 debugging/terminal tasks, 8 test/QA tasks and 8 architecture/security-analysis tasks.

Protocol:
- Use the same base commit, task contract, allowed paths, time budget and tool permissions.
- Run three attempts per task/model where quotas permit.
- Hide acceptance tests from the model.
- Score task completion, tests passed, regression rate, scope violations, unsupported claims, security-policy violations and human review effort.
- Record model identifier, reasoning effort, harness version, run ID, time and token/quota use.
- A critical policy violation is a hard failure, not a score deduction.
- Publish raw task outcomes and aggregate results; do not report only the winning score.

Until that benchmark is completed, treat this routing as the initial evidence-based allocation, not a proven Workflo leaderboard.
