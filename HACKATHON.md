# Cortex Autopilot — Hackathon Submission

> **Track:** Agents That Do Real Work *(secondary fit: Production ML Agents)*
> **License:** Apache-2.0
> **Demo video:** _(upload pending — see Phase D)_
> **Public repo:** _(push pending — see Phase A3)_

---

## What it does

Cortex Autopilot is a **CI/CD Impact Gate for data platforms** — it
blocks risky data changes (dbt models, Snowflake schemas) before they
reach production. The system is built around an LLM-powered agent
that:

1. **Reads** lineage and schema metadata from DataHub (mock or real)
2. **Reasons** about what would break if a proposed change shipped
3. **Acts** — blocks the PR, generates a ready-to-apply SQL fix,
   alerts Slack, and writes back to DataHub
4. **Remembers** — every verdict is recorded so the next agent or
   human inherits the knowledge

The core loop is the exact "read → reason → act → write back"
pattern that the **Agents That Do Real Work** challenge describes.

---

## Test it in 3 commands

```bash
git clone <repo-url> cortex-autopilot && cd cortex-autopilot
./setup.sh                     # one-command local deploy
python examples/demo/run_demo.py   # CLI demo end-to-end
```

The CLI demo runs the engine against the bundled sample dbt project,
prints the verdict, the generated PR comment, the Slack alert, and
the DataHub assertion.

---

## Architecture

```
            ┌─────────────────────────────┐
            │   GitHub Action (CI Gate)   │
            └──────────────┬──────────────┘
                           │
                           ▼
   ┌────────────────────────────────────────────┐
   │            CortexAgent (LLM)               │
   │   ┌──────────┐  ┌──────────────┐  ┌─────┐ │
   │   │  Context │→ │  Impact      │→ │ Fix │ │
   │   │  Store   │  │  Engine      │  │ Gen │ │
   │   └──────────┘  └──────────────┘  └─────┘ │
   └──────────────────────┬─────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
   ┌─────────┐      ┌──────────┐      ┌──────────┐
   │ dbt     │      │ DataHub  │      │ Slack    │
   │ manifest│      │ writeback│      │ Block Kit│
   └─────────┘      └──────────┘      └──────────┘
```

See [`docs/architecture.md`](docs/architecture.md) for the full diagram.

---

## What the benchmark says

We ran a **10,000-evaluation synthetic benchmark** plus a real-world
validation on `examples/sample_dbt_project/`. Measured numbers:

| Metric | Synthetic | Real-world |
|--------|-----------|------------|
| **p50 latency** | 0.02 ms | < 1 ms |
| **p95 latency** | 0.06 ms | < 1 ms |
| **p99 latency** | 0.10 ms | < 1 ms |
| **False-positive rate** | 2.7% | 0.0% |
| **False-negative rate** | 0.0% | 0.0% |
| **Severity accuracy** | 82.8% | 55.0% |

Full methodology: [`docs/benchmark.md`](docs/benchmark.md).
Full results: [`docs/benchmark_results_2026.md`](docs/benchmark_results_2026.md).

---

## Two cherry-on-top features

### Cherry #1: Auto-Fix PR Generation

When the engine blocks a PR, the Action posts a **ready-to-apply SQL
migration patch** as a `<details>` block in the PR comment. The patch
comes from `services/artifact_generator.py` and includes:

- The exact `ALTER TABLE … RENAME COLUMN` statement
- Updated downstream views with backward-compatible aliases
- A "review and apply" instruction for the developer

**Why it matters:** Most CI gates just block. We block *and* suggest
the fix. The developer applies the patch, the second run passes, the
incident is prevented — without a round-trip through Slack.

**Example:** [`examples/sample_artifacts/auto_fix_column_remove.sql`](examples/sample_artifacts/auto_fix_column_remove.sql)

### Cherry #2: DataHub Assertion Writeback

When the engine records a verdict, the backend writes a DataHub
assertion (`/openapi/v1/entity/{urn}/assertion`) so the metadata
system records that this asset had a "blocked change" event. The next
agent or human viewing the asset in DataHub sees the verdict history
inline with the schema.

