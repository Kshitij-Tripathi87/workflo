# Product Requirements Document — Cortex Autopilot v1.0

> **Status:** Feature complete. This document describes the v1.0 product as built. Any v1.1+ work must come from the [Feature Request Backlog](./business/feature_requests.md) and meet the three-customer bar.

## Problem

Data engineering teams run dbt in production to transform warehouse
data into tables that feed dashboards, ML pipelines, and finance
reports. When a data engineer changes a column — renames, removes,
changes a type — the change can silently break every downstream
consumer. Detection typically takes hours to days; resolution takes
hours; the cost is lost analyst trust and broken executive reports.

Existing tooling (dbt tests, observability platforms, code review) does
not prevent this. dbt tests verify the *producer*, not the *consumer*.
Observability tools detect after the change has shipped. Code review
cannot see the full downstream graph.

## Target Buyer

**Buyer persona:** Head of Data Platform or Director of Data
Engineering at a company with 50–1,000 employees and a data team of
3–25 engineers. The buyer owns MTTD, MTTR, and schema-change policy.

**Champion persona:** Senior Data Engineer or Analytics Engineer who
runs dbt daily and gets paged when downstream breaks.

## Target Outcome

Reduce schema-related incidents by ~70% within the first month of
deployment. The metric is **incidents per quarter** in the buyer's
incident tracker.

## Core Loop

```
Developer opens PR
        ↓
GitHub Action triggers Cortex Impact Gate
        ↓
dbt connector reads target/manifest.json
        ↓
Engine computes blast radius and severity
        ↓
Policy engine evaluates the ranked_choice
        ↓
Verdict: pass / warn / block
        ↓
PR comment posted
        ↓
Slack alert (on warn / block)
        ↓
Merge button disabled (on block)
```

## Functional Requirements (v1.0)

### F1. Engine

- F1.1 Build a `GraphSnapshot` from a connector input (dbt / Snowflake / DataHub).
- F1.2 Traverse the snapshot to compute blast radius (downstream count + depth).
- F1.3 Compute severity score (0–100) using weighted factors: downstream count, depth, criticality, owner gap, ML dependency, pipeline failure.
- F1.4 Rank candidate remediation actions (patch_sql, patch_dbt, patch_dag, create_temp_view, archive_asset, escalate, assign_owner, do_nothing).
- F1.5 Return a `FuturePlan` with `ranked_choice`, `candidates`, `rationale`, and `explanation`.

### F2. Policy

- F2.1 Evaluate a list of `Policy` objects against the `ranked_choice`.
- F2.2 Support `max_severity`, `max_blast_radius`, `require_owner` fields.
- F2.3 Combine verdicts: `block` dominates `warn` dominates `pass`.
- F2.4 Resolve policy hierarchy: action input > `cortex.yml` > backend defaults.

### F3. GitHub Action

- F3.1 Detect schema changes from `git diff`.
- F3.2 Call `POST /future-search/run` with the connector and policies.
- F3.3 Post a structured markdown PR comment with verdict, severity, blast radius, evidence, and recommended action.
- F3.4 Send a Slack Block Kit alert on `warn` and `block` verdicts.
- F3.5 Exit 1 on `block` to disable the merge button.

### F4. Connectors

- F4.1 dbt: parse `manifest.json` + `catalog.json`. No live connection required.
- F4.2 Snowflake: query `INFORMATION_SCHEMA.COLUMNS` and `TABLES`. Mock mode for offline.
- F4.3 DataHub: query GMS GraphQL/REST. Mock mode for offline.
- F4.4 Custom connector SDK: implement `BaseConnector` in one Python file.

### F5. UI

- F5.1 Asset picker with type-ahead search.
- F5.2 Graph summary panel showing nodes/edges.
- F5.3 Scenario form for simulating changes.
- F5.4 Impact panel with severity and affected assets.
- F5.5 Recommendation card with evidence-backed rationale.
- F5.6 Artifact preview for the generated SQL/dbt/DAG patch.
- F5.7 Write-back status indicator.
- F5.8 Future Search panel for ranked multi-future comparison.
- F5.9 Verdict primacy — the verdict is the largest UI element on the page.
- F5.10 Policy Tweaker — interactive sliders with real-time verdict flip.
- F5.11 Loading skeletons for async operations.

### F6. Operations

- F6.1 `/health` and `/health/detailed` for Docker healthcheck.
- F6.2 Prometheus `/metrics` endpoint.
- F6.3 JSON structured logging via `structlog`.
- F6.4 TTL-based graph snapshot cache.
- F6.5 Env var validation at startup (fail-fast).
- F6.6 One-command setup via `./setup.sh`.

## Non-Goals (v1.0)

The following are **explicitly out of scope** for v1.0:

- ❌ Autonomous remediation (no agent that fixes things without approval)
- ❌ AI-generated SQL patches
- ❌ Natural language interface
- ❌ RL-based outcome learning
- ❌ 30+ connectors
- ❌ Massive dashboard suite

## Success Metrics (v1.0)

### Product metrics

| Metric | Target (3 months post-launch) |
|--------|-------------------------------|
| Time from PR open to verdict | < 1 minute |
| Engine p95 latency | < 250 ms (measured: 0.06 ms in 10k synthetic) |
| False-positive rate | < 5% (measured: 2.7% in synthetic corpus) |
| False-negative rate | < 2% (measured: 0.0% in synthetic corpus) |
| Blast radius exact-match rate | > 80% (measured: 100% by construction) |

### Business metrics

| Metric | Target (12 months) |
|--------|--------------------|
| Discovery calls | 100 |
| Product demos | 50 |
| Design partners | 10 |
| Pilots | 5 |
| Paying customers | 3–5 |
| ARR | $50k–100k |
| Net Revenue Retention | > 100% |

## Architecture Constraints

- **Python 3.11+** for the backend (async/await throughout)
- **Next.js 14+** for the frontend
- **PostgreSQL 16+** for persistence
- **OpenAPI** for the API contract
- **Apache 2.0** for the open-source license

## Risks

| Risk | Mitigation |
|------|------------|
| Connector API changes break dbt / Snowflake parsing | Pin manifest schema versions; test against multiple dbt versions |
| Customers want features we don't have | Use the three-customer bar; maintain a public roadmap |
| Open-source contributors fork and don't contribute back | Trademark the name; clear license; CLA for major contributions |
| Wrong ICP — buyers don't actually have the pain | Track discovery-call outcomes weekly; adjust ICP |

## Dependencies

- dbt ≥ 1.5 (manifest schema v8+)
- Snowflake ACCOUNT, USER, DATABASE for live mode
- DataHub GMS ≥ 0.13 for live mode
- Slack workspace with admin permission to create incoming webhooks

## Release Plan

- **Internal:** v1.0-rc.1 → v1.0-rc.2 (2 weeks, design partner feedback)
- **Public beta:** v1.0.0-beta (4 weeks, 50 signups)
- **General availability:** v1.0.0 (8 weeks)

## Open Questions

- Should the GitHub Action be published as a GitHub App? (Track C roadmap item)
- Should we offer a hosted version with multi-tenant policy library? (Track D pricing)
- What's the right pricing tier for the open-source edition? (Free, by definition)
