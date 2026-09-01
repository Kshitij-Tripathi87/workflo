# Tenant Shield — DataHub-Powered Data Observability & Test Generation Agent

> **Hackathon category:** Agents That Do Real Work (with elements of Metadata-Aware Code Generation & Development)

## 📋 Summary

Tenant Shield is an AI agent that reads DataHub metadata to *understand what's connected to what*, then **takes real action**: it generates production-ready pytest tests from real DataHub schemas and lineage, runs them, and writes the results back to DataHub as assertions and incidents — so the next person or agent inherits the knowledge.

It works as a local CLI, a SaaS control plane, a Kubernetes-deployed worker fleet, and a dashboard so the same agent can serve solo developers, data teams, and enterprises without changing a line of test code.

## 🔑 What it does

1. **Reads DataHub** — connects via the DataHub GraphQL API (direct) or the DataHub MCP Server (optional transport). On connection, the agent pulls:
   - Dataset schemas (column names, types, nullability, primary keys, descriptions)
   - Upstream + downstream lineage edges (with column-level mappings)
   - Ownership metadata (declared owner per dataset)
2. **Generates metadata-aware pytest tests** that work on first try because they read DataHub's source-of-truth *before* generating anything. The generator emits, per dataset:
   - Schema integrity tests (expected columns present, PK uniqueness, nullability)
   - Lineage continuity tests (each edge declared in DataHub must be live)
   - Ownership completeness tests (every critical dataset must have an owner for SOC 2)
3. **Runs the tests** locally (single focus dev) or via the cloud worker fleet (parallel, real-browser-capable)
4. **Writes results back to DataHub** as assertion run events + incidents, so failures surface on the dataset page in DataHub and downstream consumers see them immediately

See `examples/generated-tests/` for sample generated artifacts judges can review without running the code.

## 🎯 The challenge it solves

Data teams ship broken data every day because:
- Schemas drift silently (someone drops a column the downstream pipeline depends on)
- Lineage breaks silently (an upstream Airflow task is paused, downstream dashboards still look "fresh")
- No one owns critical datasets (anonymized test data leaks into production)
- Compliance auditors ask "who is responsible for this dataset?" and no one knows

Tenant Shield turns the metadata DataHub already has into *executable guarantees*. DataHub becomes the single source of truth; Tenant Shield becomes the part of your platform that *enforces* it.

## ⚙️ Technologies used

| Layer | Tech | Why |
|---|---|---|
| Metadata source | DataHub (GraphQL + MCP) | The "memory" the agent reads from and writes back to |
| Agent transport | Direct GraphQL + optional MCP Server | MCP support lets it slot into larger agent frameworks |
| Test generation | Python AST templates (no LLM dependency) | Reproducible, economical, auditable |
| Test execution | pytest + Playwright (Worker Engine) | Works equally for data tests and UI tests |
| Backend API | FastAPI + async SQLAlchemy (Postgres / SQLite) | Async orchestration of the worker fleet |
| CLI | Click + Rich + Questionary | Goal-based, interactive UX |
| Dashboard | Next.js 14 + Tailwind | SOC 2 evidence + run history |
| Fleet | Kubernetes + KEDA | Autoscaling workers — also deployable into a customer VPC |

## 🏗️ Architecture

```
                          ┌─────────────────────────────┐
                          │  DataHub  (source-of-truth) │
                          │  - schemas, lineage, owners │
                          └──────┬──────────────┬───────┘
                                 │ read          ▲ write back (assertions + incidents)
                                 ▼              │
┌─────────────────┐    ┌──────────────────┐    │
│  Agent (CLI / IDE)│───▶│ Control Plane    │───┘
│  - asks the goal  │    │ (FastAPI)        │
│  - submits run    │    │ - run queue      │
└─────────────────┘    │ - results store  │
                       │ - test generator │
                       └────────┬─────────┘
                                │ enqueue
                                ▼
                       ┌──────────────────┐
                       │ Worker Engine     │
                       │ - runs pytest    │
                       │ - streams logs   │
                       │ - uploads traces │
                       └──────────────────┘
                                │ write results
                                ▼
                       ┌──────────────────┐
                       │ Dashboard        │
                       │ - run history    │
                       │ - SOC 2 evidence │
                       └──────────────────┘
```

