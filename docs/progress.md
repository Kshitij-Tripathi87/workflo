# progress.md — the build session's memory

Update after every step. This file is the only thing carried between context windows.

## Status board
| Step | Title | Status | Commit | Review |
|---|---|---|---|---|
| S01-pack | Agent pack installed at repo root | done | 53194d9 | - |
| S00 | Day-1 verification gate | done | 2346851 | standard |
| S01 v2 | Repo guardrails (gate + verify.sh + smoke plan) | done | 15f705f | standard |
| S02 | Contracts package | done | (this commit) | standard |
| S03 v2 | Run service, backend resolver, legacy decoupling | next | - | standard |

History note: original Day-1 commit 7ba97a3 mixed the P0 fixes with the legacy/ move; split in S00.7 into 99124aa (Day 1a: move only, 478 pure renames) + b425483 (Day 1b: the 10 P0 fix files) + 53194d9 (S01-pack replay). Tree verified byte-identical to pre-split; branch `backup-pre-split` kept for audit, safe to delete.

## Decisions log
- (2026-10-26) Pack installed on `day1-green-baseline`; the pack's own README.md deliberately not copied (repo README must stay for the S00 flag audit).
- (2026-10-27) S00.7: split Day-1 commit so the legacy move is revertable alone (see history note above).
- (2026-10-27) `.github/workflows/benchmark.yml` deleted: the Python benchmark exists only under `legacy/backend/tests/benchmark` and docs/benchmark.md describes the legacy Cortex product; frozen code should not be built or benchmarked from CI.
- (2026-10-27) ci.yml: removed the `backend` job (legacy-only; active services covered by control-plane.yml, worker.yml, workflo-cli.yml, linux-gate.yml); nextjs matrix reduced to apps/dashboard; docker-build no longer builds legacy backend/frontend images.
- (2026-10-27) Deleted root tsconfig.json, tsconfig.node.json, vite.config.ts, vitest.config.ts — the old SaaS web app's root configs, all referencing moved dirs, nothing references them. tsconfig.base.json kept (extended by 6 packages).
- (2026-10-27) workflo-cli.yml and install.sh install workflo-supervisor from `legacy/supervisor` (reference, not modification) until S03's run_service refactor removes the CLI's hard import of `workflo_supervisor`.
- (2026-10-27) setup.sh paths repointed to legacy/backend, legacy/frontend (it boots the frozen pair; reference only).
- (2026-10-27) Dashboard lint toolchain: next 15.5's `next lint` requires ESLint 9 + flat config; dashboard had eslint 8.57.1 + eslint-config-next 14.2.35. Bumped to eslint ^9.14.0, eslint-config-next ^15.5.0, added @eslint/eslintrc ^3.3.0 + eslint.config.mjs (Next 15 scaffold pattern). apps/dashboard/package-lock.json regenerated (npm-managed in CI's nextjs job) and pnpm-lock.yaml updated. `pnpm check` was failing on mainline; now green.
- (2026-10-27) workflo-cli main.py: added missing `classify_run_outcome` / `classify_failure_stage` imports — Day-1b wired the calls but never imported them; every run exited via NameError → exit 1.
- (2026-10-27) 3 verify tests in test_cli_receipt_wiring.py asserted the pre-Phase-7 exit 1 for tampered/broken receipts; aligned to run_contract.md §6 (verify exit 4). Contract says exit 1 is not a verify code.
- (2026-10-27) README: `--backend auto|docker|namespaces` documented but not implemented (S03 adds it) — marked in Quickstart #4 and the flags table.
- (2026-10-27) CLAUDE.md Commands corrected against the verified repo (no fixtures/node-bugs exists; gate synthesizes its own fixture).

## Open issues
1. workflo-cli hard-imports `workflo_supervisor` (only in legacy/) — being removed in S03 v2 (today); then drop legacy/supervisor from install.sh + workflo-cli.yml.
2. RESOLVED (S01 v2): apps/agent-cli console script renamed `workflo` → `workflo-agent`; the entry-point collision is gone. Full retirement of the standalone agent CLI stays on the S17 list per the re-baselined roadmap.
3. packages/executor adversarial/golden vitest suite on Windows: fixture teardown kills the invoking process tree (killed the verification shell twice), and vitest exited 0 with 2 failed tests (green-lying) — Windows-only hazard; keep JS CI on ubuntu; consider documenting, not weakening.
4. apps/worker-engine 2 Windows-only failures: `os.getuid` (scripts/release/run_deep_image_smoke.py:76) and Unix-path `shutil.which` (llamacpp_runtime.py:206). Worker CI is ubuntu-only; recorded, not fixed.
5. Preflight-failed receipts encode canary as `request_succeeded: true, error: "canary never ran"` → `workflo verify` fails closed calling it "isolation broken" (exit 4). Becomes the P0 tri-state canary fix in S06 v2 (blocked / leaked / not_run; only blocked passes; others exit 4).
6. fresh-install-gate.yml runs its CI container with `--privileged` (to host bwrap) — CI gate infra, not a workflo workload; flag for owner review.
7. RESOLVED (S00 + roadmap): baselines re-set at workflo-cli 125 / 1,424 total on the verified Windows run; Linux CI numbers become authoritative once the PR runs.
8. apps/dashboard is npm-managed (own package-lock.json) inside the pnpm workspace — dual lockfile management; consolidate post-beta.

