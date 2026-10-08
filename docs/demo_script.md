# Cortex Autopilot — Working Demo

This demo walks through the **CI/CD Impact Gate** workflow: a developer opens a pull request that drops a critical column. The dbt connector detects the schema change, the policy engine evaluates the blast radius, the GitHub Action posts a structured PR comment, and Slack receives a real-time alert — all before the change reaches production.

---

## Prerequisites

- `docker compose up -d` (Postgres + backend + frontend)
- `pip install -r backend/requirements.txt`
- `npm install` inside `frontend/`
- A sample dbt repo at `examples/sample_dbt_project/` (ships with the repo)

---

## Step 1 — Baseline: the healthy state

```bash
# Inspect the baseline manifest
cat examples/sample_dbt_project/target/manifest.json | jq '.nodes | keys'
```

Expected output includes `model.jaffle_shop.orders` with columns `id`, `customer_id`, `customer_name`, `order_date`, `amount`.

**Say:** "Here is the baseline schema for our `orders` model. Three downstream assets depend on `customer_name` — a dashboard, an ML feature, and a finance report."

---

## Step 2 — The risky change

Open `examples/sample_dbt_project/models/orders.sql` and **delete** the `customer_name` column. Commit on a branch:

```bash
git checkout -b demo/drop-customer-name
git add models/orders.sql
git commit -m "drop customer_name from orders"
```

**Say:** "A data engineer proposes dropping the `customer_name` column from the `orders` model. In most data platforms this change would silently break three downstream assets."

---

## Step 3 — Open the PR and trigger the GitHub Action

```bash
gh pr create --title "drop customer_name" --body "demo"
gh pr edit --add-label cortex-demo
```

The repository's workflow (`.github/workflows/cortex-gate.yml`) runs the **Cortex Impact Gate** action, which:

1. Reads the new `manifest.json` and `catalog.json`
2. Calls the Cortex server's `POST /policy/evaluate`
3. Posts a PR comment with the verdict
4. Sends a Slack alert when the verdict is `warn` or `block`

---

## Step 4 — The PR comment

The GitHub Action posts a comment like this:

```
## ⛔ Cortex BLOCK

**Asset:** model.jaffle_shop.orders
**Severity:** critical (88 / 100)
**Verdict:** BLOCK — change cannot merge

### Blast Radius
- 3 downstream assets affected
- 1 critical dashboard
- 1 ML feature pipeline
- 1 finance report

### Why this was blocked
- `customer_name` is consumed by `dashboard.revenue_dashboard`
- `customer_name` is consumed by `model.churn_features`
- `customer_name` is consumed by `report.finance_summary`

### Recommended action
Generate a SQL compatibility view that aliases `customer_name` to a placeholder, then deprecate the column after downstream consumers migrate.
```

**Say:** "The developer gets instant, structured feedback — no more 'surprise in production.'"

---

## Step 5 — Slack alert

At the same time, the configured Slack webhook fires:

```json
{
  "channel": "#data-platform",
  "text": ":no_entry: *Cortex BLOCK* — model.jaffle_shop.orders",
  "blocks": [
    { "type": "section", "text": { "type": "mrkdwn", "text": "*Severity:* critical (88/100)\n*Downstream:* 3 assets" } },
    { "type": "actions", "elements": [
      { "type": "button", "text": { "type": "plain_text", "text": "View PR" }, "url": "..." }
    ]}
  ]
}
```

**Say:** "On-call data engineers see the alert in Slack before the change ships — MTTD drops from hours to seconds."

---

## Step 6 — The policy engine in action

To run the same evaluation **without** GitHub:

```bash
curl -X POST http://localhost:8000/policy/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "connector": "dbt",
    "manifest_path": "examples/sample_dbt_project/target/manifest.json",
    "catalog_path":  "examples/sample_dbt_project/target/catalog.json",
    "changed_node":  "model.jaffle_shop.orders",
    "removed_columns": ["customer_name"],
    "policy": {
      "block_on": ["critical", "high"],
      "warn_on":   ["medium"]
    }
  }'
```

Response:

```json
{
  "verdict": "block",
  "severity": "critical",
  "score": 88,
  "affected_assets": [
    "dashboard.revenue_dashboard",
    "model.churn_features",
    "report.finance_summary"
  ],
  "rationale": "Customer_name is read by 3 downstream assets including 1 critical dashboard."
}
```

---

## Step 7 — The Autopilot loop (background)

While the developer is reviewing the PR, the **Cortex Autopilot** background worker also runs:

1. Rebuilds the graph from the dbt manifest
2. Diffs against the previous snapshot stored in Postgres
3. Emits a `schema_drift` signal
4. Calls the agent to recommend a remediation
5. Records the resolution to the audit log

You can see the loop in action:

```bash
curl http://localhost:8000/autopilot/status
```

```json
{
  "running": true,
  "last_tick": "2026-07-28T05:42:11Z",
  "drift_detected": true,
  "open_incidents": 1
}
```

**Say:** "Cortex Autopilot doesn't wait for a human to file a ticket — it detects schema drift on its own and opens an incident with a recommended action."

---

## Step 8 — Approve a safe change

Now make a **safe** change: add a new column.

```bash
git checkout main
git checkout -b demo/add-index-column
echo "ALTER TABLE orders ADD COLUMN index INTEGER;" >> examples/sample_dbt_project/models/orders.sql
git commit -am "add index column"
gh pr create --title "add index column"
```

The GitHub Action runs again, this time producing:

```
## ✅ Cortex PASS

**Asset:** model.jaffle_shop.orders
**Severity:** low (12 / 100)
**Verdict:** PASS — safe to merge

No downstream consumers are affected by adding a new column.
```

**Say:** "Safe changes sail through. Risky changes are caught early. That's the Cortex Impact Gate."

---

## Closing

**Say:** "Cortex Autopilot moves data-platform governance from after-the-fact cleanup to before-the-fact prevention. Engineers keep velocity. Leaders keep trust."

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Action fails with `Could not reach Cortex server` | Make sure `docker compose up -d` is running and `http://localhost:8000/healthz` returns `ok` |
| Slack alert never arrives | Check `SLACK_WEBHOOK_URL` is set and the channel name matches |
| Policy always `pass` | Confirm `removed_columns` is non-empty in the request body |
| Manifest not detected | Run `dbt compile` first; the action expects `target/manifest.json` to exist |

---

## Next steps

1. Wire the action into your real dbt repo
2. Configure Slack channel and severity thresholds
3. Roll out to one team, measure MTTD for one week
4. Expand to all repos
