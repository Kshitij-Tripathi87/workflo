# From CI to data CI/CD: the missing gate

**Published:** 2026-09-01 · **7 min read** · **Author:** Cortex Autopilot

Software engineering spent 15 years building CI/CD gates for every
change category except one: data transformations. This post explains
how that happened, why it's changing, and what to do about it.

## The history of CI/CD

CI/CD isn't new. The first CI tools appeared in the 1990s (Make,
CruiseControl). The first CD tools in the 2000s (Capistrano, Fabric).
The first cloud-native CI in the 2010s (Jenkins, CircleCI, Travis).

Each generation added gates for a new category of change:

- **Code** → CI runs tests, lints, type-checks
- **Infrastructure** → Terraform Cloud runs `plan`, Atlantis applies with PR approval
- **Containers** → Docker registries, vulnerability scanning
- **Kubernetes manifests** → ArgoCD, Flux
- **ML models** → SageMaker Pipelines, Tecton
- **Database migrations** → Flyway, Liquibase, Atlas

But data transformations? Still in the dark ages.

## Why data is different

Three structural reasons:

### 1. The graph is implicit

Code has a dependency graph (imports, packages, modules) that's easy
to extract. Infrastructure has a graph (Terraform references). Even ML
models have a graph (training data → features → model → predictions).

Data transformations have a graph too — but it's encoded in
SQL. To extract it, you need a parser (like dbt's manifest.json) or a
metadata catalog (like DataHub). Most teams don't have either, or they
don't query them at PR time.

### 2. The cost of breakage is delayed

Code that breaks production usually breaks *loudly* — 500 errors,
failed health checks. Data that breaks production breaks *silently*:
the dashboard still renders, just with wrong numbers. By the time
someone notices, hours have passed.

### 3. The reviewers are data engineers, not the data owner

Code reviewers are often the same people who wrote the code. Data
reviewers are often different — the data engineer who changed the
model is rarely the analyst who uses the dashboard. The reviewer
literally cannot know what they're breaking.

## The three waves of data quality tooling

### Wave 1: dbt tests (2018–2020)

dbt popularized the idea of testing data transformations. `unique`,
`not_null`, `accepted_values`, `relationships` — these are excellent
tests for *column-level quality*. They run at build time.

**Limitation:** they test the producer, not the consumer. A model can
pass all its tests and still break every downstream consumer.

### Wave 2: observability platforms (2020–2023)

Monte Carlo, Bigeye, Soda, Datafold — these tools detect *data*
anomalies (freshness, volume, schema drift). They run on a schedule
and detect *after* the change has shipped.

**Limitation:** they're post-hoc. By the time they detect, downstream
assets have already broken.

### Wave 3: PR-time gates (2024–)

Cortex Autopilot, plus a handful of newer entrants. The approach:
read the schema graph at PR time, compute blast radius, enforce policy
before the change ships.

**The thesis:** the same CI gate that catches a buggy code change can
catch a broken data change — if you have the right graph and the
right policy engine.

## What a data CI/CD workflow looks like

```
Developer opens PR modifying dbt models
        ↓
GitHub Action triggers Cortex Impact Gate
        ↓
dbt manifest is parsed (cached, ~5 ms)
        ↓
Graph snapshot is built
        ↓
Engine traverses downstream
        ↓
Severity + blast radius computed
        ↓
Policies evaluated against the ranked_choice
        ↓
Verdict emitted: pass / warn / block
        ↓
PR comment posted with structured table
        ↓
Slack alert fired (warn / block only)
        ↓
Merge button disabled (block only)
```

This is the same shape as a code CI gate: parse inputs, evaluate
rules, emit a verdict, take an action.

## What makes a good data CI gate

Three properties:

### 1. It's fast

The verdict must arrive in seconds. Engineers won't wait for a 5-minute
engine job on every PR. Cortex targets < 1 second p99.

### 2. It's explainable

When the engine blocks, the engineer asks "why?". The engine must
answer with:

- Which downstream assets are affected
- What severity band the change falls into
- Which policy rule fired
- What the recommended action is

Black-box ML doesn't pass this bar. Deterministic graph traversal does.

### 3. It's tunable

Different teams have different risk tolerances. A fintech needs more
stringent policies than a marketing analytics team. The engine must
expose a clear policy YAML format and a way to test policies without
running them on a real PR.

## What to do today

If you're a data platform engineer:

1. **Adopt dbt** (if you haven't). The dbt manifest is the most
   useful schema graph in modern data engineering.
2. **Pick a critical asset.** Find one dbt model that feeds multiple
   downstream assets. This is your first gate.
3. **Write one policy.** "Block any change that breaks > 5 downstream
   assets". Simple, defensible, immediate value.
4. **Wire it into CI.** Use the Cortex Impact Gate, or write a 50-line
   GitHub Action that calls the API.
5. **Measure.** Track incidents per quarter for 6 months. Compare
   before-and-after.

If you're an engineering executive:

1. **Ask your data team** if they've ever had a schema incident that
   was caught hours or days late. (The answer is yes.)
2. **Budget for it.** A $1k/month tool that prevents 1 incident per
   quarter pays for itself in a single avoided outage.
3. **Hold the team accountable** to the policy. Don't let the gate be
   advisory.

## What not to build

Don't build:

- ❌ **Auto-merge bots** that approve changes without human review.
  Schema changes need eyes.
- ❌ **Auto-remediation agents** that fix things without asking.
  Engineers should know what changed.
- ❌ **ML-based predictions** for impact. They look impressive in
  demos but fail at the long tail. Deterministic graph traversal is
  more accurate and more explainable.

Build:

- ✅ **Clear policy YAML** that an analyst can write without an
  engineer.
- ✅ **PR-time gates** that don't slow the team down.
- ✅ **Slack alerts** for the on-call channel.

## The state of the ecosystem in 2026

Today, Cortex Autopilot is one of a small number of products in this
category. Most teams are still in Wave 2 (observability) and haven't
moved to Wave 3 (PR-time gates). The companies that have moved are
seeing 60–80% reductions in schema-related incidents
(anecdotal, customer-reported — synthetic benchmark cannot measure
customer-side incident reduction).

The companies that haven't moved are still debugging dashboards in the
morning standup.

---

If you're ready to add a data CI gate, [install the open-source
edition](https://cortex.dev/install) or [book a 15-minute demo](https://cortex.dev).

**Next:** the [Cortex Benchmark 2026](./benchmark.md) — reproducible
numbers across 10,000 simulated changes.
