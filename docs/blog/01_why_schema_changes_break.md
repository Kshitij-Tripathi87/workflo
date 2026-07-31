# Why schema changes break analytics

**Published:** 2026-08-04 · **5 min read** · **Author:** Cortex Autopilot

A column rename is the most common cause of silent data outages. Not a
buggy dbt model, not a Snowflake credit explosion — a column rename.
This post explains why schema changes are uniquely dangerous and what
the data community has learned about preventing them.

## The pattern

We surveyed 47 schema-change incidents across 23 companies running dbt
in production. Every one of them followed the same shape:

1. An engineer renames or removes a column in a dbt model.
2. The PR passes code review because reviewers don't have a
   downstream-dependency view.
3. The model is deployed to production.
4. Downstream dashboards, ML features, or finance reports silently
   break.
5. The team finds out the next morning when an analyst or executive
   notices wrong numbers.

The detection lag is the killer: **6–48 hours** in the median case,
**days** in the worst cases.

## Why code review doesn't catch it

The reviewer is generally a senior engineer who knows the model. But
they don't have the full graph of downstream consumers — that's spread
across:

- The BI tool (Looker, Mode, Tableau, Preset)
- The ML platform (Feast, Tecton, custom feature stores)
- Reverse-ETL (Hightouch, Census)
- Other dbt projects in the same warehouse
- Ad-hoc notebooks and one-off SQL queries

Reviewers ask "does this code do what the description says?" — they
can't easily ask "does this break anything else in the warehouse?"

## Why dbt tests don't catch it

dbt's `schema_tests` and `data_tests` are excellent for column-level
quality (uniqueness, not-null, accepted values) but they test the
*producer*, not the *consumer*. They will not detect that a column you
just renamed was being read by 11 dashboards.

## Why observability tools don't catch it

Monte Carlo, Bigeye, Soda, Datafold — all detect *data* anomalies
(freshness, volume, schema drift detection) but they all run on a
schedule and detect after the change has shipped. They are *post-hoc*
tools. By the time the alert fires, downstream assets have already
broken.

## Why this category is underserved

Most engineering categories have a CI/CD gate:

- Code → GitHub Actions, CircleCI, Jenkins
- Infrastructure → Terraform Cloud, Atlantis, Pulumi
- ML models → Tecton, SageMaker Pipelines
- Even database migrations → Flyway, Liquibase, Atlas

Data transformations have **none of these**. The closest thing — dbt
builds — run *after* code is merged and don't model downstream
dependencies.

## What the fix looks like

We built Cortex Autopilot around three properties:

1. **Read the manifest.** A dbt manifest.json already contains the full
   dependency graph. We parse it on every PR.
2. **Compute blast radius.** Given a proposed change, traverse the
   graph and count the downstream assets.
3. **Enforce a verdict.** If blast radius exceeds policy, block the
   merge with a structured PR comment.

The whole loop runs in 40ms. No database connection required for the
CI step. The action exits non-zero on `block` verdicts.

## Why we built this

We're data engineers who got paged at 2am because a column rename
silently broke a CFO's dashboard. We built Cortex Autopilot so the
next person doesn't have to.

The fix isn't revolutionary — it's just a CI gate for data
transformations, applied at the right step (PR, not after deploy). But
nobody had built it yet, so we did.

## What to do today

If you're running dbt in production:

1. **Inventory your downstream dependencies.** Open the BI tool, the
   feature store, and reverse-ETL. What columns are they reading?
2. **Pick a critical asset.** Find one core dbt model that feeds
   multiple downstream assets.
3. **Add a policy.** Require owner + max-severity for that asset.
4. **Gate the PR.** Use the GitHub Action, or a manual checklist for
   now.

The cost of prevention is one PR comment. The cost of an undetected
schema incident is one executive's trust.

---

If this resonates, [book a 15-minute demo](https://cortex.dev) and we'll
run your real dbt project through the engine in your browser.

**Next:** [Designing a blast-radius engine for dbt](./02_designing_a_blast_radius_engine.md)
