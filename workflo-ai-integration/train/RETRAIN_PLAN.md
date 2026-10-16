# Adapter re-train plan — target ≥ 84 % on every task

Status: **iteration 1 complete — token gate NOT yet met; more data required.**
The training/eval tooling is built and validated; three training recipes were
executed. Empirical results below replace the estimates in sections 2–4.

## 5a. Empirical results (held-out 4 examples, unpadded teacher-forced)

Evaluator: `train/eval_adapter.py` (joint tokenization, response-template
boundary, greedy generation for schema/gate rates). Verified sound: the same
probe measures 0.90 on training examples, so the eval gap is real
generalization behavior, not a measurement artifact.

| Run | Config | Token acc | Schema valid | Gates pass |
|---|---|---|---|---|
| reasoning iter1 | r32/a64/d0.05/lr2e-4/5ep, best-loss @ep1 | 0.806 | **100 %** | **100 %** |
| reasoning iter2 | r16/a32/d0.10/lr1e-4/8ep, best @ep2 | 0.808 | 100 % | 75 % |
| reasoning iter3 | r32/a64/d0.10/lr2e-4/8ep | 0.797 | 75 % | 75 % |
| reporting | r32/a64/d0.05/lr2e-4/5ep, best-loss @ep1 | 0.751 | **100 %** | **100 %** |

Findings:

1. **Token accuracy plateaus at ~0.75–0.81 regardless of recipe.** Rank,
   dropout, LR, and epoch-count changes moved held-out accuracy by < 0.02.
   With 36 training examples the model fits the training set (0.90) but
   cannot generalize to 0.84 — **data volume, not hyper-parameters, is the
   binding constraint** (as predicted in section 2).
2. **Regularization beyond d0.05 hurts the safety gates** (iter2/iter3
   lost 25 % gate pass rate). Iteration-1 config (r32/a64/d0.05/lr2e-4)
   is the only recipe that keeps schema+gates at 100 %.
3. trl's in-training `eval_mean_token_accuracy` (0.84–0.88) reads higher
   than the unpadded teacher-forced measurement on this hybrid
   linear-attention (Qwen3.5) architecture; the unpadded number is the
   conservative, trustworthy one.
4. Per the regression guard, the **frozen serving adapters remain
   deployed and untouched**; no GGUF conversion or manifest change was
   made for the experimental runs.

## 5b. Next lever: more data (before any further training run)

The 84 % token gate needs roughly double the per-task training data
(~70–80 train examples per task, i.e. ~80+ total authored per task). Steps 1–4
of the checklist below are done; step 5+ resumes after the dataset grows
again. All recipes/eval tooling are ready to re-run as-is.

## 1. Where we are (baseline)

Current frozen adapters (QLoRA rank 16, 3 epochs, 57 ChatML examples):

| Task | Token accuracy | Loss | vs. 84 % target |
|---|---|---|---|
| test-gen | 0.867 | 1.032 | **+2.7 % (meets target)** |
| reasoning | 0.810 | 1.520 | **−3.0 % (gap)** |
| reporting | 0.804 | 1.310 | **−3.6 % (gap)** |

These are *training-token* accuracies. The re-train must additionally prove
≥ 84 % on a **held-out** split so the number is honest, not memorization.

## 2. What is limiting accuracy

1. **Data volume.** 57 examples is small; reasoning and reporting have the
   most diverse output space (free-text strategy expressions, narrative
   summaries), so they saturate first. test-gen benefits from highly
   regular output (pytest files) and is already above target.
2. **Capacity.** rank 16 caps how much task style the adapter can absorb.
3. **No held-out eval.** Current numbers cannot rule out overfitting.

## 3. Data plan (prerequisite — do this first)

Expand `train/dataset_sources.py` from 57 → **120 examples**:

| Task | Current | Added | New total |
|---|---|---|---|
| test-gen | 20 | +20 (guard against forgetting; harder edge cases) | 40 |
| reasoning | 20 | +20 (tenant isolation, pagination, rate-limit, money, auth expiry variants) | 40 |
| reporting | 17 | +23 (multi-failure narratives, severity ordering, empty-findings, flaky-test framing) | 40 |

Authoring rules — unchanged and non-negotiable (enforced by
`validate_datasets.py` and `tests/test_dataset_contract_harness.py`):

- Every assistant payload must validate against the exact serving schemas
  (`WriteTestCall` / `ProposeInvariantCall` / `ReportNarrative`).
- Generated test bodies must pass `compile_check`; strategy/property
  expressions must pass `property_expr_check`.
