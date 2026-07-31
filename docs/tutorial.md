# Tutorial — Gate Your First Data PR

This tutorial walks you through running Cortex Autopilot end-to-end on
the bundled sample dbt project. You'll simulate a "risky change," watch
the engine compute the blast radius, see the verdict, and review the PR
comment and Slack alert the GitHub Action would generate.

**Time to complete:** 15 minutes.

**What you'll need:** Docker running, the Cortex Autopilot stack up
(see [`install.md`](./install.md)), and a terminal.

---

## What we're simulating

The sample dbt project (`examples/sample_dbt_project/`) is a small
analytics warehouse with:

- 2 source tables (`raw.orders`, `raw.customers`)
- 3 staging models (`stg_orders`, `stg_customers`)
- 3 core models (`orders`, `customer_ltv`, `dashboard_feed`)

The `orders` model has a column `customer_name` that is consumed by:

- `dashboard_feed` (a downstream table that joins revenue + LTV)
- `customer_ltv` (an ML feature pipeline)

A data engineer proposes dropping the `customer_name` column. Without
Cortex, this would silently break two downstream assets. With Cortex,
it's caught in the PR.

---

## Step 1 — Run the baseline

Open a terminal at the repo root and confirm the backend is healthy:

```bash
curl http://localhost:8000/health
```

You should see `{"status":"ok","env":"dev"}`.

Run the demo runner against the sample project:

```bash
python examples/demo/run_demo.py
```

You'll see:

```
manifest.json : examples/sample_dbt_project/target/manifest.json
catalog.json  : examples/sample_dbt_project/target/catalog.json
cortex.yml    : examples/sample_dbt_project/cortex.yml
server        : http://localhost:8000

[ok] backend healthy: {'status': 'ok', 'env': 'dev'}
[ok] registered connectors: ['datahub', 'dbt', 'snowflake']

============================================================
POST /future-search/run
============================================================
{...}
```

This is the engine inspecting the baseline manifest and reporting on
the current state of `orders`.

## Step 2 — Simulate the risky change

The demo runner always uses the manifest as-is. To simulate the
proposed change, edit `examples/sample_dbt_project/cortex.yml` and
tell the engine which columns are being removed:

```yaml
asset_urn: "urn:dbt:model:jaffle_shop:orders"

change:
  action: "schema_remove"
  removed_columns: ["customer_name"]

policies:
  - name: Block critical-severity changes
    max_severity: 75
    max_blast_radius: 5
    action: block

  - name: Warn on ML downstream impact
    max_severity: 50
    max_blast_radius: 3
    action: warn

objective: minimize incident risk
```

Save and re-run:

```bash
python examples/demo/run_demo.py
```

## Step 3 — Read the verdict

The runner prints the verdict, the PR comment, and the Slack alert.

### The PR comment

```
## ⛔ Cortex Autopilot BLOCK

**Asset:** urn:dbt:model:jaffle_shop:orders
**Severity:** CRITICAL (88/100)
**Verdict:** BLOCK — change cannot merge

### Blast Radius
- 3 downstream assets affected
- 1 critical dashboard
- 1 ML feature pipeline
- 1 finance report

### Why this was blocked
- customer_name is consumed by dashboard.revenue_dashboard
- customer_name is consumed by model.churn_features
- customer_name is consumed by report.finance_summary

### Recommended action
Generate a SQL compatibility view that aliases customer_name to a
placeholder, then deprecate the column after downstream consumers migrate.
```

### The Slack alert

```json
{
  "channel": "#data-platform",
  "text": ":rotating_light: *Cortex Autopilot BLOCK*\n..."
}
```

The verdict is `BLOCK` because the predicted severity (88) exceeds the
policy threshold (75). The engine correctly identified three downstream
assets that would break.

## Step 4 — Try the policy tweak loop

The "tweak loop" is what makes Cortex valuable in code review. Move the
`max_severity` threshold up and see the verdict change without re-running
the full graph:

```bash
curl -X POST http://localhost:8000/policy/validate \
  -H "Content-Type: application/json" \
  -d '{
    "policies": [
      { "name": "Block critical-severity changes", "max_severity": 95, "action": "block" }
    ],
    "severity": 88,
    "blast_radius": 3,
    "has_owner": true
  }'
```

Move `max_severity` from 75 → 95 and the verdict flips to `pass`.
The engineer can now merge — at the cost of accepting a critical-severity
change with 3 affected downstream assets.

This is exactly the workflow that lives in the UI's **Policy Tweaker**.

## Step 5 — A safe change

Now try a safe change. Edit `cortex.yml`:

```yaml
change:
  action: "schema_add"
  added_columns: ["customer_email"]
```

Re-run the demo:

```bash
python examples/demo/run_demo.py
```

You'll see `Final verdict: PASS`. Adding a column doesn't break
downstream consumers (they simply ignore the new column).

## Step 6 — Promote to a real PR

Open a new git branch in the sample dbt project:

```bash
cd examples/sample_dbt_project
git checkout -b demo/drop-customer-name
git add cortex.yml
git commit -m "demo: drop customer_name from orders"
```

If you have GitHub CLI configured:

```bash
gh pr create --title "drop customer_name" --body "demo"
```

The repo's GitHub Actions workflow (`.github/workflows/cortex-gate.yml`)
will run the **Cortex Impact Gate** action on the PR. The action
posts the same comment you just saw locally and fires the same Slack
alert.

---

## What just happened

You:

1. Loaded a real dbt manifest into the engine.
2. Described a hypothetical change in `cortex.yml`.
3. Called the future-search endpoint and received a verdict.
4. Toggled the policy threshold and saw the verdict flip in real time.
5. Confirmed the safe-change path produces a `pass`.

In production:

- A developer opens a PR.
- The GitHub Action does steps 1–4 automatically.
- A reviewer sees the verdict in the PR comment and Slack.

That's the whole product.

---

## Where to next?

- **Production policy authoring**: [`docs/policy.md`](./policy.md)
- **Customizing the engine**: [`docs/api.md`](./api.md)
- **Adding a custom connector**: [`docs/connectors.md`](./connectors.md)
- **Recording resolutions**: see `POST /writeback` in the API reference.
