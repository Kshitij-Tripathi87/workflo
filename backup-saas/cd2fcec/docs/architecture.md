# Tenant Shield Platform — Architecture Overview

## System Components

```
┌─────────────────┐     ┌──────────────────────┐     ┌─────────────────────┐
│  Agent (CLI/IDE) │     │  Control Plane       │     │  Worker Engine       │
│  - API Key       │────▶│  (FastAPI)           │────▶│  (Pytest+Playwright) │
│  - Goal Spec     │     │  - Auth              │     │  - Browser Fleet     │
└─────────────────┘     │  - Run Queue (Redis) │     │  - Log Streaming     │
                        │  - Results (Postgres) │     └──────────┬──────────┘
┌─────────────────┐     │  - Artifacts (S3)    │                │
│  Dashboard      │     └──────────────────────┘                │
│  (Next.js)      │─────────────────────────────────────────────┘
│  - Runs         │
│  - SOC2 Reports │     ┌──────────────────────┐
│  - Settings     │     │  Enterprise Workers  │
└─────────────────┘     │  (Customer's VPC)    │
                        │  Same image, outbound│
                        │  to Control Plane     │
                        └──────────────────────┘
```

## Data Flow

1. **Auth**: Developer runs `tenant-shield auth login` → API key stored in `~/.tenant-shield/config.yaml`
2. **Submit**: `tenant-shield test --goal security --cloud` → Agent POSTs `RunSpec` to `/v1/runs`
3. **Queue**: Control Plane enqueues the spec in Redis → returns `run_id` to CLI
4. **Execute**: Worker dequeues spec → provisions browser → runs pytest → streams logs to `/v1/runs/{id}/logs`
5. **Complete**: Worker uploads artifacts to S3 → calls `/v1/runs/{id}/complete` with `RunSummary`
6. **Report**: SOC2 HTML/PDF generated → stored in S3 → presigned URL available via `/v1/runs/{id}/report`
7. **View**: Developer opens Dashboard → Run Detail page shows results, traces, screenshots, and compliance evidence

## Shared Schema

All services depend on `packages/core-schema` which defines:
- `RunSpec` (CLI → Worker)
- `TestResult` / `RunSummary` (Worker → Backend)
- `Organization` / `Project` / `ApiKey` (Dashboard ↔ Backend)

## Distribution Models

| Model | Worker Location | Connectivity | Use Case |
|-------|----------------|--------------|----------|
| **SaaS** | Tenant Shield Cloud | Direct | Standard users |
| **Enterprise** | Customer's Cloud (VPC) | Outbound to Control Plane | Data residency, low latency |

## Built on top of the existing `workflowpro-tests` framework

The `tenant_shield` package (in the original repo) provides the pytest plugin, isolation verifier, and SOC2 report generator. The Worker Engine imports and wraps these components for cloud execution.
