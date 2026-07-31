# Install Cortex Autopilot

This guide gets you from zero to your first Cortex verdict in **under 10 minutes**.

## 1. Prerequisites

You'll need:

| Tool | Version | Why |
|------|---------|-----|
| Docker | 24+ | Runs the backend, frontend, and Postgres |
| Node.js | 18+ | Builds the frontend (optional, only if you want to run from source) |
| Python | 3.11+ | Builds the backend (optional) |
| dbt | 1.5+ | If you want to gate a real dbt project |
| Git | 2.30+ | Clones the repo |

If you don't have Docker yet, install it from [docs.docker.com/get-docker](https://docs.docker.com/get-docker/).

## 2. Clone the repo

```bash
git clone https://github.com/cortex-autopilot/cortex-autopilot.git
cd cortex-autopilot
```

## 3. Configure secrets

```bash
cp compose.env.example compose.env
```

Open `compose.env` in your editor and set `POSTGRES_PASSWORD` to something
strong. The other defaults are fine for a local install.

## 4. One-command setup

```bash
./setup.sh
```

This script will:

1. Start Postgres + backend via `docker compose`.
2. Wait until the backend responds to `/health`.
3. Install frontend dependencies (`npm install`).
4. Start the frontend container.
5. Print the detailed health report.
6. Open `http://localhost:3000` in your default browser.

If you'd rather run the steps manually, see
[`docs/setup.md`](./setup.md) for the explicit instructions.

## 5. Verify the install

Open `http://localhost:3000` in your browser. You should see the
**Cortex Autopilot** header and the empty control room.

Open `http://localhost:8000/health/detailed`. You should see:

```json
{
  "status": "ok",
  "version": "0.3.0",
  "name": "Cortex Autopilot",
  "env": "dev",
  "uptime_seconds": 14.2,
  "connectors": {
    "dbt": { "status": "not_configured" },
    "snowflake": { "status": "mock" },
    "datahub": { "status": "mock" }
  }
}
```

## 6. Run the demo

The repo ships with a sample dbt project under `examples/sample_dbt_project/`.
Run the demo runner against it:

```bash
python examples/demo/run_demo.py
```

This will:

1. Load `examples/sample_dbt_project/target/manifest.json`.
2. Call `POST /future-search/run` on the local backend.
3. Print the verdict, the PR comment the GitHub Action would post, and
   the Slack Block Kit payload.

Expected output ends with `Final verdict: BLOCK` because the default
policy in the sample project blocks on critical severity.

## 7. Point Cortex at your own dbt project

```bash
export CORTEX_DBT_MANIFEST_PATH=/path/to/your/dbt/project/target/manifest.json
export CORTEX_DBT_CATALOG_PATH=/path/to/your/dbt/project/target/catalog.json
```

Restart the backend:

```bash
docker compose --env-file compose.env restart backend
```

Re-run the health check:

```bash
curl http://localhost:8000/health/detailed | python -m json.tool
```

You should now see:

```json
{ "connectors": { "dbt": { "status": "connected", "path": "..." } } }
```

## 8. Wire up the GitHub Action

In your dbt project's repo:

1. Commit a `cortex.yml` at the repo root (see
   [`docs/policy.md`](./policy.md) for the format).
2. Add the workflow at `.github/workflows/cortex-gate.yml`:

```yaml
name: Cortex Autopilot Impact Gate
on:
  pull_request:
    paths: ["models/**", "macros/**", "cortex.yml"]
jobs:
  cortex-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 2
      - uses: cortex-autopilot/impact-gate@v1
        with:
          cortex_server: ${{ secrets.CORTEX_SERVER_URL }}
          api_token: ${{ secrets.CORTEX_API_TOKEN }}
          slack_webhook: ${{ secrets.SLACK_WEBHOOK_URL }}
```

The action posts a PR comment, fires a Slack alert on `warn` / `block`,
and exits 1 when the verdict is `block`.

## 9. Configure Slack (optional)

Create an Incoming Webhook in your Slack workspace and paste the URL
into `SLACK_WEBHOOK_URL` (or the action input). Cortex sends a Block
Kit message whenever the verdict is `warn` or `block`.

## 10. Where to next?

- **Tutorial**: [`docs/tutorial.md`](./tutorial.md) — end-to-end walkthrough
  on a real dbt project.
- **Policy authoring**: [`docs/policy.md`](./policy.md) — the policy YAML
  format and the hierarchy resolution rules.
- **Connectors**: [`docs/connectors.md`](./connectors.md) — dbt, Snowflake,
  DataHub, and the connector SDK for custom sources.
- **API reference**: [`docs/api.md`](./api.md) — every endpoint with curl
  examples.
- **Demo script**: [`docs/demo_script.md`](./demo_script.md) — the 5-minute
  customer demo narrative.

## Troubleshooting

### Backend won't start

```
docker compose --env-file compose.env logs backend
```

Common causes:

- `POSTGRES_PASSWORD` not set in `compose.env`.
- Port `8000` already in use. Edit `docker-compose.yml` and remap.

### `dbt` connector status is `unreachable`

```
curl http://localhost:8000/health/detailed | jq '.connectors.dbt'
```

- Verify the manifest path is correct and the file is readable.
- If you're running the backend in Docker, the path must be reachable
  from inside the container. Mount your dbt project as a volume in
  `docker-compose.yml`.

### Frontend shows "Connection refused"

- The backend container isn't healthy yet. Wait 30 seconds and refresh.
- Check that `NEXT_PUBLIC_API_BASE_URL` in `frontend/.env` points to
  `http://localhost:8000`.

### Slack alert doesn't fire

- Webhook URL is wrong or revoked. Test with `curl` directly:

  ```bash
  curl -X POST "$SLACK_WEBHOOK_URL" \
    -H "Content-Type: application/json" \
    -d '{"text": "Cortex test"}'
  ```

- Cortex only sends Slack alerts for `warn` and `block` verdicts.
  `pass` is intentionally silent.
