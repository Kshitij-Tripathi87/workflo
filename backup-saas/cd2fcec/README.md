# Tenant Shield — DataHub-Powered Data Observability & Test Generation Agent

> Built for the DataHub hackathon — uses DataHub to read what's connected to what, generates metadata-aware pytest tests, runs them, and writes results back to DataHub so the next agent inherits the knowledge.

## What it does

1. **Reads DataHub metadata** via GraphQL (direct) or the MCP Server (optional) — schemas, lineage, ownership
2. **Generates pytest tests** that work on the first try because they read DataHub for the real schemas and lineage before generating anything
3. **Runs the tests** locally (single focus dev) or via the cloud worker fleet (parallel, browser-capable)
4. **Writes results back to DataHub** as assertion events + incidents so failures surface on the dataset page

See `examples/generated-tests/` for sample generated artifacts and `PROJECT_DESCRIPTION.md` for the full hackathon submission text.

## Project Structure

This repo combines **two layers** — a multi-tenant test framework (the original `tenant_shield/` package) and a full SaaS platform built on top of it with DataHub integration:

```
workflowpro-tests/
├── tenant_shield/            # Original test framework (pytest plugin, isolation verifier, SOC2 report)
├── tests/                    # Test suites (login, multi-tenant, integration, security, unit)
├── data/                     # Test data factories + fixtures
├── apps/                     # ── SaaS Platform ──
│   ├── control-plane/        # FastAPI backend (auth, run orchestration, results)
│   ├── agent-cli/            # Interactive CLI agent (goal-based test runner)
│   ├── worker-engine/        # Execution engine (pytest + Playwright worker pool)
│   └── dashboard/            # Next.js dashboard (run history, SOC2 compliance center)
├── packages/                 # ── Shared Libraries ──
│   ├── core-schema/          # Shared Pydantic models (RunSpec, TestResult, etc.)
│   ├── common-utils/         # Shared logging, config helpers
│   └── datahub-client/       # DataHub integration: GraphQL + MCP, test generator, writeback
├── examples/                 # Sample generated test artifacts (for judges)
│   ├── generate_examples.py
│   ├── generated-tests/      # Auto-generated pytest modules you can read directly
│   └── tests/helpers/        # Validators imported by the generated tests
├── infra/                    # Infrastructure as Code
│   ├── terraform/            # Cloud infrastructure (S3, RDS, ElastiCache)
│   └── k8s/                  # Kubernetes manifests + KEDA autoscaling
├── docs/                     # Architecture documentation
├── action.yml                # GitHub composite action for CI
├── ci-templates/             # GitLab CI template
├── pyproject.toml            # Package metadata for tenant_shield
├── pytest.ini                # Pytest configuration
├── requirements.txt          # Python dependencies
├── docker-compose.yml        # Local dev stack (Postgres, Redis, MinIO)
├── LICENSE                   # Apache 2.0
└── PROJECT_DESCRIPTION.md    # Hackathon submission text
```

## Quick Start (judge-friendly — zero external services)

### Prerequisites
- Python 3.11+
- (Optional) Node.js 20+, Docker, PostgreSQL & Redis

### 1. Install the platform
```bash
python -m venv venv
source venv/bin/activate       # or: .\venv\Scripts\activate
pip install -r requirements.txt
pip install -e packages/core-schema
pip install -e packages/common-utils
pip install -e packages/datahub-client
pip install -e apps/control-plane[dev]
pip install -e apps/agent-cli
pip install -e apps/worker-engine
playwright install chromium
```

### 2. Generate metadata-aware tests from DataHub (mock metadata)
```bash
python examples/generate_examples.py
# -> examples/generated-tests/test_schema_public_users.py
# -> examples/generated-tests/test_lineage_postgres_public_users_prod.py
# (and 4 more)
```

### 3. Run the original test framework (43 tests pass, 1 skip, 2 deselected)
```bash
pytest tests -k "not browserstack and not cross_browser" -v
```

### 4. Run the backend API (SQLite, no Postgres needed)
```bash
cd apps/control-plane
uvicorn app.main:app --reload --port 8000
# Visit http://localhost:8000/docs for the OpenAPI UI
```

### 5. Run the interactive CLI agent
```bash
tenant-shield auth login        # enter the API key you create via /v1/keys
tenant-shield test              # pick smoke/security/integration/mobile/regression
```

### 6. Connect to a real DataHub instance (optional)
```bash
export DATAHUB_GMS_URL=http://localhost:8080
export DATAHUB_TOKEN=your-personal-access-token
# Or use MCP: pass --use-mcp when invoking the generator
```

## Running the Tests

```bash
# Original test framework (multi-tenant isolation)
pytest tests -k "not browserstack and not cross_browser" -v

# Platform test suites
pytest packages/core-schema/tests -v      # 66 tests — shared models
pytest packages/common-utils/tests -v     # 23 tests — utilities
pytest packages/datahub-client/tests -v   # 15 tests — DataHub client + generator
pytest apps/control-plane/tests -v        # 16 tests — backend API
pytest apps/agent-cli/tests -v            # 34 tests — CLI agent
pytest apps/worker-engine/tests -v       # 33 tests — worker engine
```

## DataHub Integration

The `packages/datahub-client/` package is the bridge to DataHub:

| Module | Purpose |
|---|---|
| `client.py` | Connects via GraphQL (default) or the MCP Server (optional) |
| `inspector.py` | Reads schemas + lineage, computes integrity scores |
| `generator.py` | Generates pytest modules from DataHub metadata |
| `writeback.py` | Writes test outcomes back to DataHub as assertions + incidents |

## API Endpoints (Control Plane)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`  | `/v1/health` | Health check |
| `POST` | `/v1/runs` | Submit a test run (requires `X-TenantShield-Key`) |
| `GET`  | `/v1/runs/{id}` | Get run status + summary + logs |
| `POST` | `/v1/runs/{id}/logs` | Worker streams logs |
| `POST` | `/v1/runs/{id}/complete` | Worker signals completion |
| `POST` | `/v1/keys` | Create an API key (returns raw key once) |
| `GET`  | `/v1/keys` | List API keys |
| `DELETE` | `/v1/keys/{id}` | Revoke an API key |
| `GET`  | `/v1/runs/{id}/results` | Detailed test list |
| `GET`  | `/v1/runs/{id}/artifacts` | List artifacts |
| `GET`  | `/v1/runs/{id}/report` | SOC 2 report link |

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `TEST_ENV` | Yes | Environment name: `local`, `ci`, or `staging` |
| `BASE_URL` | Yes | Web app URL |
| `API_BASE_URL` | Yes | API base URL |
| `TENANT_ID` | Yes | Default tenant under test |
| `TEST_EMAIL` | Yes | Login email for test user |
| `TEST_PASSWORD` | Yes | Login password |
| `API_AUTH_TOKEN` | Yes | Bearer token for API client |
| `COMPANY1_TOKEN` | For isolation tests | Auth token for company1 |
| `COMPANY2_TOKEN` | For isolation tests | Auth token for company2 |
| `DATAHUB_GMS_URL` | For DataHub integration | DataHub GMS endpoint, e.g. `http://localhost:8080` |
| `DATAHUB_TOKEN` | For DataHub auth | DataHub personal access token |
| `BROWSERSTACK_USERNAME` | For BrowserStack | BrowserStack account username |
| `BROWSERSTACK_ACCESS_KEY` | For BrowserStack | BrowserStack account access key |
| `HEADLESS` | No | Run headless (default `true`) |
| `DEFAULT_TIMEOUT` | No | Playwright timeout in ms (default `15000`) |

## License

Apache License 2.0 — see `LICENSE`.
