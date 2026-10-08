# Pricing Strategy — Cortex Autopilot

> **Last updated:** 2026-08-04. Review quarterly.

## Pricing Principles

1. **Free is permanent.** The open-source edition is free forever, self-hostable, and complete. It includes every connector and every policy feature.
2. **Hosted is sold.** The hosted edition is the only paid tier. It charges for *operated* infra, not for *features*.
3. **No per-seat pricing.** Engineers don't buy per seat; teams buy per repo.
4. **Per-repo pricing matches value.** One repo = one PR gate. If you gate 10 repos, you pay for 10.

## Tiers

### Free

| | |
|---|---|
| **Price** | $0 forever |
| **Deployment** | Self-hosted (Docker Compose) |
| **Connectors** | All current: dbt, Snowflake, DataHub, custom SDK |
| **GitHub Action** | ✅ |
| **Slack alerts** | ✅ |
| **Policy library** | Per-repo only (`cortex.yml`) |
| **Audit log** | Local JSONL file (your infra) |
| **Support** | Community Discord |

This is the open-source edition. Apache 2.0 licensed.

### Team — $999 / repo / month

| | |
|---|---|
| **Price** | $999 per repo per month |
| **Deployment** | Hosted Cortex (multi-tenant) |
| **Connectors** | All |
| **GitHub Action** | ✅ |
| **Slack alerts** | ✅ + PagerDuty + Teams |
| **Policy library** | Org-wide saved + shareable policies |
| **Audit log** | 90-day retention |
| **Analytics dashboard** | Team-level (verdicts per week, FP rate, etc.) |
| **Support** | Priority email (4-hour SLA on weekdays) |
| **Min commit** | $3,000 / month (3 repos) |

**Annual contract discount:** 15% (effectively $849/mo).

### Enterprise — Custom (starts at $25k / year)

| | |
|---|---|
| **Price** | Custom, $25k/year floor |
| **Deployment** | Hosted, on-prem, or VPC |
| **Connectors** | All + custom connector development (1 connector / quarter) |
| **GitHub Action** | ✅ |
| **SSO** | SAML + SCIM |
| **Audit log** | Custom retention + data residency |
| **Support** | Named CSM + 24/7 incident support + 99.9% SLA |
| **Custom** | Custom policies, custom retention, dedicated capacity |

## Why Per-Repo

A data team that cares about schema safety gates one or two core
repos first, then expands. Per-repo pricing:

- **Aligns with value.** More repos = more value to the buyer.
- **Matches buying motion.** The buyer (Head of Data) typically
  approves per-repo. Per-seat would create friction with procurement.
- **Scales linearly.** No cliff at "next size up."

The downside: it caps the upper bound at ~$10k/month per customer.
That's fine — $10k/month × 5 customers = $600k ARR which is enough to
fund 3 engineers.

## Why Not Per-Seat

Per-seat pricing on a CI tool is wrong because:

- Only one or two engineers actually configure the policies.
- The benefit is realized by *everyone* on the team, not just those
  who touch the gate.
- Procurement teams reject per-seat pricing for infrastructure tools.

## Volume Discounts

| Repos | Discount |
|-------|----------|
| 1–2 | 0% |
| 3–9 | 10% |
| 10–24 | 20% |
| 25+ | Custom |

Volume discounts apply only when the customer commits to the higher
tier via an annual contract.

## Annual vs Monthly

- **Monthly:** no discount, full flexibility to add/remove repos.
- **Annual:** 15% discount, repo count fixed at signing, can add repos
  at pro-rated pricing.

Default to annual in enterprise conversations. Monthly for SMB.

## Why We Don't Charge for the Open-Source Edition

Three reasons:

1. **Distribution.** Self-hosted users become our marketing funnel.
   Every team that uses the open-source edition is a future hosted
   customer when they outgrow self-hosting.
2. **Trust.** Engineers trust open-source code more than vendor
   binaries. Charging for the open-source edition would be a trust
   killer.
3. **Ecosystem.** Community contributors extend the connector SDK
   and add new policy templates. We can't pay for that, but we can
   give them the product.

The open-source edition has all the features. The hosted edition has
**operations**: SSO, audit log, multi-team policy library, SLA, and
the team analytics dashboard.

## Add-On Pricing

| Add-on | Price |
|--------|-------|
| Custom connector development | $5,000 / connector |
| White-glove pilot onboarding (4 hours) | $1,500 one-time |
| Custom retention (beyond 90 days) | $100 / month / month of retention |
| On-prem deployment | +50% on annual contract |
| Training session (1 hour, recorded) | $500 / session |

## Competitive Anchor

| Tier | Our price | Competitor | Their price |
|------|-----------|------------|-------------|
| Team | $999/repo/mo | Monte Carlo | $2,500–10,000 / month / source |
| Team | $999/repo/mo | Bigeye | $1,500–5,000 / month / source |
| Team | $999/repo/mo | Soda | $1,000–3,000 / month / source |
| Enterprise | $25k+/year | Monte Carlo | $100k+ / year |

We are **positioned at the entry level** of premium observability
tools. We're cheaper because we're focused on one workflow (PR-time
gate) instead of a broad observability suite.

## Sales Motion

### Self-serve (Free)

```
Install docs → Docker Compose → Connect dbt project → Done.
```

The Free edition is sold by the docs and the GitHub README. No sales
touch.

### Low-touch (Team)

```
Trial signup → 14-day hosted trial → Self-onboard → Sales call if they expand.
```

Most Team customers start as a Free customer who upgrades when they
outgrow self-hosting. Sales gets involved only when:
- The customer wants SAML SSO.
- The customer has > 5 repos to gate.
- The customer wants the audit log for compliance reasons.

### High-touch (Enterprise)

```
BDR outreach → Discovery call → Demo → POC pilot → Procurement → Contract.
```

Enterprise deals take 60–90 days. We do not invest in this motion
until we have 3+ Team customers ready to expand.

## Discount Authority

| Role | Max discount |
|------|-------------|
| Founder (year 1) | 30% off list |
| Head of Sales (when hired) | 20% off list |
| AE | 10% off list |
| SDR | 5% off list |

Discounts beyond 30% require CEO + board approval.

## Pricing Reviews

- **Quarterly:** review unit economics, conversion rates, expansion revenue.
- **Annually:** review list prices against competitive landscape.
- **Trigger-based:** consider price change if MoM growth < 5% for 3 consecutive months.

## Open Questions

- Should we add a "starter" tier at $199/month for very small teams? (A/B test.)
- Should we offer a "data prep" tier that bundles BigQuery + dbt + Cortex for new teams? (Partnership with dbt Labs.)
- Should the Enterprise tier include ML platform integration? (Sales feedback pending.)