## Step notes
(one section per step: plan, deviations, verify commands)

### S00 — Day-1 verification gate (2026-10-27)
Env: Windows 11, Python 3.14.6, pnpm 9.12.0, node 26.4.0, WSL2 Ubuntu present, **Docker absent**.

1. Stale refs (Do/1): scoped grep found 6 stale targets; fixed: root tsconfig.json + tsconfig.node.json + vite.config.ts + vitest.config.ts (deleted, old-webapp configs), ci.yml (backend job, nextjs matrix, docker-build), workflo-cli.yml (supervisor/** + ./supervisor → legacy/supervisor), benchmark.yml (deleted), setup.sh (legacy paths), install.sh (dependency gaps, see 3). Dockerfiles, deploy/, scripts/ clean. Re-grep now clean; remaining pattern hits are intentional `legacy/...` references.
2. Python suites (Do/2), each run separately from its package dir with `.workflo-venv` (all 14 packages installed editable in dependency order):
   workflo-cli **125 passed / 0 failed** (claim 126; 125 collected, no skips — claim does not match tree), workflo-schema 180, workflo-utils 37, cortex-auth 42, sandbox-isolation 85, probe-engine 23, workflo-datahub 19, sandbox-runtime 310 passed + 35 Linux-only skips, sandbox-executor 55, control-plane 135 (+1 skip), agent-cli 34, validation-cli 61 (+4 deselected), worker-engine 202 passed + **2 failed — Windows-only artifacts** (os.getuid; Unix-path shutil.which; worker CI is ubuntu-only), workflo-ai-integration 116 (+1 skip). Python total: **1,424 passed / 2 failed (Windows artifacts)**. 2 timing flakes observed once in sandbox-runtime at --timeout=120; not reproducible at 180s or in isolation; no test changed.
   workflo-cli repairs found by the suite: missing classify_* imports in main.py (NameError on every run exit path — real Day-1 regression, 9 test failures), 3 verify tests asserting legacy exit 1 instead of contract exit 4.
3. JS (Do/3): `pnpm install --frozen-lockfile` OK; `pnpm check` was RED (dashboard: next lint vs ESLint 8; ingestor: unused `reject`; executor: unused `execFile` import). Fixed all three (see decisions); now lint 7/7, typecheck 6/6, vitest: contracts 40, sandbox 34 (+1 skip), ingestor 11, db 27, events 23, npm-workflo all-checks-passed, executor 13 passed + 2 failed (Windows process-kill hazard, vitest exit-0 anomaly — recorded as open issue 3; authoritative result is Linux CI). Combined Python+JS ≈ 1,572 passed.
4. Fresh-install gate (Do/4): **NOT VERIFIED** — no Docker on this host, and a WSL run is a developer-machine run which the task forbids counting. Also: the gate triggers only on push/PR to main, p4/**, arena/** — `day1-green-baseline` is not in the trigger list, so this gate has never executed for this work. Owner action: push the branch / open a PR to main to get the authoritative gate result. install.sh dependency fix validated locally: pip now resolves all 8 workflo-cli deps (was missing sandbox-runtime, workflo-supervisor, cortex-auth → gate would have failed at install).
5. README flags (Do/5): every documented flag exists in `workflo run --help` except `--backend` — marked as not implemented. CLI also has extra commands (keygen, status, repl, security-gate, update, via-api options) not in the README; out of S00 scope to add.
6. Exit codes (Do/6), confirmed live on this backend-less host:
   - `workflo run --path <fixture> --test` → one-line reason on stderr ("Preflight failed: Linux namespaces: ..."), **exit 6**, failure_stage=preflight recorded in a signed receipt, run displayed FAILURE.
   - Tampering the signed payload (passed 0→999) → `workflo verify` **exit 4**, "FAILED: signature verification failed". Also covered by 3 vertical-slice tests (exit 4).
   - BOM-corrupted receipt → **exit 5** (invalid JSON) — correct per §6.
   - Untampered preflight-failure receipt → exit 4 (canary "never ran" encoded as success → verify fails closed; open issue 5).
7. Split (Do/7): done — see history note.

Deviations: scope extended beyond the named grep set to setup.sh + root vite/vitest/tsconfig configs (same moved-dirs defect class); executor vitest suite not re-run on Linux locally (no container) — its result is recorded as Windows-observed only.

Verify commands (S00):
- Python per package (from package dir): `..\.workflo-venv\Scripts\python.exe -m pytest tests -q --timeout=180 --basetemp "C:\Users\21330\AppData\Local\Temp\opencode\wf-pytest"` (basetemp needed on this host: the default pytest temp root is access-denied).
- JS: `pnpm check` (root).
- Exit codes: `.workflo-venv\Scripts\workflo.exe run --path <dir> --test` (no backend → 6); `workflo verify --receipt <tampered>` (→ 4).

### S01 v2 — Repo guardrails (2026-10-27, per re-baselined roadmap)
Plan: SECURITY_CRITICAL.md with real paths; review gate script (tests first) wired as a required CI job; scripts/verify.sh as the one definition of green incl. CLI smoke; rename agent-cli console script (open issue 2).

Done:
1. `docs/SECURITY_CRITICAL.md`: sandbox backends + probes (sandbox-runtime, sandbox-isolation, sandbox, sandbox-executor, probe-engine), ToolGateway (tool-gateway), evidence ledger + receipts (notary, events), Judge (judge).
2. `scripts/ci/check_security_review.py`: per-commit gate — a commit touching a listed path must be an Sxx step commit carrying `docs/reviews/<Sxx>.md` with the exact line `APPROVED-BY: owner`. Fail closed; no env/flag bypass (tested). Merge commits skipped; non-step commits touching critical paths fail.
3. Tests first: `scripts/ci/tests/test_check_security_review.py` — 8 tests (pass paths, missing review, review without approval line, non-step commit, directory-prefix matching, env-var bypass attempts for 3 variable names, clean range). All green.
4. ci.yml: new required `security-review` job (PR base sha / push event.before / HEAD~1 fallback) that runs the gate and its own test suite.
5. `scripts/verify.sh`: pnpm install --frozen-lockfile + lint + typecheck + test, per-package pytest (14 suites), CLI smoke (--help, dry-run exit 0, no-backend `--backend namespaces` → exit 6 with a stderr reason). Note: the smoke's exit-6 step uses `--backend`, which lands with S03 later today — until then verify.sh fails closed on that step by design.
6. agent-cli: console script renamed `workflo` → `workflo-agent` (collision resolved); agent-cli suite re-run: 34 passed.

Deviations: none from the task; verify.sh full run deferred until S03 lands --backend (same day).

Verify commands:
- `python -m pytest scripts/ci/tests -q` (gate tests)
- `python -m pytest apps/agent-cli/tests -q` (post-rename)
- `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"` (workflow sanity)

### S02 — Contracts package (2026-10-27)
Plan (per tasks/S02.md + re-baseline): packages/crew-contracts with pydantic v2 models for all 12 contracts in docs/contracts.md; extra=forbid + schema_version on every model; invariants as validators; JSON Schemas exported to schemas/; valid+invalid fixture per contract; tests first.

Done:
1. Tests first: tests/test_contracts.py (round-trip + invalid-rejection parametrized over fixtures, unknown-field rejection per model, Confirmed >= 2 repro + control, Flaky/Unconfirmed relaxed, ReportDraft cited-ids subset via validate_report_draft, ModelCallRecord body-field rejection, StageResult ok/failure exclusivity) and tests/test_schemas.py (committed schemas must match models — drift guard).
2. All 12 contracts implemented: RunInput, SandboxHandle (canary tri-state `blocked|leaked|not_run` per the re-baseline P0 — forward-fix for S06), ProjectMap (+Route), RequirementSet (+Requirement), ProbePlan (+Probe), Candidate, Finding, ModelCallRecord (roles analyst|explorer|reporter only; the Judge cannot appear — no LLM in the Judge), ReportDraft (+cross-check fn), ReportBundle (+RunSummary, RequirementStatus, IsolationProof, ProviderProvenance), StageResult, EventRecord.
3. Invariants as validators: Confirmed needs >= 2 repro refs + 1 control ref; StageResult cannot be ok while carrying a failure (fail-closed mirror of run contract); extra=forbid rejects any body field on ModelCallRecord (prompt/response/messages).
4. Fixtures generated THROUGH the models (a fixture that fails validation fails the generator): 12 valid + 12 invalid, reasons mapped in INVALID_REASON.
5. `python -m workflo_crew_contracts.export` writes 12 schemas to packages/crew-contracts/schemas/; drift test compares committed schemas to model_json_schema().

Deviations: canary tri-state and the Judge-role rejection are additions beyond docs/contracts.md, both mandated by the re-baselined roadmap (S06 P0 + Judge hard rule); noted here for the owner's S02 review.

Verify commands:
- `python -m pytest packages/crew-contracts/tests -q` → 43 passed
- `python -m workflo_crew_contracts.export` (regenerates schemas; must be no-op diff)
