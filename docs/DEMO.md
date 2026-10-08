# Demo Video

> The 3-minute hackathon demo video is referenced from
> [`HACKATHON.md`](../HACKATHON.md) and
> [`README.md`](../README.md).

## Status

**Pending recording.** The script is finalized at
[`docs/demo_video_script.md`](demo_video_script.md). Recording setup:

- 1080p screen capture + voice-over
- Target runtime: 3 minutes
- Format: voice-over screen recording
- Scenes: cold open → risky change → blocked PR + auto-fix
  (cherry #1) → DataHub assertion writeback (cherry #2) → closing

## Recording checklist

- [ ] 1080p recording, 30 fps minimum
- [ ] Voice-over in quiet room with condenser mic
- [ ] Font: Inter, monospace for code: JetBrains Mono
- [ ] Color palette matches website (slate-900 bg, blue/violet accents)
- [ ] All terminal commands pre-tested and working
- [ ] Sample dbt project + Cortex server running locally

## Scenes to capture

| Scene | Time | What to show |
|-------|------|--------------|
| 1. Cold open | 0:00–0:15 | Cortex logo + tagline |
| 2. The problem | 0:15–0:45 | Animated diagram: dbt → 3 downstream, column dropped |
| 3. The agent loop | 0:45–1:30 | Live terminal: `python examples/demo/run_demo.py` |
| 4. The blocked PR | 1:30–2:00 | PR comment with verdict table |
| 4a. **Cherry #1: Auto-fix** | 2:00–2:20 | PR comment `<details>` block with SQL patch |
| 4b. **Cherry #2: Assertion writeback** | 2:20–2:40 | DataHub UI showing verdict in asset docs + tags |
| 5. Get started | 2:40–3:00 | `curl -sSL cortex.dev/install | bash` |

## Once recorded

Upload to YouTube (unlisted or public), then update the URL in:

1. `HACKATHON.md` (top of file)
2. `README.md` (Hackathon Submission section)
3. This file (replace `[pending]` with the actual URL)

Total effort: ~2 hours from script to upload.
