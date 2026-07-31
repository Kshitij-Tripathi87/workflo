# Cortex Autopilot

**Enterprise decision intelligence** — explore millions of possible futures before touching production.

---

## Hackathon Submission

> **Track:** Agents That Do Real Work *(secondary fit: Production ML Agents)*

- 📄 **Submission doc:** [`HACKATHON.md`](HACKATHON.md) — 1-page overview for judges
- 🎬 **Demo video:** _(YouTube URL — see Phase D in HACKATHON.md)_
- 🧪 **Test in 3 commands:**
  ```bash
  git clone <repo-url> cortex-autopilot && cd cortex-autopilot
  ./setup.sh
  python examples/demo/run_demo.py
  ```
- 📊 **Benchmark:** p95 latency 0.06 ms, FP rate 2.7%, FN rate 0.0%
  ([full report](docs/benchmark_results_2026.md))
- 🍒 **Two cherry features:**
  1. **Auto-Fix PR Generation** — blocks the PR *and* posts a ready-to-apply SQL migration
  2. **DataHub Assertion Writeback** — closes the read-write loop with DataHub

See [`HACKATHON.md`](HACKATHON.md) for the full submission.

---

Cortex Autopilot answers critical questions:

- What breaks if this column changes?
- What breaks if this pipeline fails?
- **What should we do next, and why?**
- **Which action maximizes reliability while minimizing effort?**

## Core Loop

```
DataHub context → future search → impact explanation → ranked recommendation → write-back
```

## Features

- **Future Search** — Generate and rank multiple plausible futures automatically
- **Scenario Simulation** — Test schema changes, ownership gaps, pipeline failures, deprecations
- **Impact Analysis** — Compute blast radius with severity scoring
- **Recommendation Ranking** — Select optimal actions based on risk, effort, and benefit
- **Explainable AI** — Every recommendation includes evidence-backed reasoning
- **Artifact Generation** — Produce SQL/dbt/DAG/YAML/markdown fixes
- **Write-back** — Record resolutions to audit log

## Quick Start

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000

## Demo Flow

1. **Select an asset** (e.g., `orders` table)
2. **Run Future Search** — automatically evaluates 6 candidate actions
3. **Review ranked recommendation** with severity/effort/benefit scores
4. **Read explanation** — why this action was chosen over alternatives
5. **Simulate specific scenarios** if needed
6. **Preview artifact** (generated SQL patch)
7. **Record resolution** (write-back logged)

## Architecture

```
DataHub (mock/real)
    ↓
Context Adapter
    ↓
Graph Snapshot
    ↓
Scenario Engine
    ↓
Impact Engine (scoring)
    ↓
Recommendation Engine
    ↓
Artifact Generator
    ↓
Write-back Layer
    ↓
Frontend Control Room
```

See [docs/architecture.md](docs/architecture.md) for details.

## Scenario Types

| Type | Description |
|------|-------------|
| `schema_rename` | Column renamed |
| `schema_remove` | Column removed |
| `owner_missing` | Owner unassigned |
| `pipeline_failure` | Pipeline failed |
| `dataset_deprecation` | Dataset deprecated |

## API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /assets/{urn}` | Get asset |
| `GET /assets/{urn}/lineage` | Get lineage |
| `GET /assets/{urn}/graph` | Get graph snapshot |
| `POST /scenarios/simulate` | Simulate change |
| `POST /impact/analyze` | Analyze impact |
| `POST /recommendations/generate` | Generate recommendation |
| `POST /artifacts/generate` | Generate artifact |
| `POST /writeback` | Record resolution |
| `POST /demo/run` | Run full demo flow |
| **`POST /future-search/run`** | **Generate and rank futures (NEW)** |

## Mock Mode

The app ships with mock DataHub data so it runs immediately. Set `USE_MOCK_DATAHUB=true` (default) to use mock data.

To connect to real DataHub:

```bash
export DATAHUB_BASE_URL=http://your-datahub:8080
export DATAHUB_TOKEN=your_token
export USE_MOCK_DATAHUB=false
```

See [docs/setup.md](docs/setup.md) for full setup instructions.

## Examples

Sample scenarios, artifacts, and writeback records are in `examples/`:

- `examples/sample_scenarios/` — JSON scenario definitions
- `examples/sample_artifacts/` — Generated SQL, dbt, DAG, markdown
- `examples/sample_writebacks/` — Resolution records

## Demo Script

See [docs/demo_script.md](docs/demo_script.md) for a 3-minute walkthrough.

## License

Apache-2.0