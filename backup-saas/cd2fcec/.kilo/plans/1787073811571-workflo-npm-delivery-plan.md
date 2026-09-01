# Workflo Delivery Plan — npm `@cortex/workflo` (Option C), Local-First LLM

## Goal

Make `npm install -g @cortex/workflo` → `workflo` → `workflo auth` (via a localhost:3001 web site) → `workflo run --repo <url> --test` work end-to-end on this Windows machine (Docker 29.6.2, Python 3.14, Node 26), with a verifiable signed receipt every run, and the LLM/agent layer running **local-first** (Ollama in the deep worker image; cloud is an explicit opt-in).

Architecture (locked): **Option C** — npm package is a thin distribution shim; the Python worker engine ships as prebuilt wheels inside an npm-package-local venv (sidecar). No TypeScript rewrite of the engine.

## Decisions (confirmed)

1. **LLM default = local** (Ollama + `qwen2.5-coder:7b-instruct`, already in the deep worker image). Keeps the live privacy policy ("code never leaves your machine"; "no third-party AI services") true by default. Cloud = explicit `--cloud` flag with a one-time terminal confirmation ("this sends code excerpts to <provider> — continue?"). Provider-agnostic `LLMClient` interface (OpenAI-compatible HTTP; Ollama local endpoint is the default). Receipt records `llm {provider, model, mode: local|cloud}` — signed, so mode is tamper-evident.
2. **Sandbox stays sealed**: `--network none` test stage, canary check, tmpfs teardown proof, Ed25519 receipt (existing `workflo_executor` + `sandbox_isolation`, unchanged contract). Local LLM runs **inside** the sealed container (Ollama is in-container, no egress) — P4/P5 claims preserved.
3. **Auth = localhost:3001 now**: the FastAPI control plane serves the login/device site on :3001 (email+password, OTP via pluggable SMTP — shown on-screen in dev mode until SMTP configured). Real site (`auth.cortex.dev`) + real Google OAuth = later rollout, not in this plan.
4. **Every `workflo run` stays auth-gated** (attribution) — matches the intended install → auth → run flow. Default auth base URL changes to `http://localhost:3001` (env `WORKFLO_AUTH_BASE_URL` override, per-profile persist).
5. Repo state is mid-rename (`tenant_shield`/`quarantyne_*` → `workflo_*`): repair is blocking and comes first.

## Verified current state (evidence, 2026-08-19)

