# Feature Request Backlog — Cortex Autopilot

> Track B rule: **don't build a feature until 3 distinct paying customers have asked for it.**

This is the single source of truth for product feature requests.

## How Requests Enter

1. **Discovery call** — sales rep (you, today) logs the request in
   `Active Requests` below.
2. **Demo feedback** — customer notes a gap after seeing the demo.
3. **Pilot friction** — pilot users hit a wall and ask for a workaround.
4. **Support ticket** — customer escalates a missing capability.
5. **GitHub issue** — community contributor opens a feature request.

## Promotion Rule

A feature moves from **Active → Promoted** when **3 distinct companies**
have asked for it. Until then, it's not on the roadmap.

Distinct companies, not distinct requests — three requests from the
same company count as one.

## The Three-Company Bar

| Why | Rationale |
|-----|-----------|
| **Avoids the loudest-customer trap** | One big customer's preference is not a market signal. |
| **Tests for actual revenue impact** | Three customers willing to articulate the need → they'll likely pay for the solution. |
| **Fits the engineering budget** | With 4 engineers, you can only ship ~12 well-scoped features per year. Choose wisely. |

If only one or two customers have asked, the feature is **Watched** —
noted but not committed. Re-evaluate monthly.

## Active Requests

| Date | Customer | Request | Vertical | Severity | Status |
|------|----------|---------|----------|----------|--------|
|      |          |         |          |          | Active |

**Severity:**
- **P0** — blocks adoption for new customers
- **P1** — losing deals because of this
- **P2** — annoying but workaround exists
- **P3** — nice to have

## Promoted (Ready to Build)

A feature only enters here when 3 distinct companies have asked.

| Feature | Vertical demand | Target quarter | Owner |
|---------|-----------------|----------------|-------|
|         |                 |                |       |

## Recently Shipped

| Feature | Released | Customer(s) who asked |
|---------|----------|------------------------|
| Slack Block Kit alerts | v0.3.0 | Acme Co, Beta Inc, Gamma LLC |

## Watched (1–2 Customers)

| Feature | Customers who asked | Re-evaluate |
|---------|---------------------|-------------|
|         |                     | Monthly    |

## Rejected (with reason)

| Feature | Customers who asked | Why we won't build it |
|---------|---------------------|-----------------------|
|         |                     |                       |

Common rejection reasons:

- **Wrong stage for the customer.** (They need a feature only mature platforms have.)
- **Workflow-specific.** (Easolved by a configuration, not a feature.)
- **Out of scope for the next 12 months.** (Doesn't fit the Impact Gate narrative.)

## Cadence

- **Weekly:** Founder reviews the `Active Requests` table during the
  Friday review.
- **Monthly:** Promote or reject requests that crossed the threshold.
- **Quarterly:** Publish the next quarter's roadmap in
  `docs/business/quarterly_roadmap.md`.

## What We Won't Build (For At Least a Year)

These are explicitly out of scope to keep focus on the Impact Gate:

- ❌ AI agents that auto-remediate without human approval
- ❌ Autonomous deployment pipelines
- ❌ Reinforcement learning on past outcomes
- ❌ 30+ connectors (we cap at ~5 until we have paying customers asking)
- ❌ Massive dashboard suite (the verdict card is the dashboard)
- ❌ "Enterprise Operating System" positioning

If a customer asks for one of these, thank them, log it in
`Rejected (with reason)`, and explain that we'll revisit when the
Impact Gate workflow is fully validated.

## Templates

### Logging a new request

```markdown
- **Date:** 2026-08-04
- **Customer:** {{company}}
- **Contact:** {{name}}, {{title}}
- **Request:** "We need {{specific feature}} because {{pain}}."
- **Workaround today:** {{what they do today}}
- **Severity:** {{P0/P1/P2/P3}}
- **Why now:** {{deal blocker / expansion blocker / community}}
```

### Promoting a request

When a request crosses 3 customers, move it to `Promoted`:

```markdown
| BigQuery connector | 3 SaaS customers (Acme, Beta, Gamma) | Q3 2026 | @founder |
```

### Rejecting a request

When rejecting, always explain the why:

```markdown
| Auto-remediation agent | 2 customers (Acme, Beta) | Out of scope: violates our "no AI without human approval" principle for the next 12 months. Revisit Q2 2027. |
```

## Useful Links

- [`outreach_log.md`](./outreach_log.md) — Track A pipeline
- [`pricing.md`](./pricing.md) — current pricing
- [`competitive_analysis.md`](./competitive_analysis.md) — what we're not
