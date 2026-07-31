# Cortex Autopilot — API Reference

The Cortex Autopilot backend exposes a small, focused HTTP API. Every
endpoint returns JSON. Authentication is optional in `dev` mode and
required in `prod`.

**Base URL:** `http://localhost:8000` (default local install)

**Auth:** `Authorization: Bearer <token>` header. Token issuance is
handled by `POST /auth/login` (OIDC-based) or `POST /auth/dev-token`
in dev mode.

**Error format:** every error response has the shape:

```json
{
  "error": "ERROR_CODE",
  "message": "Human-readable description",
  "details": { "...": "..." },
  "hint": "Actionable next step"
}
```

---

## Health

### `GET /health`

Quick liveness check used by Docker. Always returns 200 if the process
is running.

```bash
curl http://localhost:8000/health
```

```json
{ "status": "ok", "env": "dev" }
```

### `GET /health/detailed`

Reports per-connector status, uptime, and cache stats. Use this for
operator dashboards.

```bash
curl http://localhost:8000/health/detailed | jq
```

```json
{
  "status": "ok",
  "version": "0.3.0",
  "name": "Cortex Autopilot",
  "env": "dev",
  "uptime_seconds": 14.2,
  "connectors": {
    "dbt": { "status": "connected", "path": "..." },
    "snowflake": { "status": "mock" },
    "datahub": { "status": "mock" }
  },
  "cache": { "alive_keys": 1, "total_keys": 1, "ttl_seconds": 60.0 }
}
```

### `GET /version`

```bash
curl http://localhost:8000/version
```

```json
{ "version": "0.3.0", "name": "Cortex Autopilot" }
```

### `GET /metrics`

Prometheus-format metrics endpoint.

```bash
curl http://localhost:8000/metrics
```

---

## Future Search Engine

### `POST /future-search/run`

The core endpoint. Builds a graph snapshot from the chosen connector,
simulates the impact of the change, ranks candidate actions, and
evaluates declared policies.

**Request body:**

```json
{
  "asset_urn": "urn:dbt:model:jaffle_shop:orders",
  "objective": "minimize incident risk",
  "constraints": {},
  "policies": [
    {
      "name": "Block critical-severity changes",
      "max_severity": 75,
      "max_blast_radius": 10,
      "action": "block"
    }
  ],
  "connector": "dbt"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `asset_urn` | string | yes | Cortex URN of the asset being changed |
| `objective` | string | no | `minimize incident risk` (default), `minimize effort`, `maximize reliability`, `balance cost and risk` |
| `constraints` | object | no | Extra constraints applied during ranking |
| `policies` | array | no | Policy list — see [`docs/policy.md`](./policy.md) |
| `connector` | string | no | `dbt` (default `datahub`), `snowflake`, `datahub`, or a registered custom name |

**Response:**

```json
{
  "plan_id": "plan-7a8a7a21",
  "asset_urn": "urn:dbt:model:jaffle_shop:orders",
  "objective": "minimize incident risk",
  "candidates": [...],
  "ranked_choice": {
    "future_id": "future-001",
    "asset_urn": "urn:dbt:model:jaffle_shop:orders",
    "scenario_type": "schema_remove",
    "change": { "removed_columns": ["customer_name"] },
    "predicted_severity": 88,
    "predicted_effort": 12,
    "predicted_benefit": 75,
    "predicted_blast_radius": 3,
    "confidence": 0.85,
    "evidence": ["..."],
    "affected_dashboards": 1,
    "affected_models": 1,
    "affected_pipelines": 0
  },
  "rationale": "Removed customer_name breaks 3 downstream assets...",
  "explanation": ["..."],
  "policy_result": {
    "verdict": "block",
    "results": [
      {
        "policy_name": "Block critical-severity changes",
        "verdict": "block",
        "reason": "severity 88 exceeds max 75",
        "trigger_values": { "severity": 88, "blast_radius": 3 }
      }
    ]
  },
  "created_at": "2026-08-01T12:00:00.000Z"
}
```

**Status codes:**

| Code | Meaning |
|------|---------|
| 200 | Plan generated |
| 400 | Invalid URN, missing `asset_urn`, or connector misconfigured |
| 404 | Asset not found in the chosen connector's graph |
| 500 | Engine failure |

### `GET /future-search/connectors`

List registered connectors.

```bash
curl http://localhost:8000/future-search/connectors
```

```json
{ "connectors": ["datahub", "dbt", "snowflake"] }
```

---

## Policy

### `GET /policy/defaults`

Returns the server-side default policy list — applied when the user
provides neither inline policies nor a `cortex.yml`.

```bash
curl http://localhost:8000/policy/defaults
```

```json
{
  "policies": [
    { "name": "Block critical-severity", "max_severity": 75, "max_blast_radius": 10, "action": "block" },
    { "name": "Warn on ML downstream impact", "max_severity": 50, "max_blast_radius": 3, "action": "warn" }
  ]
}
```

### `GET /policy/examples`

Returns a curated set of example policies to copy/paste.

```bash
curl http://localhost:8000/policy/examples
```

### `POST /policy/validate`

Dry-run a policy list against hypothetical severity and blast-radius
values. Used by the "tweak loop" in the UI.

```bash
curl -X POST http://localhost:8000/policy/validate \
  -H "Content-Type: application/json" \
  -d '{
    "policies": [
      { "name": "Block critical", "max_severity": 75, "action": "block" }
    ],
    "severity": 88,
    "blast_radius": 3,
    "has_owner": true
  }'
