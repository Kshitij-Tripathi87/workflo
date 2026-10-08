# Cortex Benchmark 2026 — Methodology

> **Goal:** produce reproducible numbers that demonstrate Cortex
> Autopilot's impact-prediction engine is accurate, fast, and useful.

This document describes the **inputs**, **procedure**, and **metrics**
of the benchmark. Anyone with the open-source repo can reproduce it.

## Why this matters

Engineering founders need **evidence**, not feature lists. Customers
will ask:

- How accurate is your blast-radius prediction?
- What's your false-positive rate?
- How long does the engine take on a real warehouse?

The benchmark answers each with a number, published with the
methodology so others can audit it.

## Inputs

### 1. Synthetic dbt repositories

We generate **100** synthetic dbt projects. Each project:

- Models the structure of a real analytics warehouse.
- Has between **20 and 200 models** (Poisson-distributed around 60).
- Has between **2 and 12 sources**.
- Has random lineage edges with realistic density (avg 1.8
  upstream dependencies per model).

The generator seeds are fixed for reproducibility. Same seed → same
repos. The repo generator is at
`backend/tests/benchmark/repo_generator.py`.

### 2. Simulated schema changes

For each project, we generate **100 schema changes** randomly drawn
from:

| Change type | Frequency |
|-------------|-----------|
| `column_remove` | 30% |
| `column_rename` | 25% |
| `type_change` | 15% |
| `add_not_null` | 10% |
| `add_column` | 10% |
| `no_change` | 10% |

Total: **10,000** simulated changes across the corpus.

### 3. Ground truth

For each simulated change, we compute the **true blast radius** by
literally applying the change to a copy of the manifest and walking the
resulting graph. This is the answer key.

## Procedure

### Step 1 — Generate the corpus

```bash
python backend/tests/benchmark/repo_generator.py \
  --output-dir backend/tests/benchmark/corpus \
  --num-repos 100 \
  --num-changes-per-repo 100 \
  --seed 20260801
```

This produces 100 repos and 10,000 change records in `corpus/`.

### Step 2 — Run the engine

For each repo + change pair, we call:

```python
from app.connectors.dbt.connector import DbtConnector
from app.engine.future_search_engine import generate_futures

connector = DbtConnector(
    manifest_path=f"corpus/{repo}/manifest.json",
    catalog_path=f"corpus/{repo}/catalog.json",
)
await connector.connect()
snapshot = await connector.build_snapshot([change.asset_urn])
plan = generate_futures(snapshot, change.asset_urn, "minimize incident risk")
predicted_blast = plan.ranked_choice.predicted_blast_radius
predicted_severity = plan.ranked_choice.predicted_severity
```

We record the predicted blast radius and severity for each pair.

### Step 3 — Compute metrics

The benchmark script (`benchmark/run_benchmark.py`) computes:

#### A. Latency

| Metric | Definition |
|--------|------------|
| **p50 latency** | Median simulation time across all 10,000 changes |
| **p95 latency** | 95th percentile simulation time |
| **p99 latency** | 99th percentile simulation time |
| **Max latency** | Worst-case simulation time |

Measured from `connector.connect()` return to `generate_futures()`
return.

#### B. Blast-radius accuracy

For each change, compare predicted blast radius to true blast radius.

| Metric | Definition |
|--------|------------|
| **Exact match rate** | % of changes where predicted == true |
| **Off-by-one rate** | % of changes where `|predicted − true| ≤ 1` |
| **Mean absolute error** | Average `|predicted − true|` |
| **Spearman correlation** | Rank correlation between predicted and true across all 10,000 changes |

#### C. Severity accuracy

Severity is on a 0–100 scale.

| Metric | Definition |
|--------|------------|
| **Mean absolute error** | Average `|predicted − true|` |
| **Pearson correlation** | Linear correlation between predicted and true |
| **Calibration error** | Average `|predicted_band_share − true_band_share|` across bands (low/medium/high/critical) |

#### D. False-positive / false-negative rates

A **false positive** is when the engine blocks a change that, in
reality, would have caused no downstream breakage.

A **false negative** is when the engine passes a change that, in
reality, would have broken something.

For each threshold setting (default `block_on: critical`):

| Metric | Definition |
|--------|------------|
| **FP rate** | False positives ÷ total harmless changes |
| **FN rate** | False negatives ÷ total harmful changes |
| **Precision** | TP ÷ (TP + FP) |
| **Recall** | TP ÷ (TP + FN) |
| **F1 score** | Harmonic mean of precision and recall |

### Step 4 — Generate the report

The benchmark script writes:

- `benchmark/results/latency.csv` — per-change latencies
- `benchmark/results/predictions.csv` — predicted vs true for all changes
- `benchmark/results/summary.json` — aggregate metrics
- `benchmark/results/REPORT.md` — human-readable summary

## What "Good" Looks Like

Targets we expect to hit (and publish):

| Metric | Target |
|--------|--------|
| p50 latency | < 50 ms |
| p95 latency | < 250 ms |
| p99 latency | < 1 s |
| Blast radius exact match | > 80% |
| Blast radius off-by-one | > 95% |
| Severity Pearson r | > 0.85 |
| FP rate (block_on: critical) | < 5% |
| FN rate (block_on: critical) | < 2% |

## Reproducing the Benchmark

```bash
git clone https://github.com/cortex-autopilot/cortex-autopilot.git
cd cortex-autopilot
pip install -r backend/requirements.txt

# Generate corpus + run benchmark
python backend/tests/benchmark/repo_generator.py --seed 20260801
python backend/tests/benchmark/run_benchmark.py \
  --corpus backend/tests/benchmark/corpus \
  --output benchmark/results
```

Expected runtime on a MacBook Pro M2:

- Corpus generation: ~30 seconds
- 10,000 evaluations: ~10 minutes
- Total: ~12 minutes

## What We Won't Benchmark

- **Recommendation accuracy.** "Did the engineer accept the
  recommendation?" is a customer workflow question, not an engine
  question.
- **LLM agent performance.** We use a deterministic scoring engine for
  impact, not an LLM. The agent is a thin orchestrator.

## What We'll Add in 2027

- Real-world datasets from design partners (anonymized)
- Comparison to a baseline (Monte Carlo schema drift detection)
- Latency under concurrent load
