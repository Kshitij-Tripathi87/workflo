# KPI Dashboard — Cortex Autopilot

> **Last updated:** 2026-08-04. Refreshed weekly during the Friday review.

## The 8 KPIs That Matter

These are the only metrics worth tracking. Everything else is vanity.

| # | KPI | Definition | Target (12 months) | Current |
|---|-----|------------|---------------------|---------|
| 1 | **Discovery calls** | Number of 15–30 minute discovery calls held | 100 | — |
| 2 | **Product demos** | Number of full product demos given | 50 | — |
| 3 | **Design partners** | Number of companies signed as design partners | 10 | — |
| 4 | **Pilots** | Number of customers running Cortex on staging/production | 5 | — |
| 5 | **Paying customers** | Number of customers paying for hosted Cortex | 3–5 | — |
| 6 | **ARR** | Annual Recurring Revenue from paying customers | $50k–100k | — |
| 7 | **Net Revenue Retention** | Expansion revenue ÷ starting revenue (annualized) | > 100% | — |
| 8 | **Weekly Active Users** | Number of engineers running Cortex on PRs in a week | Increasing | — |

## What Each KPI Tells You

### 1. Discovery calls

- **Why it matters:** the funnel starts here. Without discovery calls,
  nothing else moves.
- **Leading indicator:** discovery calls in week N correlate with
  paying customers in week N+12 to N+16.
- **When to panic:** < 5 calls/week for 3 consecutive weeks.

### 2. Product demos

- **Why it matters:** demos convert at higher rates than calls. Each
  demo is a chance to make the product tangible.
- **Leading indicator:** demos in week N correlate with paying
  customers in week N+8 to N+12.
- **When to panic:** < 3 demos/week for 3 consecutive weeks.

### 3. Design partners

- **Why it matters:** design partners are your product feedback loop.
  They tell you what to build next.
- **Definition:** a paying customer OR a customer signed to a 0$
  pilot agreement who commits to weekly feedback.
- **When to panic:** < 1 design partner/quarter for 2 quarters.

### 4. Pilots

- **Why it matters:** pilots are the moment of truth. They install
  Cortex on real data and run real PRs through it.
- **Pilot duration:** typically 30–60 days.
- **Conversion rate target:** ≥ 50% of pilots convert to paying.

### 5. Paying customers

- **Why it matters:** paying customers = revenue = company.
- **Conversion rate target:** ≥ 50% of pilots convert to paying.
- **Time to first dollar:** aim for < 6 months from company launch.

### 6. ARR

- **Why it matters:** ARR is the proxy for product-market fit.
- **Calculation:** sum of all customer MRR × 12.
- **ARR per customer target:** $10k–$50k/year (Team tier avg).

### 7. Net Revenue Retention

- **Why it matters:** NRR > 100% means existing customers expand
  faster than they churn. It's the single best indicator of
  long-term growth.
- **Calculation:** (Starting ARR + Expansion - Churn) ÷ Starting ARR
- **Target:** > 100%. Best-in-class SaaS: 120%+.

### 8. Weekly Active Users

- **Why it matters:** WAU proves the product is being *used*, not just
  bought. A paying customer with 0 WAU is going to churn.
- **Definition:** unique engineers with at least one Cortex-evaluated
  PR in the past 7 days.
- **Trend:** strictly increasing. If it plateaus, the team has
  stopped using the gate.

## What We Don't Track

These are tempting but misleading:

- ❌ **GitHub stars** — vanity. Customers don't come from stars.
- ❌ **Docker pulls** — vanity. Most pulls are CI test runs.
- ❌ **Discord members** — vanity. Quiet lurkers don't matter.
- ❌ **Twitter followers** — vanity.
- ❌ **Web traffic** — vanity unless it converts to signups.

## Conversion Ratios

These are computed weekly:

| Ratio | Formula | Target | Current |
|-------|---------|--------|---------|
| Outreach → Reply | Replies ÷ Outreach Sent | ≥ 15% | — |
| Reply → Call | Calls ÷ Replies | ≥ 50% | — |
| Call → Demo | Demos ÷ Calls | ≥ 50% | — |
| Demo → Partner | Partners ÷ Demos | ≥ 30% | — |
| Partner → Pilot | Pilots ÷ Partners | ≥ 50% | — |
| Pilot → Paying | Paying ÷ Pilots | ≥ 50% | — |

If any ratio drops below target for 3 weeks in a row, **stop and fix
that step before moving to the next**.

## Weekly Review Template

```
Week of: {{date}}

## Numbers
- Outreach sent this week: {{n}}
- Replies: {{n}}
- Discovery calls: {{n}}
- Demos: {{n}}
- New design partners: {{n}}
- New pilots: {{n}}
- New paying customers: {{n}}

## Conversion Ratios (vs target)
- Outreach → Reply: {{x%}} (target ≥ 15%)
- Reply → Call: {{x%}} (target ≥ 50%)
- Call → Demo: {{x%}} (target ≥ 50%)
- Demo → Partner: {{x%}} (target ≥ 30%)

## Wins
- {{win 1}}
- {{win 2}}

## Losses
- {{loss 1}}
- {{loss 2}}

## One thing to change next week
{{answer}}

## One number that's red
{{answer + remediation}}
```

## Quarterly Review Template

```
Quarter: Q{{n}} {{year}}

## ARR
- Starting ARR: ${{x}}
- Ending ARR: ${{y}}
- Net new ARR: ${{z}}
- Net Revenue Retention: {{x%}}

## Customer Count
- Starting: {{n}}
- New: {{n}}
- Churned: {{n}}
- Ending: {{n}}

## Product
- New paying customers: {{n}}
- Average time to first verdict for new customers: {{days}}
- Top 3 customer-requested features: {{list}}

## Sales
- Total outreach sent: {{n}}
- Discovery calls held: {{n}}
- Demos given: {{n}}
- Win rate (demo → paying): {{x%}}

## One thing that worked
{{answer}}

## One thing that didn't
{{answer}}

## One big bet for next quarter
{{answer}}
```

## Tracking Tools

For a pre-PMF company, use a Notion or Google Sheet:

- One tab per week with the numbers.
- One tab for the funnel ratios.
- One tab for customer notes.

For a post-PMF company (3+ paying customers), migrate to:

- **HubSpot Free** for CRM + funnel tracking
- **Stripe** for ARR tracking
- **Baremetrics** or **ChartMogul** for SaaS metrics
- **Looker Studio** for the dashboard

## Cadence

- **Daily:** update outreach log
- **Weekly:** Friday review (15 minutes)
- **Monthly:** recalculate conversion ratios
- **Quarterly:** board / advisor update

## Open Questions

- Should WAU include Slack alert readers or only engineers who run
  the gate? (Lean toward gate-runners.)
- Should we count self-hosted Free users as WAU? (Lean toward yes, but
  only if we can measure.)
- How do we attribute multi-stakeholder deals (engineering lead +
  manager + director) to one conversion? (Use the buyer as the
  primary attribution.)