- **pytest cannot start**: stale root `tenant_shield.egg-info/entry_points.txt` declares pytest11 plugin → `tenant_shield.reporting.plugin` (deleted). `python -m pytest` puts repo root on `sys.path`; `importlib.metadata` auto-loads the dangling entry point → `ModuleNotFoundError: No module named 'tenant_shield'` at startup (full traceback captured).
- **`.workflo-venv` is stale**: editable installs pointing at deleted dirs (`packages/core-schema`, `packages/common-utils`, `apps/worker-engine/src/tenant_shield_worker`) + pre-rename wheels.
- **npm install broken (3 ways)**: (a) `postinstall.js` hardcodes `python3` (fails on Windows); (b) expects `vendor/workflo_executor-*.whl` + `vendor/workflo_probe_engine-*.whl` — vendor/ only has pre-rename `quarantyne_*` wheels; (c) package name is `workflo`, not `@cortex/workflo`. Also missing: `cortex-auth` wheel is a 6th internal dep of `workflo-cli` but absent from the postinstall list.
- **Auth code complete, unusable e2e**: `cortex_auth` (device flow, keychain/Win/file store, profiles) + `workflo auth *` wired; default endpoint `https://auth.cortex.dev` not deployed. Contradiction to fix: control-plane `POST /v1/auth/device/verify` requires an API key (can't exist before device flow completes) while browser path `POST /device` (`app/main.py`) approves without any login check.
- **Sandbox**: `workflo_executor` stage flow verified (tmpfs → clone/copy → optional Stage-1 networked prep → sealed Stage-2 → RunReport → canary → teardown proof → signed receipt). `workflo-worker:latest` exists locally but predates the rename → rebuild. Deep/web images not built.
- **Dependency declarations stale**: 4 pyprojects declare `tenant-shield-schema` while code imports `workflo_schema` (provided by `packages/workflo-schema`, dist `workflo-schema`).
- Ballast: root `workflo/` dir (old framework copy), root `pyproject.toml`/`pytest.ini` (old `tenant-shield` dist with the pytest11 landmine, testpaths=legacy `tests/`), legacy `tests/`+`data/` (import deleted `tenant_shield`).

## Phase 0 — Repo repair (blocking; do first)

1. Delete stale root artifacts:
   - `tenant_shield.egg-info/` (pytest landmine), root `workflo/`, root `pyproject.toml`, root `pytest.ini`, legacy `tests/`, `data/`, root-level scratch (`receipt*.json*`, `report.json`, `replace_login.py`, `test_device_flow*.py`, `test_live.py`, `test_provisioning_e2e.py`, `verify-test-*` — keep only what non-test tooling still references; verify nothing imports them).
   - Keep: `docs/`, `examples/` (regenerate later if broken), `ci-templates/`, `action.yml` (refresh in Phase 6), `infra/` (out of scope).
2. Fix dependency names: in `apps/workflo-cli`, `apps/sandbox-executor`, `packages/probe-engine`, `packages/sandbox-isolation` pyprojects: `tenant-shield-schema` → `workflo-schema`. Sweep remaining `tenant_shield`/`quarantyne` references (Dockerfiles, stale `*.egg-info` under `src/` dirs — delete).
3. Rebuild clean venv `workflo-venv/` (replace `.workflo-venv`): fresh venv, then `pip install -e` the six internal packages in dep order: `packages/workflo-schema`, `packages/sandbox-isolation`, `packages/probe-engine`, `packages/cortex-auth`, `apps/sandbox-executor`, `apps/workflo-cli` (+ `apps/control-plane[dev]`, `apps/worker-engine[dev]` for local test runs) + dev extras (pytest, pytest-asyncio, pytest-timeout, httpx, cryptography, pyyaml).
4. **Checkpoint A — pytest actually runs**: `python -m pytest apps/workflo-cli/tests -q` starts and reports results (not a startup crash). Then fix test failures until the matrix is green:
   - `packages/workflo-schema/tests`, `packages/sandbox-isolation/tests`, `packages/probe-engine/tests`, `packages/cortex-auth/tests`, `apps/workflo-cli/tests`, `apps/sandbox-executor/tests`, `apps/worker-engine/tests`, `apps/control-plane/tests`, `workflo-ai-integration/workflo-ai-integration/tests` (mocks).
   - Root causes to expect: stale imports in tests, conftest paths, control-plane DB init on Python 3.14.
5. Commit the migrated state as one milestone: "Finish workflo rename: drop tenant_shield v0 root, fix dep names, green test matrix."

## Phase 1 — npm package `@cortex/workflo` (Option C done properly)

Files: `packages/npm-workflo/**` only.

1. `package.json`: name `@cortex/workflo`, version 0.2.0, `bin: {workflo: "bin/workflo.js"}`, `files: ["bin","scripts","vendor"]`, `engines: {node: ">=18"}`, scripts: `pack:build` (steps 2–3), `test`.
2. New `scripts/build-wheels.py`: builds the **six** wheels into `vendor/` in dependency order with `python -m build --wheel`: `workflo-schema`, `airlock-sandbox-isolation`, `workflo-probe-engine`, `workflo-executor`, `cortex-auth`, `workflo-cli`. Wipes `vendor/*.whl` first (no stale pre-rename wheels). Then `npm pack` → `dist/@cortex+workflo-*.tgz`.
3. Rewrite `scripts/postinstall.js` (cross-platform):
   - Python detection: try `python3`, `python`, `py -3` (`-c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)"`); on failure print OS-specific install hint (winget `Python.Python.3.12` on Windows), exit 1.
   - venv at `<pkgRoot>/.venv` (idempotent: skip reinstall when `.workflo-install.json` marker matches `{version, pythonVersion, wheelFingerprints}`).
   - `pip install --quiet` the six wheels in order (PyPI network needed for transitive deps — documented; the one network call at install time).
   - All failures: actionable message + non-zero exit (no silent partial installs).
4. `bin/workflo.js`: verify `.venv` + `workflo` binary exist (else instruct `npm rebuild @cortex/workflo`), arg passthrough, stdio inherit, forward exit code, Windows `workflo.exe` path (already present — keep).
5. **Checkpoint B**: on this machine: `node scripts/build-wheels.py` → `npm pack` → `npm install -g dist/@cortex+workflo-*.tgz` → `workflo --version` and `workflo doctor` (Phase 5) succeed.
6. README section in `packages/npm-workflo`: install, requirements (Python 3.11+, Docker for `run`), first-run walkthrough (`workflo auth login` → `workflo run`).
7. Publishing note (rollout, not here): `@cortex` scope requires an npm org; until then, `npm install -g` from the dist tarball is the supported install.

## Phase 2 — Auth at localhost:3001 (the login-to-run trace)

Components: control plane (auth API exists) + new login site pages + CLI spawn behavior.

1. **Site** (control plane serves on :3001): new minimal pages under `apps/control-plane/app/static/` (server-rendered, no build step):
   - `/login` — email+password form → `POST /v1/auth/login`; token stored in `sessionStorage`. "Use one-time code" tab → `POST /v1/auth/otp/request` → in dev mode (no `SMTP_*` env) the 6-digit code is displayed on-page with a banner ("Development mode — code not emailed; configure SMTP for real email OTP"); with `SMTP_HOST/PORT/USER/PASS`, send via stdlib `smtplib` (pluggable `OtpSender`: `dev_console | smtp`).
   - `/signup` — email+password → existing `POST /v1/auth/signup`.
   - `/device?user_code=...` — **requires an authenticated browser session** (page JS attaches `Authorization: Bearer`; server verifies before showing/approving). Shows logged-in email, client name (workflo CLI), scopes; Allow/Deny → existing `POST /device` (which now requires the bearer token and 401s without one).
   - Rate limiting: reuse existing `_check_login_rate_limit` on OTP requests too.
2. **Delete the contradictory endpoint** `POST /v1/auth/device/verify` (`apps/control-plane/app/api/v1/auth.py:650` — requires an API key that cannot exist before the device flow; duplicate of the browser path). Move its test assertions to `/device` page tests.
3. **Control plane serves static site**: mount `StaticFiles` at `/`; run config port 3001 for local mode (env `WORKFLO_CP_PORT`).
4. **CLI side** (`apps/workflo-cli`):
   - `workflo auth login`: if `http://localhost:3001/health` unreachable, spawn `uvicorn app.main:app --port 3001` as child (SQLite at `~/.config/cortex/local-cp.db`; `WORKFLO_AUTH_BASE_URL` wins), open browser to device URL, wait for token, then terminate the spawned child (unless `--keep-server`).
   - Default auth base URL: `http://localhost:3001` (was `https://auth.cortex.dev`) — in `workflo_cli/main.py` + `auth_commands.py`; persist per profile; env override unchanged.
   - Fix `run()` auth gate to use the same default (currently hardcodes the cortex.dev URL at `main.py:642-676`).
5. **Credential dedup**: `~/.config/cortex/` (cortex-auth) is the single store for workflo-cli (Windows: file fallback `~/.config/cortex/credentials.json` 0600 — `cmdkey` can't read back, verified in `credential_store.py`). Legacy `~/.workflo/config.yaml` (old `apps/agent-cli`) marked deprecated; no changes to agent-cli.
6. **Checkpoint C (the trace, executed live)**: clean state → `workflo auth login` → browser :3001 → signup+login (email+password **and** OTP dev path) → device approve → CLI gets tokens → `workflo auth status` shows email/org → `workflo auth logout` clears store. Full terminal + browser log captured in `reports/`.

## Phase 3 — Sandbox e2e (first live post-rename run)

1. Rebuild `workflo-worker:latest` from `apps/worker-engine/Dockerfile` (current image predates the rename). Base image only for this phase.
2. Fixture `e2e_fixtures/demo-app/` (new): minimal Flask/FastAPI multi-tenant app with `POST/GET/PUT/DELETE /api/v1/projects`, `X-Tenant-ID` enforcement, `GET /health`, `requirements.txt`, passing pytest suite, and a `workflo.yaml` (`web:`/`security:` start_command+port). Matches the exact shape `probe_engine.generator.DEFAULT_SECURITY_PROBES` expects.
3. E2E script `scripts/e2e_sandbox.sh` + `.ps1` (Docker Desktop compatible), each step asserted:
   - `workflo run --path <fixture> --test` → exit 0; receipt: `total>0`, `passed>0`, `canary_check.request_succeeded == false`, `teardown_proof.{container_removed,filesystem_removed,no_snapshot_retained} == true`.
   - `workflo verify --receipt <out> --pubkey <pem>` → VERIFIED.
   - Tamper test: flip one byte in a receipt copy → `workflo verify` → FAILED.
   - `workflo run --path <fixture> --test --security --start-command "python app.py" --port 5031` → receipt `security_probes` populated, `app_start_error == null`, probes non-empty.
   - `--web` step **skippable** (needs `workflo-worker-web:latest` + Chromium) — run if image present.
   - `--via-api`: start control plane (:8000) → `workflo run --via-api http://localhost:8000 --repo file://<fixture> --test` (demo token flow) → `RunStatus.completed` + receipt present. This exercises the frozen REST contract incl. the previously-500ing `POST /v1/runs`; if it 500s, capture the actual traceback first, then fix.
4. Windows risk to verify **first**: `mount_tmpfs` under Docker Desktop. If `--tmpfs` fails in the Linux-VM context, implement a documented fallback (bind-mounted temp dir + explicit receipt flag) — a decision, not silent degradation.
5. **Checkpoint D**: all of the above pass on this machine; receipts stored under `reports/e2e/`.

## Phase 4 — LLM/agent layer (local-first)

Design (extends, does not replace, the existing in-container model stage in `workflo_worker`):

- **Placement**: all LLM work runs **inside the sealed Stage-2 container** on the deep image (Ollama local, no egress — contract-safe). No host-side LLM. CLI prints structured agent progress from worker stdout (existing `WORKFLO_*` line protocol).
- **`LLMClient` interface** (new `workflo_worker/model/llm_client.py`): `generate(prompt, schema, budget) -> str`. Implementations: `OllamaClient` (default; container loopback `127.0.0.1:11434`, model `qwen2.5-coder:7b-instruct`) and `OpenAIClient` (constructed only when host passes `WORKFLO_LLM_MODE=cloud`, set by CLI `--cloud` after its one-time confirmation; `WORKFLO_LLM_BASE_URL`/`WORKFLO_LLM_API_KEY`). Default local = privacy policy preserved.
- **Three agents** (sequential passes in the worker model stage, replacing today's single generate pass):
  1. **Env agent (planner)** — input: repo tree + budget-limited source (existing caps: 4000 lines / 256KB); output: validated `AppPlan` (Pydantic: install steps, `start_command`, `port`, required env vars). Used when `--security/--web` start config is absent → replaces hand-written `workflo.yaml` (worker-side `resolve_*_config` falls back to the LLM plan; explicit CLI flags still win). If the app needs deps beyond the image, plan sets `needs_network_install=True` → host executor switches to **two-stage** (Stage 1 bridge: clone + install into the tmpfs prefix; Stage 2 sealed: app runs from that prefix) and `dependency_install_had_network=True` on the receipt (field already exists).
  2. **TestGen agent** — after app boot (127.0.0.1), input: repo routes + live endpoint discovery (`/health`, OpenAPI spec if present) + AppPlan; output: `ProbeSpec` list (already validated) + executable pytest file via existing `ProbeGenerator.generate_pytest_file` — **never** `assert True` stubs; each generated test either runs (execution facts) or skips with a reason. Generated tests run in the same pytest pass as the repo's native suite.
  3. **Analyzer agent (feedback)** — input: structured RunSummary + findings + app/pytest logs (budget-limited); output: `ReportNarrative` (Pydantic: findings[{title, severity, evidence: {nodeid, status, detail}, soc2_controls, recommendation}]). Enters the receipt **only** as structured findings with `source: "model_inference"` + execution-evidence references (P5: no unsigned model claims).
- **Safety gate**: merge `workflo-ai-integration/src/safety_gate.py` (compile/import check) into `workflo_worker` before generated tests reach pytest. Bad generations discarded (existing one-retry correction-prompt pattern, keep).
- **Model-state wipe**: existing `wipe_model_state()` + `model_inference_teardown` receipt field unchanged; three-state (None/True/False) discipline preserved.
- **Receipt extension** (`workflo_schema.sandbox.SignedReceipt` + `canonical_payload()`): `agent_mode: {llm: {provider, model, mode}, app_plan: AppPlan|None, generated_tests: [names], narrative: ReportNarrative|None}` — additive; schema tests + `docs/workflo/sandbox_contract.md` updated in the same change.
- **CLI**: `--cloud` (one-time confirmation, choice stored in profile), `--ai` (default on for `--deep-test/--aggressive-test`; off for plain `--test`).
- Tests: unit tests with a **mock Ollama** (deterministic canned responses) for all three agents + safety-gate negative cases. Live-Ollama deep run = optional manual e2e (deep image build + ~5GB model pull — documented, not in CI).
- **Checkpoint E**: mock-LLM agent tests green; one live `--deep-test` run against `e2e_fixtures/demo-app` produces a receipt with `llm.mode=local`, executed `generated_tests`, analyzer findings with evidence — or (if 7B output fails the gate) the run still completes with honest skip findings. No regression to base tiers.

## Phase 5 — `workflo doctor` (the "is it working" surface)

`workflo doctor` (in `workflo-cli`): table of checks — Node/npm shim integrity, Python version + package venv present, Docker running, images present per tier (base/deep/web), auth status + credential-store backend, Ollama model reachable (deep image). Exit non-zero on any hard failure. Standing answer to "how is it doing" for any future session.

## Phase 6 — CI + docs (thin)

- Update root `action.yml` (stale tenant-shield reference) → node+python install → `node packages/npm-workflo/scripts/build-wheels.py` → `npm pack` → `npm i -g` → `workflo doctor` → `workflo run --path e2e_fixtures/demo-app --test --security --start-command "python app.py" --port 5031` on ubuntu (docker service) → `workflo verify`.
- Refresh `README.md` top section to the npm-first story (DataHub section under a "legacy platform" heading).
- `docs/workflo/sandbox_contract.md`: add agent-mode + two-stage app-execution notes.

## Out of scope (explicit)

- Publishing `@cortex/workflo` to npmjs (needs npm org — rollout step).
- Real Google OAuth (needs GCP client) and real deployment of `auth.cortex.dev` — :3001 site is the stand-in; real email OTP needs user SMTP creds.
- Trained LoRA adapters / llama.cpp serving (scaffold in `workflo-ai-integration/` untouched).
- K8s/KEDA fleet, BrowserStack/Sauce grids, DataHub writeback, dashboard run-history pages.
- `workflo-worker-deep-web` combined image (executor deliberately raises).

## Risks

- **Windows tmpfs**: verify early in Phase 3; fallback (bind dir + receipt flag) is a decision, not silent.
- **Ollama 7B quality**: agent outputs may fail the safety gate on real repos — mitigations: one-retry correction prompt (exists), honest skips, quality-eval fixture set before any model swap. Deep image build is large (~GB) — document, don't auto-pull in base workflows.
- **npm postinstall network**: transitive PyPI deps fetched at install (documented; normal for Python CLI distribution).
- **Stale images**: `workflo-worker:latest` rebuild is mandatory before Phase 3 (pre-rename build exists locally).
- **Control-plane in-process sandbox** (`POST /v1/runs` → `SandboxExecutor` in the API process): the previous 500 on this path is exercised live in Phase 3 via `--via-api`; if it fails, capture the actual traceback before fixing.

## Validation matrix (final gate, all must pass)

1. Phase 0 matrix: all unit/integration suites green in the fresh venv; clean `git status` at each milestone commit.
2. `npm install -g` from tarball on Windows: `workflo --version`, `workflo doctor` exit 0.
3. Auth trace (Checkpoint C) recorded in full (terminal + browser actions).
4. Sandbox e2e (Checkpoint D): receipt assertions incl. canary-blocked, teardown proof, verify + tamper-fail, `--security` probes populated, `--via-api` completed.
5. Agent layer (Checkpoint E): mock-LLM unit tests green; live deep run (optional) receipt shows local mode + executed generated tests.
6. `workflo doctor` passes clean.

## Open questions (flagged, not blocking)

1. Deep image: pull model at image-build time (bigger image, faster first run) vs. lazy pull on first `--deep-test` (recommended: lazy, with progress line) — decide when building the deep image.
2. `--cloud` opt-in endpoint (OpenAI vs. internal gateway): needs the user's endpoint decision when cloud is actually turned on; interface is provider-agnostic so nothing blocks.
3. Whether legacy `apps/agent-cli` (old goal-based CLI on `~/.workflo` config) should be deleted outright — currently deprecated only.
