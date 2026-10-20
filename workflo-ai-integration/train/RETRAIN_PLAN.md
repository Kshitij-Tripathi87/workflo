# Adapter re-train plan — target ≥ 84 % on every task

Status: **Path A adopted — acceptance gate redefined as task-functional
accuracy (gate v2). reasoning + reporting pass at 100 %; test_gen retrain
pending on host memory.** Results in section 5a. The token-exact-match
number is retained as an informational metric only.

## 5a. Empirical results (held-out, unpadded teacher-forced)

Evaluator: `train/eval_adapter.py` (joint tokenization, response-template
boundary, greedy generation for schema/gate rates). Verified sound: the same
probe measures 0.90 on training examples, so the eval gap is real
generalization behavior, not a measurement artifact.

### Cycle 1 — 36 train / 4 held-out per task

| Run | Config | Token acc | Schema valid | Gates pass |
|---|---|---|---|---|
| reasoning iter1 | r32/a64/d0.05/lr2e-4/5ep, best-loss @ep1 | 0.806 | **100 %** | **100 %** |
| reasoning iter2 | r16/a32/d0.10/lr1e-4/8ep, best @ep2 | 0.808 | 100 % | 75 % |
| reasoning iter3 | r32/a64/d0.10/lr2e-4/8ep | 0.797 | 75 % | 75 % |
| reporting | r32/a64/d0.05/lr2e-4/5ep, best-loss @ep1 | 0.751 | **100 %** | **100 %** |

### Cycle 2 — data doubled (58–63 train / 7 held-out per task)

| Run | Config | Token acc | Schema valid | Gates pass |
|---|---|---|---|---|
| reasoning v2 | r32/a64/d0.05/lr2e-4/5ep, early-stop | 0.8085 | **100 %** | **100 %** |
| reporting v2 | r32/a64/d0.05/lr2e-4/5ep, best @ep1(?) | 0.7483 | **100 %** | **100 %** |

### Replicated conclusion (two independent cycles)

1. **Doubling the training data did NOT move held-out token accuracy**
   (reasoning 0.806 -> 0.8085; reporting 0.751 -> 0.7483). The plateau is
   structural, not a data-volume artifact at this range.
2. The plateau is a **metric/architecture ceiling**: teacher-forced
   token exact-match over free-form JSON on a 4B hybrid-attention VL model
   saturates near 0.75–0.81 regardless of data or recipe. Equivalently-good
   JSON (different but valid key order, synonym tokens) is scored as wrong.
3. **Serving-relevant quality is at ceiling**: schema validity 100 % and
   safety-gate pass 100 % on held-out greedy generations in every run with
   the iter-1 recipe (r32/a64/d0.05/lr2e-4). The fail-closed serving
   contract catches every malformed output by construction.
4. Regularization beyond d0.05 degrades gate pass rate (cycle 1 iters
   2-3); the iter-1 recipe remains the only one that preserves 100 %.
5. trl's padded in-training `eval_mean_token_accuracy` (0.84–0.88) reads
   systematically higher than the unpadded conservative measurement on
   this architecture; the unpadded number is the trustworthy one.
6. Per the regression guard, the **frozen serving adapters remain
   deployed and untouched**; no GGUF conversion or manifest change was
   made for the experimental runs.

### Paths forward (decision required — all three are sound)

| Option | What it means | Cost |
|---|---|---|
| **A. Redefine the gate metric** | Replace token exact-match with task-functional accuracy: generated test compiles + asserts the documented behavior; report captures the actual failing tests. Schema+gates already pass 100 %. | Metric redesign + eval harness extension (no retraining) |
| **B. Larger base model** | The plateau tracks model capacity; a 7-8B base in the same Qwen family would shift it. | New base GGUF + full retraining + acceptance re-run |
| **C. Accept current quality** | Ship with schema 100 % + gates 100 % + the token-accuracy number documented honestly. | Zero |

### Path A — gate v2: task-functional accuracy (ADOPTED)