## 🧪 How judges can test it

### Run the test generator against mock DataHub metadata (zero setup)

```bash
# 1. Install dependencies (Python 3.11+)
python -m venv venv
source venv/bin/activate       # or: .\venv\Scripts\activate
pip install -e packages/core-schema
pip install -e packages/common-utils
pip install -e packages/datahub-client

# 2. Generate sample test artifacts using mock DataHub metadata
python examples/generate_examples.py
```

This produces 6 pytest modules under `examples/generated-tests/`. Each is a complete, runnable pytest file built from realistic DataHub metadata (a multi-tenant SaaS with `users` + `projects` tables). The generated `examples/generated-tests/MANIFEST.md` lists every artifact.

### Run the backend API locally (zero external services)

```bash
pip install -e apps/control-plane
uvicorn app.main:app --reload --port 8000
# Visit http://localhost:8000/docs for the OpenAPI UI
```

Create an API key and submit a "security" run:

```bash
curl -X POST http://localhost:8000/v1/keys \
  -H "Content-Type: application/json" \
  -d '{"label":"demo","scopes":["run_tests","read_reports","admin"]}'
# -> {"raw_key":"ts_live_...","id":"..."}

curl -X POST http://localhost:8000/v1/runs \
  -H "Content-Type: application/json" \
  -H "X-TenantShield-Key: ts_live_..." \
  -d '{"goal":"security","markers":["security"]}'
# -> {"run_id":"...","status":"queued"}
```

### Run automated tests

```bash
pytest packages/core-schema/tests -v          # shared models
pytest packages/common-utils/tests -v         # utilities
pytest packages/datahub-client/tests -v       # DataHub client
pytest apps/control-plane/tests -v            # backend API (16 tests)
pytest apps/agent-cli/tests -v                # CLI (34 tests)
pytest apps/worker-engine/tests -v            # worker (33 tests)
```

## 🚀 Extra innovation (wider SaaS category)

Tenant Shield goes beyond single-task hackathon scope to be a full SaaS product:

| Innovation | What it means |
|---|---|
| **Goal-based UX** | Developers say "test security", the agent handles the rest — no markers, filters, or boilerplate |
| **Hybrid SaaS + on-prem** | Workers can run in your cloud or in the customer's VPC (data residency) |
| **SOC 2 evidence built in** | Every test pins to AICPA controls (CC6.1, CC7.2) and exports auditable HTML/PDF reports |
| **Real browser fleet** | Worker supports both Playwright containers and remote grids (BrowserStack, Sauce Labs) for high-fidelity cross-platform runs |
| **Result writeback to DataHub** | The agent doesn't just *read* DataHub — it writes assertion events and incidents back so the metadata graph becomes self-healing |
| **Multi-tenant by design** | Each org has its own API keys, projects, quotas — same agent serves multiple teams |
| **Dashboard** | Run history, run detail with traces, compliance center |

## 📦 Repository layout

See `docs/architecture.md` for the full diagram. Key pieces:

- `packages/core-schema/` — shared Pydantic models (RunSpec, TestResult, etc.)
- `packages/common-utils/` — structured logging + config helpers
- `packages/datahub-client/` — **DataHub integration: GraphQL + MCP client, metadata inspector, test generator, result writeback**
- `apps/control-plane/` — FastAPI backend (auth, runs API, key management, queue)
- `apps/agent-cli/` — interactive CLI (`tenant-shield test`, `auth login`, `runs list`)
- `apps/worker-engine/` — execution engine (pytest + Playwright worker with auto-scaling)
- `apps/dashboard/` — Next.js frontend
- `examples/generated-tests/` — sample generated test artifacts
- `infra/` — Terraform + Kubernetes manifests

## 🎥 Demo video

A demonstration video is available at <YOUTUBE-URL-PLACEHOLDER>. The video walks through:
1. Connecting to DataHub (mock metadata)
2. Generating a full suite of metadata-aware pytest tests
3. Submitting a "security" run to the control plane
4. Viewing results and SOC 2 evidence

## 📄 License

Apache License 2.0 — see `LICENSE` at the root of the repository.

## 👥 Authors

Tenant Shield team — built for the DataHub hackathon.
