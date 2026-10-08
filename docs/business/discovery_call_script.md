# Discovery Call Script — Cortex Autopilot

> 15–30 minute call with a data platform buyer or champion.
> Goal: **understand their pain**, **not pitch**. Listen for the
> words "yeah, that happens to us." If they don't say it, you don't have a customer yet.

---

## Pre-Call (5 minutes)

- [ ] Look up their company: data team size, recent blog posts, any dbt public content
- [ ] Skim their GitHub org (if public) for dbt project size and structure
- [ ] Note 1 specific personalization hook for the opener
- [ ] Open `outreach_log.md` and start a new entry for this call

---

## 1. Opener (2 minutes)

> **Goal:** set context and ask permission to dig.

```
"Thanks for taking the time. I won't take more than 15 minutes.

The reason I reached out is that we're building tooling for teams
running dbt on Snowflake/BigQuery — specifically around schema
change safety.

Before I tell you about it: I'd love to understand how your team
handles schema changes today. Mind if I ask a few questions?"
```

**Listen for:** tone (defensive / curious / tired). If defensive, lead
with empathy. If tired, lead with "this might be exactly the pain we built this for."

---

## 2. Probe: The Problem (5–8 minutes)

> **Goal:** get them to describe a specific incident in their own words.

### Question 1 — The Last Incident

```
"What's the most recent time a schema change broke something in
production? Can you walk me through what happened?"
```

**Listen for:**
- Trigger: rename, drop, type change, owner change
- Discovery time: minutes, hours, days
- Resolution: rollback, hotfix, manual patch
- Cost: data team hours, downstream outage length, dashboard blast radius

**If they can't recall one:** they're either not yet at scale, or
the pain isn't acute enough to justify a tool. **Note this.** It
doesn't disqualify them — they may be a future customer.

### Question 2 — Frequency

```
"How often does that happen? Once a quarter? Once a month? Every week?"
```

**The bar for ICP fit:** at least 2 incidents per quarter.

### Question 3 — Detection Lag

```
"How do you find out? Slack ping from an analyst? PagerDuty? Morning standup?"
```

**The ideal customer answer is "morning standup" or "the day after
deploy"** — that means their MTTD is hours or days. Cortex cuts
that to seconds.

### Question 4 — Today's Workflow

```
"What's your current process to prevent this? Manual code review? A test
suite? A linter? A dedicated reviewer?"
```

**Listen for:** "code review" alone is usually insufficient — the
reviewer doesn't have a blast radius map. This is the gap.

---

## 3. Probe: The Organization (3 minutes)

> **Goal:** figure out whether the buyer is the data platform lead or the data engineering IC.

### Question 5 — Decision Maker

```
"If you wanted to bring in a tool like the one I'm describing, who on
your team would need to approve it?"
```

**Listen for:** procurement, security review, head of data, director of
analytics engineering. **Capture the buyer's title and the approver's title.**

### Question 6 — Team Shape

```
"How big is your data team? How is it structured — analysts, engineers,
ML, BI?"
```

**Listen for:** "we have a platform team" = great. "everyone wears
many hats" = early stage, may not have the time to evaluate tools.

---

## 4. Soft Pitch (2 minutes)

> **Goal:** describe what we built, **tied to what they just said**.

```
"Based on what you said, here's what we built:

Cortex Autopilot reads your dbt manifest, computes the blast radius
of a proposed change, and posts a structured PR comment with a
verdict — pass, warn, or block. It works like a CI gate but for
data changes.

The cool part is that it's connector-agnostic. We support dbt,
Snowflake, DataHub, and there's an SDK to write your own.

If {{the specific pain they mentioned}} is something you deal with
every week, this would save you about an hour per incident and
probably catch the next one before it ships."
```

**Don't show a demo yet.** Get their reaction first.

---

## 5. The Offer (1 minute)

> **Goal:** get to a real next step.

### If they sounded interested

```
"I'd love to show you a 5-minute demo running on a public dbt
project. Want me to send you a link to grab 15 minutes next week?"
```

### If they were noncommittal

```
"No pressure. I'll send you the benchmark numbers and a one-pager
after this call. If it resonates, we can pick it up later."
```

### If they pushed back on need

```
"Totally fair. If it becomes a pain point, here's my email. I'd
rather hear from you in three months than take your time today."
```

---

## 6. Wrap (1 minute)

```
"Last thing — who else on your team would find this useful?
Analytics engineering? ML? Both?"
```

**Listen for:** other potential champions. Add them to the outreach
list. Always send them their own intro email — not a forwarded
version of this call.

---

## After the Call (5 minutes)

- [ ] Update `outreach_log.md` with: stage, pain points, schema stack, decision-maker
- [ ] Send a follow-up email within 1 hour
- [ ] Schedule the demo or next call before hanging up

---

## Follow-up Email Template

```
Hi {{first_name}},

Thanks for the conversation today. To recap what I heard:

  - Your team uses dbt on Snowflake/BigQuery for {{specific use case}}
  - The last incident was {{specific incident they described}}
  - Today it takes about {{time to detect}} to catch a breaking change
  - Decision-maker: {{title}}

Next step: {{link to demo video OR link to book a 15-minute walkthrough}}

If anything else comes up in the meantime, reply here.

{{founder_name}}
```

---

## Red Flags (Pass on These Accounts)

- ❌ "We have a 6-month procurement process" without an internal champion
- ❌ "We're rebuilding our data platform next year" — too late
- ❌ "Just use dbt tests" — already believes they have the solution
- ❌ "We're not using dbt yet" — wrong stage
- ❌ "AI will solve this in 2 years" — doesn't believe in tooling investment

---

## Green Flags (Move These to Pilot Fast)

- ✅ Specific incident description within the first 5 minutes
- ✅ "We tried Monte Carlo / Bigeye and it doesn't catch this"
- ✅ Multiple stakeholders on the call (shows internal buy-in)
- ✅ Open-source dbt project on GitHub (uses the public Cortex API well)
- ✅ Already aware of schema drift and actively working on it
