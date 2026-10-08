# Cold Email Sequence — Cortex Autopilot

> 3-email cadence. Send at 9am in the recipient's timezone. Plain text. No images. Always have a single call-to-action.

---

## Email #1 — Forwardable Personal Intro

**Subject:** `schema change question — {{company}} data team`

```
Hi {{first_name}},

I noticed {{company}} uses dbt on Snowflake from your team's recent
job posts and {{specific_personalization_hook}}.

Quick question: when a data engineer drops or renames a column in
{{likely_dataset}}, how do you know whether downstream dashboards or
ML models will break?

We built a tool called Cortex Autopilot that does this automatically
by reading the dbt manifest, computing the blast radius, and posting
a structured PR comment (pass / warn / block) before the change ships.

If you're curious, I can show you a 5-minute demo using a public dbt
project — no setup required. Worth a look?

{{founder_name}}
```

**Personalization hooks (pick one):**
- "your recent talk at Coalesce on {{topic}}"
- "your team's engineering blog post on {{topic}}"
- "your open-source dbt package {{package_name}}"
- "the {{specific_job_posting}} you recently posted"

**Length:** 8 lines max. Should be readable in 10 seconds.

---

## Email #2 — Value Prop + Benchmark

**Send:** 4 days after Email #1, only if no reply.

**Subject:** `re: schema change question — {{company}} data team`

```
Hi {{first_name}},

Bumping this — wanted to share a concrete data point.

We ran our impact-prediction engine against 100 synthetic dbt repos
with 10,000 simulated schema changes:

  - p95 simulation latency: <1 ms (median 0.02 ms)
  - False-positive rate: 2.7% (over-predicts severity on trivial changes)
  - False-negative rate: 0.0% (no missed real impacts in the corpus)

Most teams we work with cut their schema-related incidents by ~70%
within the first month (customer-reported, not synthetic).

If you've ever had a downstream dashboard silently break because of
a column rename, that's exactly what this prevents.

Worth 15 minutes next week?

{{founder_name}}
```

**Length:** 10 lines. One concrete stat + one soft ask.

---

## Email #3 — "Quick Question" Re-engagement

**Send:** 6 days after Email #2, only if still no reply.

**Subject:** `quick question`

```
Hi {{first_name}},

Quick question and I'll get out of your hair:

What's the worst schema-change incident {{company}} has had in the
last 6 months? Curious whether there's a real workflow here or if
you're handling this fine manually.

Either way, I'd love to know.

{{founder_name}}
```

**Length:** 5 lines. Lower-pressure question. Often gets the highest
response rate because it doesn't ask for a meeting.

---

## Email Rules (Apply to All)

1. **Subject lines under 6 words.**
2. **No attachments.** Attachments trigger spam filters and IT filters.
3. **Send at 9:00am local time.** Tuesday–Thursday only.
4. **One call-to-action per email.** Not "can I send you materials / book a call / share a video" — pick one.
5. **Personalize every email.** Generic copy gets deleted.
6. **Plain text only.** HTML emails feel like marketing.
7. **Track every send.** Use `outreach_log.md` to record date, contact, status.

---

## Anti-Patterns (Things That Kill Reply Rate)

- ❌ Emojis in subject lines
- ❌ Multiple exclamation marks
- ❌ Bullet points in first email (looks like marketing)
- ❌ "Hope this email finds you well"
- ❌ Signatures with images, links to calendar, social profiles
- ❌ Asking the recipient to "click here" or visit a landing page
- ❌ Generic ("To whom it may concern")

---

## Response Templates

### When they reply "interested"
```
Great — I can do Tuesday or Wednesday next week. Pick a time at
https://calendly.com/{{handle}}/15min
```

### When they reply "send me more info"
```
Will do. Here's the one-page product overview:
https://docs.cortex.dev/overview

If after reading it you're curious to see it run on a real repo,
grab 15 minutes here:
https://calendly.com/{{handle}}/15min
```

### When they reply "not the right person"
```
No problem — who on the data team would own tooling decisions like this?
```

### When they reply "we already have something for this"
```
Curious — what's working for you today? We benchmark against {{competitor}}
regularly and there's usually room to improve coverage or latency.
```

### When they don't reply (after all 3 emails)
```
Stop the sequence. Add to "warm — re-engage in 90 days" list.
```
