# CLAUDE.md — Workflo build rules (read at the start of every step)

## What we are building
`workflo run` takes a repo with a Dockerfile or explicit run config, executes it in isolation, and produces an evidence-backed findings report shown in a local dashboard. Local-first beta. Nothing may fabricate execution, evidence, findings or verification.

## Two layers — never mix them
- **Product agents** (Analyst, Explorer, Judge, Reporter + Orchestrator, ToolGateway, Evidence ledger): live in `packages/crew/` and `packages/crew-contracts/`. Run on the host at customer run time. They emit typed contracts; deterministic services act on them. They never run shell commands or touch the filesystem.
- **You (build agent)**: development time only. You never see customer run data. Product code must never import build tooling.

## Non-negotiables
1. Fail closed. No silent fallbacks. Never skip, xfail or mock a test to get green.
2. A failed run must never display as a success.
3. Only the Judge can confirm a finding. No model output is evidence.
4. Exit codes follow docs/run_contract.md. Never edit `classify_run_outcome`; branch on `failure_stage` before it.
5. Credentials and host env never enter the sandbox. Never mount docker.sock into a workload, never use --privileged.
6. Receipts and evidence must name the backend that actually ran.
7. Prompts and source bodies are never logged. Store prompt hashes only.
8. Do not touch `legacy/`.

## Security-critical modules (owner review required before the next step)
sandbox backends and probes, ToolGateway, evidence ledger and receipts, Judge. Steps touching them are flagged in tasks/. After finishing one, write `docs/reviews/Sxx.md` summarizing the diff against docs/review-checklist.md and STOP. Only the owner adds the line `APPROVED-BY: owner`. Do not start the next step until that line exists.

## Step protocol (one step per context window)
1. Read this file, `docs/progress.md`, and the task file `tasks/Sxx.md`. Nothing else yet.
2. Write a short plan (5-10 lines) under the step heading in `docs/progress.md`.
3. Write tests first. Then implement.
4. Run the step's tests and the relevant package suites. Run packages separately (duplicate `tests` package names collide).
5. Update `docs/progress.md`: done, deviations, open issues, exact commands to re-verify.
6. Commit as `Sxx: <title>`. Commit security-critical steps separately from refactors.
7. Stop and report. Do not continue to the next step in the same context.

## Commands (confirmed against the repo 2026-10-27, S00; verify.sh added S01)
- One definition of green: `./scripts/verify.sh` (JS lint+typecheck+test, per-package pytest, CLI smoke incl. exit-6 preflight check; smoke's exit-6 step requires the `--backend` flag that lands with S03)
- Install check: fresh container, `./install.sh`, `workflo doctor` (Windows dev host: `install.ps1`). install.sh must install every workflo-cli dependency or pip fails resolving against PyPI.
- Python tests per package: `pytest -q <package>/tests` from the package dir (Windows host: add `--basetemp` under a writable temp dir if the default pytest temp root is locked).
- JS: `pnpm install --frozen-lockfile && pnpm check`
- Fixture run: no repo fixture dir exists; the fresh-install gate synthesizes its own minimal pytest fixture. Local plan check: `workflo run --path <dir-with-a-pytest-suite> --test --dry-run`.

## Reporting style
Be precise. State what you ran, what passed, what failed, and what you did not verify. If a step cannot meet its Expect section, say so and stop instead of adjusting the test.
