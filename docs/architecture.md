# Architecture

## Overview

Cortex Autopilot is a **digital twin for data systems** that simulates changes, predicts impact, and generates remediation artifacts.

## System Flow

```
DataHub Context (mock or real)
        ↓
Context Adapter (datahub_client)
        ↓
Graph Snapshot (nodes + edges)
        ↓
┌───────────────────────────────────────┐
│  Future Search Engine (NEW)           │
│  - Generate 6 candidate futures       │
│  - Evaluate each via scenario+impact  │
│  - Rank by risk/effort/benefit        │
│  - Return optimal action + why        │
└───────────────────────────────────────┘
        ↓
Scenario Engine (simulate individual changes)
        ↓
Impact Engine (traverse + score)
        ↓
Recommendation Engine (select action)
        ↓
Recommendation Ranker (rank candidates)
        ↓
Explanation Builder (evidence-backed why)
        ↓
Artifact Generator (produce fix)
        ↓
Write-back Layer (record resolution)
        ↓
Frontend Control Room (UI)
```

## Core Components

### Backend (FastAPI)

| Component | Purpose |
|-----------|---------|
| `datahub_client` | Single boundary for DataHub access (mock or real) |
| `graph_builder` | Converts asset metadata into local graph snapshot |
| **`future_search_engine`** | **Generates and ranks candidate futures (NEW)** |
| **`recommendation_ranker`** | **Scores and ranks futures by risk/effort/benefit (NEW)** |
| **`explanation_builder`** | **Produces evidence-backed reasoning (NEW)** |
| `scenario_engine` | Applies hypothetical changes deterministically |
| `impact_engine` | Traverses graph and scores consequences |
| `recommendation_engine` | Selects best remediation action |
| `artifact_generator` | Produces SQL/dbt/DAG/YAML/markdown artifacts |
| `writeback_service` | Persists resolution records to JSONL log |

### Models

| Model | Purpose |
|-------|---------|
| `AssetNode` | Canonical internal asset representation |
| `GraphEdge` | Directed edge with type and confidence |
| `GraphSnapshot` | Snapshot of asset graph for reasoning |
| `ScenarioRequest` / `ScenarioResult` | Simulated change input/output |
| `ImpactReport` | Blast-radius analysis with severity |
| `Recommendation` | Remediation plan with action type |
| `ArtifactDraft` | Generated fix artifact |
| `WritebackRecord` | Resolution record |
| **`FutureScenario`** | **Candidate future with predicted outcomes (NEW)** |
| **`FuturePlan`** | **Ranked plan with optimal choice (NEW)** |

### Frontend (Next.js)

| Component | Purpose |
|-----------|---------|
| `AssetPicker` | Search and select assets |
| `GraphSummary` | Display node/edge counts |
| `ScenarioForm` | Configure and trigger simulations |
| `ImpactPanel` | Show severity and affected assets |
| `RecommendationCard` | Display recommended action |
| `ArtifactPreview` | Preview generated fix |
| `WritebackStatus` | Show resolution status |
| `LineageGraph` | Visualize upstream/downstream |

## Scenario Types

1. **schema_rename** — Column renamed (e.g., `customer_name` → `name`)
2. **schema_remove** — Column removed
3. **owner_missing** — Owner unassigned
4. **pipeline_failure** — Pipeline status = failed
5. **dataset_deprecation** — Dataset marked deprecated

## Impact Scoring

Severity is computed from weighted factors:

| Factor | Weight |
|--------|--------|
| Downstream count | 10 per asset (max 30) |
| Depth | 15 per level (max 30) |
| Criticality | 0–40 (low to critical) |
| Owner gap | 15 |
| ML dependency | 20 |
| Pipeline failure | 20 |

**Bands:** 0–24 = low, 25–49 = medium, 50–74 = high, 75–100 = critical

## Recommendation Ranking

The Future Search engine evaluates multiple candidate actions and ranks them using a weighted scoring function:

```
score = benefit_weight * predicted_benefit
      - risk_weight * predicted_severity
      - effort_weight * predicted_effort
      + confidence_bonus
      - constraint_penalty
```

Weights adjust based on the stated objective:

| Objective | Risk Weight | Effort Weight | Benefit Weight |
|-----------|-------------|---------------|----------------|
| minimize incident risk | 0.60 | 0.15 | 0.25 |
| minimize effort | 0.25 | 0.55 | 0.20 |
| maximize reliability | 0.55 | 0.20 | 0.25 |
| balance cost and risk | 0.35 | 0.35 | 0.30 |

This makes the recommendation **explainable** rather than appearing to invent numbers. Every score can be traced back to:
- The stated objective
- The applied weights
- The constraint penalties
- The underlying impact analysis evidence

## Recommendation Rules (Legacy)

The original recommendation engine uses rule-based selection for individual scenarios. The Future Search engine supersedes this by evaluating multiple scenarios and ranking them.

| Scenario | Primary Action | Fallback |
|----------|---------------|----------|
| schema_rename | patch_sql | patch_dbt |
| schema_remove | patch_sql | create_temp_view |
| owner_missing | assign_owner | escalate |
| pipeline_failure | patch_dag | rollback_change |
| dataset_deprecation | archive_asset | escalate |

## Write-back

Resolutions are persisted to `backend/data/writeback.jsonl` as newline-delimited JSON. Each record contains:

- `record_id`, `asset_urn`, `status`
- `summary`, `linked_artifact`
- `affected_assets`, `created_by`, `created_at`

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/assets/{urn}` | GET | Get asset summary |
| `/assets/{urn}/lineage` | GET | Get lineage |
| `/assets/{urn}/graph` | GET | Get graph snapshot |
| `/scenarios/simulate` | POST | Simulate change |
| `/impact/analyze` | POST | Analyze impact |
| `/recommendations/generate` | POST | Generate recommendation |
| `/artifacts/generate` | POST | Generate artifact |
| `/writeback` | POST | Record resolution |
| `/demo/run` | POST | Run full demo flow |
| **`/future-search/run`** | **POST** | **Generate and rank futures (NEW)** |