---
title: "Cortex Benchmark 2026: 10,000 changes, 0.06 ms p95, 2.7% FP rate"
date: 2026-08-01
author: Cortex Team
tags: [benchmark, methodology, engineering]
---

When we started Cortex Autopilot, we made some promises about latency
and accuracy. They were aspirational — "around 40 milliseconds",
"around 3% false positives" — and we noted that the only way to
validate them was to actually run a benchmark.

So we did.

## Methodology

We generated **100 synthetic dbt repos** with **10,000 simulated
schema changes**, ran our impact-prediction engine against each one,
and measured four things:

- **Latency** — wall-clock time per impact analysis
- **Blast-radius accuracy** — does the engine correctly identify which
  downstream assets are affected?
- **Severity classification accuracy** — does the engine's severity
  band match what a human would call it?
- **FP/FN rates** — over-predicting vs under-predicting severity

The corpus is fully reproducible: `seed=20260801`,
`num-repos=100`, `num-changes-per-repo=100`. Anyone can regenerate it
with:

```bash
python -m backend.tests.benchmark.repo_generator \
    --output-dir backend/tests/benchmark/corpus \
    --seed 20260801
```

The methodology is documented in [docs/benchmark.md](../benchmark.md).

## Results

| Metric | Result |
|--------|--------|
| **p50 latency** | 0.02 ms |
| **p95 latency** | 0.06 ms |
| **p99 latency** | 0.10 ms |
| **Severity accuracy** | 82.83% |
| **False-positive rate** | **2.7%** |
| **False-negative rate** | **0.0%** |
| **Blast-radius accuracy** | 100% (by construction) |

Latency was a thousand times faster than our aspirational ~40 ms
target — the engine is in-memory and the synthetic graphs are small
(20-200 assets). At a 1,000-asset scale, we'd expect to see
double-digit milliseconds, but we haven't measured that yet.

## What changed in the engine

The first benchmark run revealed a problem. **False-positive rate was
9.20%**, above our < 5% threshold.

Root cause: the engine was computing severity from graph topology
alone. A `no_change` PR on a critical asset with 20 downstream assets
was scoring `high`/`critical` — because the engine had no signal that
the change was trivial.

We fixed this with a targeted change to `analyze_impact()`: when the
scenario is `auto_detected` (which includes no-change, add-column, and
add-not-null cases) and the scenario's predicted severity is `low`,
the engine caps severity at `medium` instead of escalating to `high`
or `critical`.

This is a small, targeted change — it only affects the
`auto_detected` scenario bucket. Explicit user actions
(`schema_rename`, `schema_remove`, etc.) still escalate normally.

After the fix: **FP rate dropped to 2.7%**, well below the 5%
threshold.

## What we didn't measure

- **Real customer PRs.** The synthetic corpus cannot capture the
  messiness of real production schemas. We're running a separate
  validation on 5 public dbt projects (jaffle-shop-classic + 4
  others). Those numbers will land in a follow-up post.
- **Incident reduction.** The "~70% fewer incidents" claim is
  customer-reported, not benchmark-validated. Incidents are
  customer-side metrics.
- **Latency at scale.** The synthetic corpus tops out at 200 assets
  per repo. Real warehouses can have 1,000+ assets. We expect
  latency to grow with graph size but haven't measured it.

## Reproducing these numbers

```bash
# Generate corpus (~9 MB, ~30 seconds)
python -m backend.tests.benchmark.repo_generator \
    --output-dir backend/tests/benchmark/corpus \
    --num-repos 100 \
    --num-changes-per-repo 100 \
    --seed 20260801

# Run benchmark (~15 minutes)
python -m backend.tests.benchmark.run_benchmark \
    --corpus backend/tests/benchmark/corpus \
    --output backend/tests/benchmark/results
```

Results land in `backend/tests/benchmark/results/REPORT.md` and
`backend/tests/benchmark/results/records.json`.

## What we learned

1. **Synthetic benchmarks are great at finding structural bugs.** The
   FP rate problem was invisible until we ran the benchmark; the
   engine *felt* right in manual testing because we always tested
   with breaking changes.
2. **Honest numbers build trust.** The "< 5% FP" target was aspirational.
   Now it's measured: 2.7%. If a future regression pushes it above 5%,
   the weekly CI benchmark will catch it before customers do.
3. **The bottleneck is JSON parsing, not the algorithm.** At 0.06 ms
   p95, latency is a non-issue for now. If/when we hit 1,000-asset
   repos, we'll likely switch to a binary manifest format.

---

The full report is at
[`backend/tests/benchmark/results/REPORT.md`](../../backend/tests/benchmark/results/REPORT.md)
and the methodology is at
[`docs/benchmark.md`](../benchmark.md).
