# Outreach Log — Cortex Autopilot

> Customer Relationship Management (CRM) tracker for the founder-led
> discovery sprint. **Update this file weekly.**

## Recent Updates

- **2026-08-01** — Synthetic benchmark validated: p95 0.06 ms, FP rate
  2.7%, FN rate 0.0%. Engine fix landed (scenario-aware severity).
  Marketing claims updated to measured numbers. See
  [`docs/blog/04_benchmark_results.md`](../../docs/blog/04_benchmark_results.md).

## Funnel Stages

```
outreach → replied → discovery_call_booked → demo → design_partner → pilot → paying
```

A contact moves through these stages in order. The goal is **5 paying
customers in 12 months**.

---

## Weekly Summary

| Week | Outreach Sent | Replies | Discovery Calls | Demos | Partners | Pilots | Paying | Notes |
|------|---------------|---------|-----------------|-------|----------|--------|--------|-------|
| W1   | —             | —       | —               | —     | —        | —      | —      | Sprint planning, target list built |
| W2   |               |         |                 |       |          |        |        |  |
| W3   |               |         |                 |       |          |        |        |  |
| W4   |               |         |                 |       |          |        |        |  |
| W5   |               |         |                 |       |          |        |        |  |
| W6   |               |         |                 |       |          |        |        |  |
| W7   |               |         |                 |       |          |        |        |  |
| W8   |               |         |                 |       |          |        |        |  |
| W9   |               |         |                 |       |          |        |        |  |
| W10  |               |         |                 |       |          |        |        |  |
| W11  |               |         |                 |       |          |        |        |  |
| W12  |               |         |                 |       |          |        |        |  |

**Targets (12-month):**
- 100 discovery calls
- 50 product demos
- 10 design partners
- 5 pilots
- 3–5 paying customers

---

## Contact Log

### Active Conversations

| Date | Contact | Company | Stage | Stack | Last Touch | Next Step |
|------|---------|---------|-------|-------|------------|-----------|
|      |         |         |       |       |            |           |

### Cold Outreach Sent

| Date | Contact | Company | Template | Sent At | Status |
|------|---------|---------|----------|---------|--------|
|      |         |         | #1       |         | sent / replied / no_response |

### Discovery Calls

| Date | Contact | Company | Pain Heard | Decision Maker | Outcome |
|------|---------|---------|------------|----------------|---------|
|      |         |         |            |                |         |

### Demos

| Date | Contact | Company | Stack | Demo Outcome | Next Step |
|------|---------|---------|-------|--------------|-----------|
|      |         |         |       |              |           |

### Design Partners (signed pilot agreement)

| Date | Contact | Company | Term | Value | Champion | Notes |
|------|---------|---------|------|-------|----------|-------|
|      |         |         |      |       |          |       |

### Pilots (using Cortex on staging / production)

| Date | Contact | Company | Stack | Pilot Started | Pilot Ends | Conversion |
|------|---------|---------|-------|---------------|------------|------------|
|      |         |         |       |               |            |            |

### Paying Customers

| Date | Contact | Company | Plan | MRR | Contract Start | Notes |
|------|---------|---------|------|-----|----------------|-------|
|      |         |         |      |     |                |       |

---

## Templates

### Outreach #1 — Forwardable Intro

See [`cold_email_sequence.md`](./cold_email_sequence.md) for the full
template.

### Follow-up After Reply

```
Hi {{first_name}},

Thanks for the reply. Two questions:

1. When did the last schema change break something in your stack?
2. Who on the data team would own a tool like this?

I'll prep a 15-minute demo for the call — you'll see a real dbt PR
go from green to red as we drop a column.

Book a slot here: https://calendly.com/{{handle}}/15min

{{founder_name}}
```

---

## Conversion Ratios (Track Weekly)

| Ratio | Formula | Target |
|-------|---------|--------|
| **Outreach → Reply** | Replies ÷ Outreach Sent | ≥ 15% |
| **Reply → Call** | Calls ÷ Replies | ≥ 50% |
| **Call → Demo** | Demos ÷ Calls | ≥ 50% |
| **Demo → Partner** | Partners ÷ Demos | ≥ 30% |
| **Partner → Pilot** | Pilots ÷ Partners | ≥ 50% |
| **Pilot → Paying** | Paying ÷ Pilots | ≥ 50% |

**End-state funnel (from 100 outreach):**
- 100 outreach → 15 replies → 8 calls → 4 demos → 1–2 partners → 0.5–1 pilots → 0.25–0.5 paying.

This is the bar for **founder-led sales** before hiring an AE.

---

## Wins (Celebrate These)

- ✅ First reply that mentions a specific incident
- ✅ First discovery call where the prospect uses the phrase "yeah, that happens"
- ✅ First demo where the prospect asks about pricing
- ✅ First design partner agreement signed
- ✅ First pilot installation
- ✅ First paid invoice

## Losses (Document These)

- ❌ Replied "we already use [competitor]" — capture which competitor
- ❌ Replied "not the right person" — capture the right person
- ❌ Discovery call ended with no follow-up scheduled — capture why
- ❌ Demo with no next step — capture why

The losses are more informative than the wins.

---

## Tools

- **Outreach tracker:** This file (`outreach_log.md`).
- **CRM:** When volume grows past 50 active contacts, migrate to HubSpot Free or Attio.
- **Calendar:** Calendly free tier for booking discovery calls.
- **Email tracking:** Gmail + Superhuman (or just Gmail if cost matters).
- **Note-taking:** Notion or Quip per-call notes.

---

## Weekly Review Ritual (Friday 4pm)

1. Update the weekly summary table.
2. Calculate the conversion ratios.
3. Identify the next 10 outreach targets for next week.
4. Send a recap to your accountability partner (or advisor).
5. **One thing to change:** what was the highest-leverage thing you learned this week?
