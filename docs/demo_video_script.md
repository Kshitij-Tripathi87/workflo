# Demo Video Script — Cortex Autopilot

> **Target runtime:** 5 minutes.
> **Format:** voice-over screen recording + cutaways.
> **Audience:** data platform engineers and their managers.
> **Goal:** by the end of the video, the viewer knows what Cortex does, why it matters, and how to install it.

## Pre-Production Checklist

- [ ] 1080p recording, 30 fps minimum
- [ ] Voice-over recorded in a quiet room with a condenser mic
- [ ] Font: Inter, monospace for code blocks: JetBrains Mono
- [ ] Color palette matches the website (slate-900 bg, blue/violet accents)
- [ ] All terminal commands pre-tested and working
- [ ] Slack channel pre-created for the demo notification

---

## Scene 1 — Cold open (0:00 – 0:15)

**Visual:** Dark screen, white text, the word "CORTEX" fades in. Then the subtitle "A CI/CD Impact Gate for Data Platforms."

**Narration:**
> "Every other change in your stack has a CI gate. Code, infra, even ML models. Data transformations? None. A column rename silently breaks three downstream dashboards — and you find out in the morning standup. Cortex Autopilot is a CI gate for data."

---

## Scene 2 — The problem (0:15 – 0:45)

**Visual:** Animated diagram showing a single dbt model → 5 downstream assets. A developer drops a column. The downstream assets turn red one by one with timestamps.

**Narration:**
> "Here's a typical analytics stack. A dbt model feeds a dashboard, an ML feature pipeline, and a finance report. A data engineer drops a column. The dbt build passes — the model is just SQL. The PR gets merged.
>
> Six hours later, an analyst notices the revenue dashboard shows null customer names. The ML feature pipeline has been emitting NULL embeddings all day. The finance report is missing rows.
>
> Total cost: lost analyst trust. 3+ hours of data engineering time. Possibly an executive postmortem."

**On screen:** timer counting up "6 hours since merge".

---

## Scene 3 — Install (0:45 – 1:15)

**Visual:** Terminal session. Clean dark background. Command typed.

```bash
git clone https://github.com/cortex-autopilot/cortex-autopilot.git
cd cortex-autopilot
./setup.sh
```

The script runs, prints `[ok] Backend healthy`, `[ok] Frontend ready`, then opens a browser to `http://localhost:3000`.

**Narration:**
> "One command. Twenty seconds later, you're at the control room."

**On screen:** the `setup.sh` running with the green [ok] ticks.

---

## Scene 4 — The control room (1:15 – 1:45)

**Visual:** Browser opens to `http://localhost:3000`. The cursor clicks on "orders" in the asset picker. The control room shows:

- Asset details
- Lineage graph with 4 downstream assets
- Scenario form: "Drop column: customer_name"

**Narration:**
> "Cortex Autopilot has ingested your dbt manifest. You can see every asset, its downstream dependencies, and its severity score.
>
> Now we'll simulate dropping a column."

**Cursor clicks** "Simulate Scenario".

---

## Scene 5 — The verdict (1:45 – 2:30)

**Visual:** The page transitions to a results view. The verdict appears in big letters at the top: **BLOCK** in red. Below it:

- Severity: CRITICAL (88/100)
- Blast Radius: 3 downstream assets
- Affected: 1 critical dashboard, 1 ML feature, 1 finance report
- Policy fired: "Block critical-severity changes"

Then the Slack notification appears in a side-by-side split screen:

**Narration:**
> "Within 40 milliseconds, Cortex has read the manifest, computed the blast radius, and applied our policy. The verdict is BLOCK.
>
> Three downstream assets would break — including a critical dashboard and an ML feature pipeline. The engineer sees this before merging."

**On screen:** the verdict card pulses once.

---

## Scene 6 — The PR comment (2:30 – 3:00)

**Visual:** GitHub PR comment mockup. The comment contains:

- A structured table with verdict, asset, severity, blast radius
- A "Why this was blocked" section listing affected consumers
- A "Recommended action" with a generated SQL patch

**Narration:**
> "In a real PR, this comment posts automatically when the GitHub Action runs. The engineer doesn't just see 'BLOCKED'. They see exactly which consumers break, why, and what to do about it.
>
> The recommended action: create a SQL compatibility view that aliases the old column to a placeholder, then deprecate the column after downstream consumers migrate."

**On screen:** the SQL patch preview expands.

---

## Scene 7 — The policy tweak loop (3:00 – 3:45)

**Visual:** Back in the UI, the Policy Tweaker panel. The cursor slides `max_severity` from 75 to 95. The verdict card flashes: PASS. Then slides back: BLOCK.

**Narration:**
> "Policies aren't black boxes. Drag the threshold. Watch the verdict flip. This is the loop your team uses during code review — try a policy, see what it does, commit it.
>
> Start permissive — warn only. Once you trust the verdicts, switch to block."

**On screen:** the slider moving, the verdict transitioning colors.

---

## Scene 8 — The full pipeline (3:45 – 4:30)

**Visual:** Animated diagram showing the architecture:

```
[dbt manifest.json]
        ↓
Cortex Connector (file read)
        ↓
Graph Snapshot (in-memory)
        ↓
Impact Engine (traverse + score)
        ↓
Recommendation Ranker
        ↓
Policy Engine (block/warn/pass)
        ↓
Verdict + PR Comment + Slack Alert
```

Each box highlights as the narration names it.

**Narration:**
> "Under the hood, three connectors feed a common engine. dbt, Snowflake, DataHub today — and a Python SDK if you have a custom source. The engine builds a graph snapshot in memory, traverses it to compute blast radius, ranks candidate remediations, and evaluates your policy.
>
> 40 milliseconds, end to end."

---

## Scene 9 — Get started (4:30 – 5:00)

**Visual:** Final screen. Dark background. Big text:

- "Install locally" → `curl -sSL cortex.dev/install | bash`
- "Read the docs" → `docs.cortex.dev`
- "Talk to a founder" → `hello@cortex.dev`

**Narration:**
> "The open-source edition is free, self-hosted, complete. Install locally in under 10 minutes. Read the docs. Or book a 15-minute walkthrough on your own dbt project. We'll show you exactly what Cortex would catch in your stack.
>
> Thanks for watching."

**On screen:** URL `cortex.dev` fades in.

---

## Post-Production

- [ ] Caption file (.srt) for accessibility
- [ ] Compressed version for landing page (under 1 MB)
- [ ] Embed on `/` homepage and `/product` page
- [ ] Publish to YouTube with a clear title and tags
- [ ] Add the link to `docs/business/discovery_call_script.md`

## Variations

| Length | Use case | What's cut |
|--------|----------|------------|
| 5 min | Default | None |
| 2 min | Landing page | Scenes 4, 7, 8 |
| 30 sec | Twitter / LinkedIn ad | Scenes 3–9 condensed |

## Voice-Over Style

- **Tone:** calm, confident, slightly understated.
- **Pace:** medium. Don't rush. Pause between scenes.
- **Words per minute:** ~150.
- **Avoid:** buzzwords ("revolutionary", "game-changing"), superlatives, hype.
- **Prefer:** concrete numbers ("under a millisecond", "12 downstream assets", "2.7% false-positive rate", "70% fewer incidents").

## Music (Optional)

A subtle lo-fi track under the narration, ducked to 20% during voice.
Fade in at Scene 1, fade out at Scene 9.

If you skip music, the video should still feel complete.
