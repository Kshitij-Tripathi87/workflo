# Cortex Autopilot — Connectors

Connectors are how Cortex discovers assets and reads schema metadata.
The engine itself is connector-agnostic; every connector implements the
same `BaseConnector` interface and contributes to a shared `GraphSnapshot`.

## Built-in Connectors

| Connector | Source | Mode | Auth |
|-----------|--------|------|------|
| `dbt` | `manifest.json` + `catalog.json` | File-based | None (file read) |
| `snowflake` | `INFORMATION_SCHEMA` | Live or mock | Password / private key |
| `datahub` | DataHub GMS GraphQL/REST | Live or mock | Personal Access Token |

## Common Configuration

Every connector is selected by passing `connector: <name>` to
`POST /future-search/run`. The default is `datahub`.

If a connector is not configured, it will appear in
`/health/detailed` with `status: "not_configured"`. The engine skips
it and returns a clear error pointing at the missing config.

## dbt Connector

Reads `manifest.json` and `catalog.json` from a dbt project. No live
database connection is required — perfect for CI.

### Configuration

Set the paths via environment variables:

```bash
export CORTEX_DBT_MANIFEST_PATH=/path/to/dbt/target/manifest.json
export CORTEX_DBT_CATALOG_PATH=/path/to/dbt/target/catalog.json
```

If `manifest.json` doesn't exist, the connector raises
`CONNECTOR_MANIFEST_MISSING`. The fix is to run `dbt compile` or
`dbt docs generate` first.

### URN scheme

```
urn:dbt:model:<project>:<model_name>
urn:dbt:source:<source_name>:<table>
urn:dbt:seed:<project>:<seed_name>
urn:dbt:snapshot:<project>:<snapshot_name>
```

### Caching

Snapshots are cached based on the manifest file's mtime + size. If the
file hasn't changed, repeated calls within the TTL (~30s) skip the
parse phase entirely.

### Best practice: GitHub Actions cache

Add this step before running the Cortex Action to avoid re-downloading
the manifest on every PR:

```yaml
- name: Cache dbt artifacts
  uses: actions/cache@v4
  with:
    path: |
      target/manifest.json
      target/catalog.json
    key: ${{ runner.os }}-dbt-${{ hashFiles('**/dbt_project.yml', 'models/**/*.sql') }}
```

## Snowflake Connector

Queries `INFORMATION_SCHEMA.COLUMNS` and `INFORMATION_SCHEMA.TABLES`
to build the asset graph.

### Configuration

```bash
# Required for real (non-mock) connection
export CORTEX_SNOWFLAKE_ACCOUNT=xy12345.us-east-1
export CORTEX_SNOWFLAKE_USER=cortex_service
export CORTEX_SNOWFLAKE_DATABASE=PROD

# Auth: one of these
export CORTEX_SNOWFLAKE_PASSWORD=...
# OR
export CORTEX_SNOWFLAKE_PRIVATE_KEY_PATH=/secrets/snowflake_rsa.p8

# Optional
export CORTEX_SNOWFLAKE_WAREHOUSE=ANALYTICS_WH
export CORTEX_SNOWFLAKE_SCHEMA=PUBLIC
export CORTEX_SNOWFLAKE_ROLE=CORTEX_ROLE

# Mock mode (no real connection — uses fixture data)
export CORTEX_SNOWFLAKE_MOCK=true
```

### Required Snowflake permissions

For the production connector:

```sql
GRANT USAGE ON DATABASE PROD TO ROLE CORTEX_ROLE;
GRANT USAGE ON ALL SCHEMAS IN DATABASE PROD TO ROLE CORTEX_ROLE;
GRANT SELECT ON ALL TABLES IN SCHEMA PUBLIC TO ROLE CORTEX_ROLE;
GRANT SELECT ON INFORMATION_SCHEMA.TABLES TO ROLE CORTEX_ROLE;
GRANT SELECT ON INFORMATION_SCHEMA.COLUMNS TO ROLE CORTEX_ROLE;
```

The connector **only** reads metadata. It does not query table data.

### URN scheme

```
urn:snowflake:table:<DATABASE>.<SCHEMA>.<TABLE>
```

### Mock mode

For testing and offline development, set `CORTEX_SNOWFLAKE_MOCK=true`.
The connector will return a fixture-based graph (10 tables, ~30
columns). Useful for unit tests and demos.

## DataHub Connector

Queries DataHub GMS (GraphQL or REST) for asset metadata, lineage, and
ownership.

### Configuration

```bash
# Live DataHub
export DATAHUB_BASE_URL=http://datahub-gms:8080
export DATAHUB_TOKEN=<personal-access-token>
export USE_MOCK_DATAHUB=false

# Mock mode (no DataHub required)
export USE_MOCK_DATAHUB=true
```

### Required DataHub permissions

The PAT must have:
- `Read entities` permission
- `Read lineages` permission
- `Read aspects` permission

For a self-hosted DataHub, the env var is `DATAHUB_GMS_TOKEN`. For
DataHub Cloud, generate a token in **Settings → Access Tokens**.

### URN scheme

```
urn:li:dataset:(urn:li:dataPlatform:<platform>,<name>,<env>)
```

### Rate limits

The connector respects DataHub's rate limits (default 10 RPS). Override
via `DATAHUB_RATE_LIMIT_RPS`.

## Custom Connectors

Build your own connector in **one Python file**:

```python
# backend/app/connectors/my_source/connector.py
from app.connectors.base import BaseConnector
from app.connectors.registry import register
from app.models.asset import GraphSnapshot

class MyConnector(BaseConnector):
    async def connect(self) -> bool:
        # Initialize any clients here
        return True

    async def get_asset(self, urn: str) -> AssetNode:
        # Resolve URN to an AssetNode
        ...

    async def get_upstream(self, urn: str) -> list[str]:
        ...

    async def get_downstream(self, urn: str) -> list[str]:
        ...

    async def build_snapshot(self, center_urns: list[str]) -> GraphSnapshot:
        # Build the local graph view
        ...

register("my_source", MyConnector)
```

### Rules

- **Single Python file.** Keep the connector ≤ 500 lines.
- **URN scheme.** Follow a documented `urn:<namespace>:<type>:<id>`
  pattern.
- **Async.** All connector methods are `async`.
- **Idempotent connect/disconnect.** The engine may call these many
  times in a long-running process.
- **Error handling.** Raise the structured exceptions from
  `app.core.exceptions` (`ConnectorManifestMissingError`,
  `ConnectorNotConfiguredError`, `ConnectorConnectionError`).

### Registering

Drop the file into `backend/app/connectors/<your_connector>/connector.py`.
It will be auto-imported and registered at startup.

### Testing

Add tests under `backend/tests/test_<your_connector>_connector.py`.
Cover:
- The connector appears in `list_connectors()`.
- `build_snapshot` returns the expected number of nodes/edges.
- An invalid URN raises `KeyError`.

## When to Build a Custom Connector

Only when:

- None of the built-in connectors cover your source.
- The data source has stable schema metadata.
- The cost of a custom connector is < the cost of a CSV-to-dbt
  intermediate layer.

If you're tempted to build a connector for a one-off source, it's
probably cheaper to model the source in dbt and let the existing
`dbt` connector pick it up.

## Adding a Connector to the Engine (Roadmap)

The community is most likely to ask for: BigQuery, Databricks, Unity
Catalog, OpenMetadata, Airflow DAGs, Dagster, Kafka topics.

We build a connector when **3 paying customers request it**. See
[`docs/business/feature_requests.md`](./business/feature_requests.md)
for the current backlog.