- Reporting inputs contain only structured outcomes, never source code.
- System prompts stay byte-identical to `service_defaults.SYSTEM_PROMPTS`.

After authoring:

```bash
python train/validate_datasets.py   # must pass 120/120 before training
```

## 4. Training plan (per adapter; reasoning + reporting are the priority)

Hardware constraint: single RTX 4050 (6 GB VRAM). All settings keep the
QLoRA + NF4 + gradient-checkpointing configuration from `train_qlora.py`.

| Hyper-parameter | Baseline (frozen) | Re-train | Rationale |
|---|---|---|---|
| LoRA rank | 16 | **32** | Doubles task-style capacity for the two lagging tasks |
| LoRA alpha | 32 | **64** | Keep the standard 2× rank heuristic |
| Epochs | 3 | **5** | More data + held-out eval makes extra epochs safe |
| Learning rate | 2e-4 (cosine) | 2e-4 (cosine) | Proven stable at this scale |
| Warm-up | none | **10 % of steps** | Stabilizes early loss with rank-32 adapters |
| Batch / grad-accum | 1 / 1 | 1 / **2** | Effective batch 2 fits 6 GB and smooths gradients |
| Eval cadence | end only | **every epoch** on held-out split | Early-stop signal |

**Held-out split:** stratified 90/10 (36 train / 4 eval per task). The eval
examples are removed from training entirely. If VRAM or stability problems
appear at rank 32, fall back to rank 24 / alpha 48 rather than batch
changes (batch is the harder constraint at 6 GB).

Early-stop rule: stop when held-out token accuracy has not improved for
2 consecutive evals.

## 5. Acceptance gate (the 84 % benchmark)

An adapter is accepted only when **all three** hold on the held-out split:

1. Token accuracy ≥ **0.84**
2. Schema-validity rate = **100 %** (Pydantic validates every output)
3. Safety-gate pass rate = **100 %** (`compile_check` / `property_expr_check`)

Regression guard: test-gen's existing adapter is NOT re-trained unless its
own re-train also clears the gate — the frozen 0.867 artifact stays
deployable meanwhile. Adapters are independent files; upgrading one never
touches the others.

## 6. Post-training pipeline (unchanged mechanics, new digests)

```bash
# per re-trained adapter
python scripts/convert_peft_to_gguf.py --peft-dir train/out/<task>/final \
    --output serving/adapters/<task>.gguf

# regenerate + verify the frozen manifest (all four artifacts re-hashed)
python train/make_manifest.py
python scripts/verify_artifact_manifest.py serving/model-artifacts.json

# full contract + package regression
python -m pytest tests -q     # 57-example harness auto-picks up new counts? no — update EXPECTED_COUNTS
```

**Required code change when data grows:** update `EXPECTED_COUNTS` in
`tests/test_dataset_contract_harness.py` (and its 57-total assertion) to the
new 40/40/40 split — the harness intentionally hard-pins the authoritative
counts so silent dataset changes fail CI.

**Required ops follow-up:** the four SHA-256 values in the `p4-staging`
environment variables and any staged GGUFs must be refreshed after the
manifest is regenerated (the old digests become stale by design).

## 7. Execution checklist

```
[x] 1. Author +120 examples in dataset_sources.py, regenerate JSONL
[x] 2. validate_datasets.py -> 120/120
[x] 3. Update EXPECTED_COUNTS in test_dataset_contract_harness.py (40/40/40)
[x] 4. Full pytest suite green
[x] 5. Stratified 90/10 split; re-train reasoning adapter (3 recipes executed)
[x] 6. Eval vs gate -> NOT MET (0.797-0.808 < 0.84; see section 5a)
[x] 7. Reporting adapter trained + evaluated -> NOT MET (0.751 < 0.84;
       schema+gates 100 % with iter-1 config)
[ ] 8. Decide on test-gen re-train (optional; frozen one already passes)
[ ] 9. Convert -> manifest -> verify -> pytest (blocked on step 5b data)
[ ] 10. Refresh p4-staging vars + staged GGUFs; PR with new metrics table
```

## 8. Non-goals

- No base-model change (ChatML protocol freeze holds; swapping the base is
  a protocol change requiring a new acceptance run).
- No serving-side schema/prompt changes — training data must move toward
  the frozen serving contract, never the reverse.
- No hosted-LLM fallback work: the whole point of this cycle is removing
  the ChatGPT/Claude dependency for tool-calling/agentic tasks.
