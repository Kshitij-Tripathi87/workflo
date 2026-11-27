# Workflo Agent Model Calibration Protocol

**Purpose:** determine whether the five available models perform well on Workflo's actual engineering tasks before routing high-risk implementation work.  
**Run window:** first 48 hours of the 30-day programme.  
**Planning date:** 27 November 2026.

## 1. Why this is required

Published benchmark results are useful priors, not Workflo-specific accuracy measurements.

The five models report scores on different tasks, versions, tool harnesses, reasoning settings and evaluation protocols. For example:

- DeepSeek V4.1 Flash-1017 reports DeepSWE v1.1 using Mini-SWE-V2 and Terminal-Bench 4.0 using Claude Code.
- MiniMax publishes DeepSWE v1.1 and CyberGym results in its M3.1 Flash GA material.
- GLM-5.3-Flash reports Toolathlon Verified and Terminal Bench 2.1, not Terminal-Bench 4.1.
- Gemini 4 Hydrogen reports SWE-sweep and Terminal-Bench 4.1 plus AutomationBench-AA and OSWorld-2.1.
- GPT-6 Luna reports DeepSWE v1.1 at max effort.

Do not turn these into a single ranking. The purpose of this protocol is to validate the expected task fit using the same Workflo repo state and acceptance harness.

## 2. Models and initial routing hypotheses

| Model | Initial task hypothesis | Evidence to test |
|---|---|---|
| DeepSeek V4.1 Flash-1017 | Complex Python/control-plane/runner implementation and multi-file debugging | Can it make a bounded implementation that passes Workflo integration tests without changing trust contracts? |
| MiniMax M3.1 Flash | Privacy/security review, inference hardening and adversarial test construction | Does it find reproducible boundary violations and produce correct negative tests without false-positive claims? |
| GLM-5.3-Flash | CLI workflows, connector/API integration and tool orchestration | Can it implement typed client/server interactions, retries and permission edge cases correctly? |
| Gemini 4 Hydrogen | Dashboard flows, UI implementation and browser validation | Can it map the real APIs correctly and produce accessible, reliable user journeys without fabricated state? |
| GPT-6 Luna | Cross-system tests, contract parity, regression triage and CI/release automation | Can it construct tests that catch actual defects and distinguish mocked results from real release evidence? |

These are routing hypotheses. Reassign only when internal evidence justifies it.

## 3. Evaluation task set

Use **12–20 small, representative tasks**, not broad open-ended prompts. Keep tasks bounded to a few files and a clear acceptance test.

Minimum task classes:

1. CLI: add one safe argument/config behavior with validation and tests.
2. CLI/GitHub: implement a client-side permission/expiry edge case against a frozen API contract.
3. Control plane: fix a deterministic dispatch/idempotency defect using existing contracts.
4. Runner: implement a small isolated lifecycle fix or test in a mocked host fixture; do not run an unqualified live host.
5. Inference: detect and block a synthetic source/secret payload before an outbound request.
6. Inference: validate a malformed or unauthorized model tool plan.
7. Security: analyze a seeded vulnerability and provide a minimal reproducer plus a negative test.
8. Dashboard: implement a small run-state component using actual canonical fixture schemas.
9. Dashboard: fix loading/error/partial state and verify keyboard interaction.
10. QA: produce a regression test for a seeded bug and show that it fails before the fix and passes after.
11. Contracts: detect a deliberate TypeScript/Python schema mismatch.
12. Release: identify a deliberately skipped real-infrastructure gate and prevent it from being reported as passed.

At least two tasks should be common to all models (for example, a small multi-file bug fix and a contract/regression task). The remaining tasks should reflect each model's assigned workstream.

Never use customer source, production credentials or live infrastructure secrets in the evaluation corpus. Use a fixed synthetic fixture and a disposable branch.

## 4. Controlled execution conditions

For each run, record:

- exact provider model ID/version and date;
- reasoning/effort setting;
- agent harness and version;
- tools and permissions available;
- system/developer prompt version;
- repository base SHA;
- task and acceptance-test IDs;
- maximum turns, token/output budget and wall-clock limit;
- input/output tokens or provider usage if exposed;
- elapsed time and provider cost if exposed;
- final changed-file list and diff;
- test command output and exit status.

Keep the same task statement, repository base, tests and tool permissions for models compared on a common task. Use each model's appropriate supported effort setting; do not pretend provider-specific effort values are identical. Run each task in an isolated worktree.

No model may inspect another model's attempt before completing its own run. No model may see expected patch content.

## 5. Hard acceptance gates

The score is **not** a weighted average if a hard gate fails. Mark the attempt rejected when any of these occur:

- required tests fail or are skipped without an approved reason;
- the patch changes files outside the assigned scope without a written reason;
- canonical lifecycle/receipt/policy contracts are modified without approval;
- secrets or source content are copied into prompts, logs or outbound payloads contrary to policy;
- an execution or security boundary is weakened;
- tests are removed, weakened or bypassed to get green CI;
- generated output claims real KVM/model acceptance when only mocks ran;
- the patch cannot be reproduced from a clean checkout.

A critical privacy/security violation disqualifies the attempt regardless of its code score.

## 6. Scoring after hard gates pass

Score each attempt from 0 to 100:

| Dimension | Weight | Evaluation |
|---|---:|---|
| Functional correctness | 40 | Acceptance tests pass; behavior matches task contract |
| Regression safety | 20 | Existing targeted tests and adjacent workflows still pass |
| Contract and scope discipline | 15 | Correct schema/API use; no unrelated or unauthorized changes |
| Test quality | 15 | Tests fail on the seeded defect, pass on the correct fix and cover negatives |
| Maintainability | 10 | Readability, focused diff, error handling and compatibility |

Use two reviewers who did not author the patch. One must be a human for security-sensitive work. GPT-6 Luna may prepare review notes, but cannot be its own independent verifier.

Record score, failed tests, defects introduced, review findings, tokens/cost and latency. Efficiency is a tie-breaker after correctness and safety, never a substitute.

## 7. Routing decision

After the calibration:

- Keep the initial ownership mapping where the model passes its specialization tasks.
- Route high-impact work only to models that pass the exact relevant task class.
- Use a second agent as reviewer only if it has a separate worktree and has not seen the implementation reasoning before the review task.
- Any task involving Firecracker, guest/host authority, tenant isolation, secrets or source privacy requires human review and real acceptance tests regardless of score.
- If a model fails a specialization, downgrade it to documentation, test scaffolding or low-risk implementation until it passes a focused retest.

Do not average away a failure in security or contract correctness.

## 8. Recalibration triggers

Re-run relevant tasks when:

- provider changes model version or routing;
- prompt, tool harness or agent runtime changes materially;
- a model repeatedly creates regressions;
- the repo architecture or shared contracts change materially;
- a model is assigned a new high-risk task class.

## 9. Output artifact

GPT-6 Luna maintains `docs/agent-workplans/model-calibration-results.md` after the actual runs. The report must include raw run metadata, test results, reviewer decisions, routing changes and unresolved limitations. Do not invent missing usage/cost values.

A calibration report is not a security certification. It is evidence about task fit under the tested conditions only.