```

```json
{
  "verdict": "block",
  "results": [
    {
      "policy_name": "Block critical",
      "verdict": "block",
      "reason": "severity 88 exceeds max 75",
      "trigger_values": { "severity": 88, "blast_radius": 3, "has_owner": true }
    }
  ]
}
```

---

## Assets

### `GET /assets/{urn}`

Returns the asset node metadata.

```bash
curl http://localhost:8000/assets/urn%3Adbt%3Amodel%3Ajaffle_shop%3Aorders
```

### `GET /assets/{urn}/lineage`

Returns upstream + downstream neighbors.

```bash
curl http://localhost:8000/assets/urn%3Adbt%3A...%3Aorders/lineage
```

### `GET /assets/{urn}/graph`

Returns the full graph snapshot for the asset's lineage.

```bash
curl http://localhost:8000/assets/urn%3Adbt%3A...%3Aorders/graph
```

---

## Scenarios

### `POST /scenarios/simulate`

Apply a hypothetical scenario to a snapshot. Returns the modified
snapshot.

```bash
curl -X POST http://localhost:8000/scenarios/simulate \
  -H "Content-Type: application/json" \
  -d '{
    "asset_urn": "urn:dbt:model:jaffle_shop:orders",
    "scenario_type": "schema_remove",
    "change": { "removed_columns": ["customer_name"] }
  }'
```

---

## Impact

### `POST /impact/analyze`

Compute the blast radius from a scenario result.

```bash
curl -X POST http://localhost:8000/impact/analyze \
  -H "Content-Type: application/json" \
  -d @scenario_result.json
```

---

## Recommendations

### `POST /recommendations/generate`

Generate a recommended action from an impact report.

```bash
curl -X POST "http://localhost:8000/recommendations/generate?scenario_type=schema_remove" \
  -H "Content-Type: application/json" \
  -d @impact_report.json
```

---

## Artifacts

### `POST /artifacts/generate`

Generate a remediation artifact (SQL patch, dbt model, DAG patch,
markdown) from a recommendation.

```bash
curl -X POST "http://localhost:8000/artifacts/generate?scenario_type=schema_remove&asset_name=orders" \
  -H "Content-Type: application/json" \
  -d @recommendation.json
```

---

## Write-back

### `POST /writeback`

Record a resolution (the auditor's view of "we triaged this").

```bash
curl -X POST http://localhost:8000/writeback \
  -H "Content-Type: application/json" \
  -d '{
    "asset_urn": "...",
    "impact_report": {...},
    "recommendation": {...},
    "artifact": {...}
  }'
```

### `GET /writeback/assets/{urn}/resolutions`

List all resolutions recorded for an asset.

```bash
curl http://localhost:8000/writeback/assets/urn%3Adbt%3A...%3Aorders/resolutions
```

---

## Autopilot

### `GET /autopilot/status`

Cortex Autopilot background-worker status.

```bash
curl http://localhost:8000/autopilot/status
```

```json
{
  "running": true,
  "last_tick": "2026-08-01T12:00:00Z",
  "drift_detected": false,
  "open_incidents": 0
}
```

### `POST /autopilot/trigger`

Trigger an Autopilot task manually.

```bash
curl -X POST http://localhost:8000/autopilot/trigger \
  -H "Content-Type: application/json" \
  -d '{ "asset_urn": "...", "task": "remediate" }'
```

---

## Demo

### `POST /demo/run`

Run the full demo flow in one call (used by the homepage).

```bash
curl -X POST http://localhost:8000/demo/run \
  -H "Content-Type: application/json" \
  -d '{
    "asset_urn": "urn:dbt:model:jaffle_shop:orders",
    "scenario_type": "schema_remove",
    "change": { "removed_columns": ["customer_name"] }
  }'
```

---

## SDKs

- **Python:** Use `httpx` (see `examples/demo/run_demo.py`).
- **TypeScript:** Use the `frontend/lib/api.ts` wrapper.
- **Go / Java / Ruby:** Just `curl` — every endpoint is documented above.

---

## Rate Limits

| Endpoint | Default Limit |
|----------|---------------|
| `GET /health*` | 600/min |
| `GET /version`, `GET /metrics` | 600/min |
| `POST /future-search/run` | 60/min |
| `POST /policy/validate` | 600/min (it's cheap) |
| All others | 120/min |

Override via `RATE_LIMIT_PER_MINUTE` env var.