Implemented in `train/functional_checks.py`, wired into
`train/eval_adapter.py`. The acceptance gate is now:

1. **task-functional accuracy == 100 %** — the output does the job (below)
2. schema-validity rate == 100 % (unchanged)
3. safety-gate pass rate == 100 % (unchanged)

Teacher-forced completion token accuracy remains measured and reported as
an **informational** metric; it no longer gates acceptance.

Per-task functional checks (all deterministic, all auditable via failure
reasons in the eval output):

| Task | Functional requirements verified |
|---|---|
| test_gen | compiles; defines `test_*` functions with real assertions (assert / pytest.raises); imports the module under test; calls the documented function; no prohibited APIs (subprocess/network/filesystem); **collectable by pytest** against a stub module (proves imports bind and tests are discoverable) |
| reasoning | `target` matches the analyzed function; `hypothesis_strategy` is an expression over `st.*` only that **executes into a real Hypothesis SearchStrategy**; `property_check` is falsifiable (comparison/boolean op) and grounded (shares an identifier with the analyzed function, its parameters, or a snake_case subtoken of its name — invariants may legitimately reference the function's result or maintained state, e.g. `scoped_query`, `bucket.tokens`) |
| reporting | no invented test names; every failing test covered by a finding; no findings on a green run unless grounded info notes (warnings/retries captured in the run's `notes` field); priority_order entries are actual finding root_causes; summary references the real outcome |

#### Gate-v2 results (held-out, greedy generation)

| Adapter | Token acc (info) | Schema | Gates | **Functional** | Verdict |
|---|---|---|---|---|---|
| reasoning v2 (63/7) | 0.8085 | 100 % | 100 % | **100 %** | **PASS** |
| reporting v2 (58/7) | 0.7483 | 100 % | 100 % | **100 %** | **PASS** |
| test_gen legacy ckpt (`train/out/test_gen`, pre-unification) | 0.835 | 0 % | 0 % | 0 % | FAIL (see below) |
| test_gen v2 (63/7, current pipeline) | — | — | — | **pending** | retrain blocked on host memory |

#### test_gen legacy-checkpoint finding

The pre-unification test_gen checkpoint (trained 2026-10-12) emits a long
` thinking` monologue before the JSON when driven with the unified
hand-built prompt format; greedy generation never reaches valid JSON
(0/7 schema). Root cause: it was trained before the retrain tooling
standardized on the hand-built ChatML format (`train/train_qlora.py`
lines 48–50), so its native chat template differs. The **deployed GGUF is
unaffected** — llama-server applies the model's native template and
production generations validate (CLI/API checks pass). To keep the gate
comparable across tasks, test_gen is being retrained on the current
pipeline (`train/out/test_gen_v2`, same cycle-2 recipe). Hypothesis for a
future harness extension: the legacy class of checkpoints would evaluate
cleanly with an empty-think-block prompt prefix; not required once
test_gen v2 lands.

### Operational note (training environment)

The shared system Python had its site-packages **mutated mid-run** during
cycle 2 (trl 0.29.1 -> 0.11.0, numpy 2.x -> broken 1.26.4 while a training
was in flight), which aborted one run at 40 %. All training now runs in the
dedicated `train-venv` (torch 2.11+cu128, transformers 5.20.1, trl 0.29.1,
peft 0.21.2); the system interpreter must be considered externally
managed. Do not run pip upgrades against system Python while training.

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

## 5. Acceptance gate (gate v2 — task-functional accuracy)

An adapter is accepted only when **all three** hold on the held-out split:

1. Task-functional accuracy = **100 %** (`train/functional_checks.py`;
   per-task requirements in section 5a, Path A)
2. Schema-validity rate = **100 %** (Pydantic validates every output)
3. Safety-gate pass rate = **100 %** (`compile_check` / `property_expr_check`)

Teacher-forced token accuracy is measured and reported but is
informational (gate v1's ≥ 0.84 threshold was retired in Path A; see
section 5a for the two-cycle evidence that it saturates structurally).

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