**Why it matters:** This closes the read-write loop with DataHub. The
agent READS metadata, REASONS about impact, ACTS by blocking, and
WRITES BACK so future agents inherit the knowledge. This is the
literal description of the "Agents That Do Real Work" challenge.

**Mock-mode safe:** When `USE_MOCK_DATAHUB=true` (the default), the
assertion is recorded in the mock store so judges can see the
behavior without running a real DataHub instance.

---

## Why this fits "Production ML Agents"

The bundled sample dbt project (`examples/sample_dbt_project/`)
includes `customer_ltv` — a model tagged `ml-feature` and owned by
`ml-team`. It feeds `dashboard_feed`, which is tagged `critical`.

The engine has an explicit `WEIGHT_ML_DEPENDENCY = 20` in
[`app/engine/impact_engine.py`](backend/app/engine/impact_engine.py).
A schema change on `stg_customers.first_name` cascades:

```
stg_customers (rename first_name → first_initial)
    → customer_ltv (clv_score now uses first_initial)
    → dashboard_feed (ltv_score is wrong)
    → ML feature pipeline emits corrupted embeddings
```

Cortex blocks the change and writes the rename propagation SQL into
the PR. That's **ML lineage protection at PR time**, not after
the model silently degrades.

---

## Project structure

```
cortex-autopilot/
├── backend/                 # FastAPI app, agents, engines, connectors
├── frontend/                # Next.js UI (verdict card, policy tweaker)
├── action/                  # GitHub Action (CI gate)
├── website/                 # Marketing site
├── docs/                    # Architecture, setup, tutorials, blog
├── examples/                # Sample dbt project, artifacts, scenarios
└── backend/tests/benchmark/ # Synthetic + real-world benchmark
```

---

## What's in `examples/`

| Path | Contents |
|------|----------|
| `examples/sample_dbt_project/` | Realistic 7-model dbt project with ML lineage |
| `examples/sample_artifacts/` | 5 generated artifacts (SQL, dbt, DAG, markdown, auto-fix) |
| `examples/sample_scenarios/` | 5 scenario JSON files (rename, remove, owner, pipeline, deprecation) |
| `examples/sample_writebacks/` | Resolution records |
| `examples/sample_fix.sql` | Sample remediation script |
| `examples/sample_incident.json` | Sample incident payload |
| `examples/demo/run_demo.py` | End-to-end CLI demo runner |

---

## How the agent works

The `CortexAgent` (in [`backend/app/services/agent.py`](backend/app/services/agent.py))
runs an LLM tool-calling loop:

1. **Builds messages** — system prompt + RAG context from the
   Context Store + the current task
2. **Asks the LLM** for the next step (a tool call or final answer)
3. **Executes** the tool (`get_asset_context`, `classify_complexity`,
   `run_impact_analysis`, `generate_fix`, …)
4. **Records** every step on the `AutopilotTask` so a human can audit
   the reasoning chain afterwards
5. **Writes back** the verdict to DataHub

The `Autopilot` (in
[`backend/app/services/autopilot.py`](backend/app/services/autopilot.py))
wraps the agent with an autonomous observer loop that polls every
registered connector on a cadence and auto-enqueues a task when an
asset's schema or ownership has drifted.

---

## Stack

- **Backend:** FastAPI, Pydantic v2, asyncpg, OpenTelemetry
- **Agent:** OpenAI-compatible LLM (default: Nvidia NIM)
- **Connectors:** dbt (manifest.json/catalog.json), Snowflake (INFORMATION_SCHEMA mock), DataHub (mock + real GMS)
- **Frontend:** Next.js 14, React 18, SWR
- **Action:** Python 3.11, GitHub toolkit
- **Benchmarks:** 10K-evaluation synthetic corpus, NIST percentile, confusion matrix

---

## License

Apache-2.0. See [`LICENSE`](LICENSE).
