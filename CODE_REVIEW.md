# Workflo — Codebase Review

**Reviewed:** `Kshitij-Tripathi87/workflo` @ `6ebf2fe` (branch `arena/ef654f0f-workflo`)
**Review date:** 2026-10-08 · **Method:** read the tree, installed deps, ran every test suite, typechecker, and builder I could.
**Bottom line:** big, genuinely interesting repo with a real privacy/isolation architecture and ~1,400 passing tests — but **two blocking defects** (a broken Next.js frontend and a fatally broken supervisor IPC layer) and **several CI workflows that can never pass**.

---

## 1. What this repo actually is

A monorepo holding **three partly-overlapping products** under three different names:

| Product name | Where | What it is |
|---|---|---|
| **Workflo** | `apps/workflo-cli`, `packages/*`, `apps/worker-engine`, `apps/sandbox-executor`, `sandbox/` runtime, `supervisor/`, `client/` + root Vite app | Privacy-first QA agent: runs tests in network-blocked sandboxes, emits Ed25519-signed receipts (`wf://receipts/...`) |
| **Cortex Autopilot** | `backend/`, `frontend/`, `action/`, `examples/`, `ci-templates/` | CI/CD impact gate for data platforms: reads DataHub/dbt/Snowflake metadata, blocks risky schema changes, writes back |
| **Tenant Shield** | `apps/control-plane/`, `infra/`, `packages/cortex-auth` | Multi-tenant FastAPI SaaS control plane: OAuth device flow, API keys, run queue, audit trail, credential sealing |

Plus supporting sites: `website/` (Next marketing), `apps/dashboard/` (Next ops dashboard), `workflo-ai-integration/` (local model router + safety gate), `docs/business/` (cold-email sequences, pricing, KPIs).

**Naming note:** `CORTEX_*` env vars, `cortex-auth`, `@cortexstudio/workflo`, and `workflo-*` packages all coexist. Config keys are inconsistent across components (`CORTEX_DBT_MANIFEST_PATH` vs `WORKFLO_*`). Worth a decision before launch.

---

## 2. Repo metrics

- **964 tracked files, ~36 MB** (excl. `node_modules`/`.git`)
- **1 commit total** (squashed, 2026-09-29) — no history to bisect, no contributor record
- **~66k lines Python** (436 files), **~10.7k lines TSX** (100 files), 1.6k TS, 9.5k YAML, 6.8k MD
- 13 CI workflows, 13 Python packages/apps, 5 test-bearing frontend surfaces

---

## 3. Verification results (everything I actually ran)

### Python — ~1,400 tests, 6 failing, 34 skipped

| Component | Result | Time |
|---|---|---|
| `backend/` (Cortex Autopilot API) | ✅ **154 passed** — coverage **70%** | 1.6 s |
| `apps/control-plane/` | ✅ **103 passed** | 52 s |
| `apps/worker-engine/` | ✅ 178 passed | 10 s |
| `packages/workflo-schema/` | ✅ 175 passed | 0.4 s |
| `packages/sandbox-runtime/` | ⚠️ 295 passed, **5 failed**, 34 skipped | 138 s |
| `packages/sandbox-isolation/` | ✅ 85 passed | 2 s |
| `apps/validation-cli/` | ⚠️ 60 passed, **1 failed**, 4 deselected | 4 s |
| `apps/sandbox-executor/` | ✅ 53 passed | 32 s |
| `packages/cortex-auth/` | ✅ 42 passed | 2 s |
| `packages/workflo-utils/` | ✅ 37 passed | 0.1 s |
| `apps/agent-cli/` | ✅ 34 passed | 0.3 s |
| `packages/probe-engine/` | ✅ 23 passed | 0.2 s |
| `packages/workflo-datahub/` | ✅ 19 passed | 0.2 s |
| `apps/workflo-cli/` | ⚠️ **7 collection errors** → ✅ 119 passed *after* `pip install -e supervisor` | 1 s |
| `supervisor/` | ❌ **hangs** — 1 passed, 1+ hangs forever (see §4.2) | ∞ |
| `apps/dashboard/`, `client/`, `frontend/` | no Python tests | — |

### TypeScript / frontend

| Surface | Command | Result |
|---|---|---|
| Root Vite app (`client/`) | `tsc --noEmit` | ✅ **clean, 0 errors** |
| Root Vite app | `vitest run` | ✅ **9 passed** (hero, surfaces, trial signups) |
| Root Vite app | `vite build` | ✅ builds (396 kB JS / 368 kB HTML) with warnings |
| Root Vite app | `npm install` | ❌ **ERESOLVE** — `@builder.io/vite-plugin-jsx-loc@0.1.1` peers `vite@^4||^5`, project pins `vite@7.1.9` |
| Root Vite app | `npx pnpm@10.4.1 install` | ✅ works (651 pkgs) — **pnpm is mandatory, npm is broken** |
| `frontend/` (Next 14) | `npx tsc --noEmit` | ❌ **6 syntax errors in 5 files** |
| `frontend/` | `npx next build` | ❌ **fails to compile** |
| `apps/dashboard/` (Next 14) | — | no lockfile committed; CI cache path points at a file that doesn't exist |

---

## 4. Blocking defects

### 4.1 `frontend/` does not compile — JSX expressions are missing closing braces

`next build` fails; therefore `ci.yml`'s `frontend` job fails, and `ci.yml`'s `docker-build` job (`needs: [backend, frontend]`) never runs; `cd.yml` can't build the frontend image either.

All six are the same class of typo — a `}` dropped before a closing tag — and the misaligned indentation around each suggests a botched automated edit:

| File | Line | Now | Should be |
|---|---|---|---|
| `frontend/app/assets/[urn]/page.tsx` | 15 | `<p>{safe</p>` | `<p>{safe}</p>` |
| `frontend/components/AuthGuard.tsx` | 31 | `return <>{children</>;` | `return <>{children}</>;` |
| `frontend/components/PolicyTweaker.tsx` | 125 | `<div ...>{policy.name</div>` | `{policy.name}</div>` |
| `frontend/components/PolicyTweaker.tsx` | 190 | `<span ...>{label</span>` | `{label}</span>` |
| `frontend/components/PolicyTweaker.tsx` | 191 | `<span ...>{value</span>` | `{value}</span>` |
| `frontend/components/VerdictCard.tsx` | 205 | `<div ...>{value</div>` | `{value}</div>` |

`AuthGuard.tsx` also has a stray mis-indented `</div>` at line 28, and `VerdictCard.tsx` at line 207.

### 4.2 `supervisor/` IPC is fatally broken — clients hang forever

`supervisor/src/workflo_supervisor/ipc.py`:

- line **161** — `import threading` is **inside the method** `SupervisorServer.start()`
- line **168** — `_serve_loop()` (module scope) calls `threading.Thread(...)` → **`NameError: name 'threading' is not defined`**

Consequence: the moment any client connects, the accept loop dies and the connection is never serviced. The client then blocks on `sock.recv(4)` (line 67) with **no socket timeout**, so callers hang instead of erroring.

Reproduced independently:

```
$ python -c "…SupervisorServer('/tmp/t.sock').start(); connect; send RPC…"
Exception in thread Thread-1 (_serve_loop):
  File ".../workflo_supervisor/ipc.py", line 168, in _serve_loop
    threading.Thread(target=self._handle_connection, args=(conn,), daemon=True).start()
NameError: name 'threading' is not defined
```

`supervisor/tests/test_ipc.py::test_client_server_roundtrip` hangs indefinitely (the suite has no timeout configured; I needed `pytest-timeout` to get a stack). `test_server_start_stop` passes only because it never connects.

**Fix:** hoist `import threading` (and `struct`/`json`) to module level, add a client socket timeout + error, and add `pytest-timeout`/`asyncio` timeouts to the suite. Note `daemon.py` *does* import `threading` at module level — only `ipc.py` is broken.

### 4.3 `workflo-cli` depends on `supervisor/` but nothing declares or installs it

- `apps/workflo-cli/src/workflo_cli/supervisor_client.py:10` → `from workflo_supervisor.ipc import SupervisorClient`
- `apps/workflo-cli/pyproject.toml` dependencies: schema, sandbox-isolation, executor, probe-engine, cortex-auth — **no `workflo-supervisor`**
- `.github/workflows/workflo-cli.yml` installs those five packages, **not** `supervisor/`
- **No workflow anywhere references `supervisor/`** (verified by grep across `.github/workflows/`)

Result: all 7 CLI test files fail at collection (`ModuleNotFoundError: No module named 'workflo_supervisor'`) for anyone following the README install steps, and the `workflo-cli` CI job is red. After `pip install -e supervisor` → **119 passed** (exit path in `SupervisorCLIClient.run` falls back to local execution only if supervisor *isn't running*, not if the import fails).

### 4.4 Two packages install the same `workflo` console script

- `apps/agent-cli/pyproject.toml` → `workflo = "workflo_agent.cli:main"`
- `apps/workflo-cli/pyproject.toml` → `workflo = "workflo_cli.main:cli"`

Installing both into one environment silently clobbers one entry point (currently `workflo_cli` wins). Rename one (e.g. `workflo-agent`) or merge the CLIs.

---

## 5. CI/CD problems (verified against the actual files)

| Workflow | Problem | Consequence |
|---|---|---|
| `ci.yml` | `docker compose up -d --wait` then `curl localhost:8000/health`, but **`docker-compose.yml` defines only `db`, `redis`, `minio`** — no backend/frontend service | Smoke test can *never* pass |
| `ci.yml` | `frontend` job runs `tsc` + `next build` | Red (§4.1); blocks `docker-build` |
| `linux-gate.yml` | Runs `packages/sandbox-runtime/tests -q -x` on `ubuntu-latest` | Red — 4 tests there assume a host *without* Landlock (§6.1) |
| `workflo-cli.yml` | `pytest --timeout=120` but `pytest-timeout` is not in the CLI's `[dev]` extra | `unrecognized arguments: --timeout=120` → job aborts (reproduced locally) |
| `dashboard.yml` | `cache-dependency-path: apps/dashboard/package-lock.json` — **no lockfile exists** | Cache step errors/warns; build unpinned |
| `workflo-npm.yml` | `pip install`-free wheel build + `npm pack` — fine, but publishes on release only | OK; paths all resolve (`packages/npm-workflo/scripts/*` exist) |
| `validate.yml` | `continue-on-error: true` on the gate itself; `MODEL_ENDPOINT` from a secret that may be unset | Gates may "pass" without running |
| `benchmark.yml` | `Upload REPORT.md` with `if-no-files-found: warn` | Silent no-op if benchmark produced nothing |

Also: **`supervisor/`, `website/`, `apps/dashboard` type-check, `workflo-ai-integration/`, and the AI-router tests are not covered by any workflow.**

### 5.1 The root lockfile is stale — frozen installs fail

`pnpm-lock.yaml` does **not** match `package.json`: the lockfile is missing the `npm-workflo: file:./packages/npm-workflo` dependency that `package.json` declares. Verified:

```
$ pnpm install --frozen-lockfile          # default in CI
ERR_PNPM_OUTDATED_LOCKFILE  Cannot install with "frozen-lockfile" because
pnpm-lock.yaml is not up to date with <ROOT>/package.json
```

`npm install` also cannot be used at the root (ERESOLVE, §3), so **any CI job that installs the root JS app fails before it builds anything**. Fix: `pnpm install --no-frozen-lockfile` and commit the result.

Two smaller lockfile notes: `frontend/package-lock.json` still carries the old project name `datahub-incident-autopilot-frontend` (leftover from a product rename — `npm ci` still passes, but it's a stale artifact), and **`apps/dashboard/` and `website/` have no lockfiles at all**, so their CI builds are unpinned.

---

## 6. Test-suite quality (failures that are test bugs, not product bugs)

### 6.1 Environment-dependent assertions (4 of the 5 `sandbox-runtime` failures)

`packages/sandbox-runtime/tests/test_landlock.py::TestProbeAbi::test_unsupported_platform_returns_zero` asserts `probe_abi() == 0` unconditionally, but `probe_abi()` correctly returns the kernel's Landlock ABI (this host: **2**). The three `test_supervisor_receipt.py` failures have the same root cause — they assert `landlock.requested is False`, expect hardened mode to refuse, and expect a `LANDLOCK_UNAVAILABLE` event, all of which are wrong on a Landlock-capable kernel.

These aren't product bugs; they are un-guarded platform assumptions that make the suite fail on exactly the platform `linux-gate.yml` runs it on. Guard with `pytest.mark.skipif(probe_abi() != 0, ...)` or split into marked `linux` tests.

### 6.2 Test referencing a file that doesn't exist (5th failure)

`packages/sandbox-runtime/tests/test_bench_inference.py::test_direct_mode_against_stub` loads `bench/model-serving/bench_inference.py`. **There is no `bench/` directory in the repo at all** → guaranteed `FileNotFoundError` in every environment. Either the file was never committed or the test is stale.

### 6.3 Brittle string assertion

`apps/validation-cli/tests/test_sandbox_isolation.py::test_gate_command_does_not_leak_host_path` asserts `"tmp" not in result.command.lower()` while `result.command` embeds `sys.executable`. It fails in any venv under `/tmp` (my case), and would also fail for `C:\Temp`. Assert against the *actual* tmpdir path, not the substring `tmp`.

### 6.4 Tests mutate a committed data file (non-hermetic)

Running the `backend` suite **appends rows to `backend/data/writeback.jsonl`**, a tracked file (my run added 9 lines, which I reverted). Tests should use `tmp_path`/`WRITEBACK_PATH` override instead of writing to a committed data file — otherwise every CI run produces a dirty tree and the file grows unbounded. The same applies to `backend/data/test_writeback.jsonl` and the committed `backend/data/chromadb/` binary store.

### 6.5 Other

- `apps/validation-cli/pyproject.toml` sets `timeout = 60` but doesn't guarantee `pytest-timeout` → `PytestConfigWarning: Unknown config option: timeout` (the option is silently ignored, so gates can hang).
- `packages/workflo-schema` emits `PytestCollectionWarning` for `TestResult`/`TestTargets` Pydantic classes (pytest thinks they're test classes) — harmless, but `__test__ = False` would silence it.
- Pydantic `protected_namespaces` warnings on `model_inference_*` fields in schema models.

### 6.6 Coverage (`backend/`, 70% overall)

Untouched at **0%**: `app/db/models.py` (66 stmts), `app/db/session.py` (42), `app/db/migrations/env.py` (37), `app/db/migrations/versions/001_init.py` (24), `app/connectors/datahub/gms.py` (138), `app/core/config.py` (8), `app/models.py` (23).

Lowest covered: `app/services/autopilot.py` **45%**, `app/core/auth.py` **46%**, `app/connectors/snowflake/connector.py` **40%**, `app/api/assets.py` **48%**, `app/core/llm.py` **31%**, `app/api/incidents.py` 53%, `app/api/scenarios.py` 56%, `app/engine/recommendation_ranker.py` 55%.

The DB layer is essentially unexercised (only `resolution_repo.py` uses it) — fine if intentional, but it means the persistence path is unproven.

Good news: 374 asserts across 3.5k lines of tests, and the `control-plane` suite covers the newest features (tenant RLS, audit, envelope, key provisioning, inference gateway).

---

## 7. Architecture & code-health observations

1. **Duplicated layers in `backend/`** — `app/engine/` and `app/services/` both exist, and five modules (`explanation_builder`, `future_search_engine`, `impact_engine`, `recommendation_ranker`, `scenario_engine`) are byte-for-byte **re-export shims** in `services/` pointing at `engine/`. `services/impact_analyzer.py` (16 lines), `fix_generator.py`, `incident_detector.py`, `graph_builder.py`, `recommendation_engine.py` are separate implementations.
2. **Empty modules** — `backend/app/services/{datahub_adapter,datahub_client,mock_store}.py` are 0 bytes (3 of 8).
3. **Duplicate DataHub clients** — `connectors/datahub/gms.py` and `services/datahub_gms.py` are near-identical 340/138-line implementations of the same `TokenBucketRateLimiter` + GMS client.
4. **Two backends, three CLIs, three dashboards** — `backend/` vs `apps/control-plane/`; `workflo-cli` vs `agent-cli` vs `validation-cli`; `client/` (Vite) vs `frontend/` (Next) vs `apps/dashboard/` (Next) vs `website/` (Next).
5. **Legacy shim with a typo** — `backend/app/core/config.py:13` defines `WRITERBACK_PATH = settings.WRITEBACK_PATH` (and it's 0% covered).
6. **Docstring documents a class that doesn't exist** — `backend/app/middleware/auth.py` advertises `AuthMiddleware`; there is no such class, and the real middleware stack (`main.py`) never adds one. `PUBLIC_PATHS` is referenced only inside that module.
7. **Unused declared dependencies in `backend/`** — `slowapi` (0 imports), all four `opentelemetry-*` packages (0 imports), and `RATE_LIMIT_PER_MINUTE` is declared but never read. `chromadb` is only used behind a try/except fallback.
8. **Committed build artifacts** — `frontend/tsconfig.tsbuildinfo`, `backend/data/chromadb/**/*.bin` (binary vector store), `data/writeback.jsonl`, and 6 vendored `.whl` files in `packages/npm-workflo/vendor/`. `.gitignore` ignores `*.tsbuildinfo` yet one is tracked.
9. **`workflo-ai-integration/workflo-ai-integration/`** — double-nested directory (likely a bad extraction).
10. **`apps/control-plane/app/main.py`** — ~700 lines, mostly inline HTML/CSS/JS templates; also a duplicated `from app.api.v1.audit import router as audit_router` import.

---

## 8. Dependency vulnerabilities (from `npm audit` / `pnpm audit`)

### `frontend/` — 4 vulnerabilities (3 high, **1 critical**)

`next` is pinned **exactly** (`"next": "14.2.5"`, no caret), so none of the 14.2.x security patches apply. Advisories include *Next.js Cache Poisoning* (`GHSA-gp8f-8m3g-qvj9`) plus `postcss` and `source-map-js` issues. `npm audit` reports the fix as "outside the stated dependency range" **only because of the exact pin** — the patched `next@14.2.35` is in the same major line, so this is a one-line change (`^14.2.35`).

`website/package.json` pins the same vulnerable `next: "14.2.5"`.

### Root app — 152 vulnerabilities (5 critical, 53 high, 82 moderate, 11 low)

Mostly dev/build tooling (`pnpm` itself, `vitest`, `tar`, `tinypool`), but note:

- **`axios ^1.12.0` is declared as a runtime dependency and is never imported anywhere** (`client/src`, `server/`, `shared/` all have 0 references). It accounts for ~11 of the high advisories. Drop it.
- `express@4.21.2` (runtime) pulls the critical **`proxy-addr`** IP-spoofing advisory and a **`path-to-regexp`** ReDoS.
- `nanoid ^5.1.5` (runtime, direct) is flagged.
- `pnpm.overrides` pins `tailwindcss>nanoid` to **`3.3.7`**, while the 3.x nanoid advisory range is `<3.3.18` — the override keeps a vulnerable version deliberately pinned. Bump it.
- `recharts 2.15.4` is deprecated upstream (v3 migration available) and pulls `lodash@4.17.21` (code-injection advisory).

**Caveat:** audit output over-reports for a dev/build tree; the actionable items are `next` (both Next apps), the unused `axios`, the `nanoid` override, and `express`.

---



## 9. Security posture

### Strengths (these are genuinely well done)

- **Argon2id** password hashing with an explicit "no SHA-256 fallback" rationale in the docstring — fail-fast rather than silent downgrade.
- API keys and OAuth tokens hashed with **PBKDF2-HMAC-SHA256 (100k iterations, per-value salt)** and compared with `secrets.compare_digest`.
- Hand-rolled HS256 JWT verification that **never trusts the header's `alg`** (recomputes HMAC-SHA256) → no algorithm-confusion class of bug.
- **Device-flow identity binding**: `/device` approval requires a valid Bearer token and binds the real `user_id` to the code — explicitly to avoid issuing tokens for a demo placeholder.
- **Envelope encryption** (`wfenc1:v{n}:…`) with per-organization DEKs, KEK/unwrap seam, legacy-plaintext read path, and rotation-friendly versioning.
- **Row-level security SQL** (`db/rls/001_tenant_rls.sql`) bound per-transaction via `set_config(..., true)` so pooled connections can't leak tenant context.
- Audit service with correlation IDs (`X-Request-ID` honored and echoed).
- `AuthGuard` + CSP with `unsafe-eval` deliberately omitted in the Next config.
- No hardcoded secrets found; only test fixtures (`fake-access-token`, `wf-placeholder-key`) — good.

### Gaps worth closing before any public deployment

| Issue | Location |
|---|---|
| `jwt_secret` defaults to `"change-me-in-production"`; **no fail-closed production guard** | `apps/control-plane/app/core/config.py:14` |
| Credential sealing is **off by default** (`master_kek_hex=""` → `is_enabled()` False, plaintext hashes stored); the doc says "release checks *can* assert" — nothing does | `app/core/envelope.py` |
| `rls_enabled=False` by default, so the RLS tripwire is inert unless set | `app/core/config.py:35` |
| Tables are created with `Base.metadata.create_all` in the app lifespan — no migration/Alembic path for the control-plane (`backend/` has Alembic) | `app/db/database.py:63` |
| Broad `except Exception: return None` in token verification hides real errors | `app/core/crypto.py` |
| `/health/detailed` is public (no auth dependency) and reports per-connector status/uptime | `backend/app/main.py` |
| `PUBLIC_PATHS` lists `/metrics` as public while the route actually requires auth — inconsistent authorization declarations | `backend/app/middleware/auth.py:18` |
| No `SECURITY.md` / vulnerability disclosure path | repo root |

---

## 10. Frontend/runtime notes

- **Root app is Manus-platform-coupled.** `vite.config.ts` hard-wires `vite-plugin-manus-runtime`, a debug collector writing `.manus-logs/`, a `/manus-storage` proxy requiring `BUILT_IN_FORGE_API_URL`/`BUILT_IN_FORGE_API_KEY`, and `server.allowedHosts` restricted to `*.manus*.computer` + localhost. **Any other host (e.g. a `*.e2b.app` preview) is rejected → blank page.** Add the host or make `allowedHosts` configurable.
- The built `index.html` references `/manus-storage/workflo-sandbox-immersive-hero_b63d7110.jpg` which Vite explicitly could not resolve → **hero image 404s without the Manus proxy**.
- Build leaves `%VITE_ANALYTICS_ENDPOINT%` / `%VITE_ANALYTICS_WEBSITE_ID%` unsubstituted (Umami script tag is broken).
- `frontend/lib/api.ts` defaults to `http://localhost:8000` client-side and the Next CSP `connect-src` only allows localhost — production needs both env vars set.
- `packages/npm-workflo` vendors wheels pinned at `1.1.1`, matching package versions — consistent (good).

---

## 11. Licensing & docs consistency

- Root `LICENSE` = **MIT**; `HACKATHON.md` says **Apache-2.0**; `README.md` says "MIT / Apache 2.0".
- Per-package metadata disagrees: **"Proprietary"** for `cortex-auth`, `probe-engine`, `sandbox-isolation`, `workflo-cli`, `sandbox-executor`; **Apache-2.0** for the rest; npm packages **MIT**.
- `CONTRIBUTING.md` points at `github.com/cortex-autopilot/cortex-autopilot`, while the npm package repository points at `github.com/cortexstudio/workflo` and the actual remote is `Kshitij-Tripathi87/workflo`.
- `docs/benchmark_results_2026.md` is honestly labelled **"Source: synthetic"** (p50 0.02 ms, 10,000/10,000 success, 0% false-negative rate) — that framing is fine, but those numbers shouldn't appear in marketing copy without the synthetic caveat.
- Docs are otherwise strong: 28 files covering API contract, policy, connectors, validation, install, architecture.

---

## 12. Suggested fix order

**Unblock CI (hours)**
1. Add the missing `}` in the 5 `frontend/` files — `next build` then works (§4.1).
2. Fix `supervisor/src/workflo_supervisor/ipc.py` (module-level `import threading`) + add client socket timeout (§4.2).
3. Declare `workflo-supervisor` as a dependency of `workflo-cli`; add `supervisor/` to a workflow (§4.3).
4. Regenerate the root lockfile (`pnpm install --no-frozen-lockfile` + commit) — frozen installs fail today (§5.1). Consider committing lockfiles for `apps/dashboard/` and `website/` too.
5. Guard the 4 Landlock assumptions and delete/fix the `bench/model-serving/` test (§6.1–6.2).
6. Either add app services to `docker-compose.yml` or drop the smoke-test step; add `pytest-timeout` to `workflo-cli`'s dev extra; fix the `dashboard.yml` cache path (§5).
7. Rename one of the two `workflo` console scripts (§4.4).
8. `next` → `^14.2.35` in `frontend/` and `website/`; drop the unused `axios`; bump the `nanoid` override (§8).
9. Stop tests writing to `backend/data/writeback.jsonl` (§6.4).

**Hardening (days)**
10. Fail-closed on default `jwt_secret` / missing KEK / disabled RLS when `environment == "production"` (§9).
11. Make `allowedHosts` and the storage proxy configurable so the Vite app runs off-Manus (§10).
12. Delete the re-export shims and 0-byte modules; pick one DataHub client (§7.1–7.3).
13. Drop unused deps (`slowapi`, OpenTelemetry) or wire them up; add auth to `/health/detailed` (§7.7, §9).
14. Reconcile licensing (one license per package, matching the root) and fix the stale repo URLs (§11).

**Structural (weeks)**
15. Decide whether `backend/` and `apps/control-plane/` are one service or two; same for the three CLIs and three dashboards (§7.4).
16. Pick one product name (Workflo vs Cortex vs Tenant Shield) and normalise env-var prefixes (§1).
17. Add coverage floors for the untested DB/persistence path (§6.6).

---

---

## 13. Remediation status (2026-10-08)

The staged fix-up directed after this review is complete for P0–P3. Every item
below was verified by running it, not by inspection; the two defects marked
"found during remediation" were invisible to the old CI because `mypy` was run
as `mypy ... || true`.

### P0 — build and runtime blockers

| Item | Result |
| --- | --- |
| `frontend` build | `tsc --noEmit` 0 errors; `next build` PASS (was: 6 JSX syntax errors + 3 masked type errors) |
| `website` build | Same corruption class found (7 sites incl. an HTML entity decoded into raw `<1ms`); `tsc` 0, `next build` PASS — it had **no CI**, which is why the breakage survived |
| `apps/dashboard` build | `tsc` 0, `next build` PASS |
| supervisor IPC | `import threading` was local to `start()` (so `stop()` raised `NameError`) plus client hangs were unbounded; fixed, `start(); stop()` is idempotent, client timeouts now raise instead of blocking |
| regression proof | supervisor suite 12 passed (was 1P/1F); defect-reintroduction check turned it red again |
| `setup.sh` | called `docker compose up -d postgres backend` / `... frontend`, but compose only defines `db`, `redis`, `minio` — the one-command setup could never work. Rewritten against the real service names and run end-to-end (exit 0, both services healthy) |

### P1 — dependency graph, CI, and the security gate

| Item | Result |
| --- | --- |
| Next.js | `frontend`, `website`, `apps/dashboard` all on **15.5.27**; every Next-14-line advisory requires `>= 15.5.24`. `npm audit` for frontend went 4 → 2 (the remaining two are `postcss` bundled inside `next` itself) |
| clean install | `npm ci` verified in all three apps; `website`/`apps/dashboard` had **no committed lockfile** (so `npm ci` could never run) — both are now committed |
| pnpm | `pnpm install --frozen-lockfile` (twice, from a state with no `node_modules`) exit 0; `pnpm check` exit 0; `pnpm test` 9/9 |
| `ci.yml` | `mypy ... \|\| true` removed (now a real gate: 0 errors in 101 files); npm-for-frontend job replaced by a Next.js matrix over all three apps; new pnpm workspace job; dead `docker compose up -d --wait` + `curl localhost:8000` smoke test replaced with what compose actually defines |
| `linux-gate.yml` | **was not even valid YAML** (unquoted colons in step names, lines 27 and 70) — GitHub could never run it. Fixed; its unit step is verified locally (475 passed) |
| false-green specifics | `workflo-cli.yml` needed `pytest-timeout` for `--timeout=120`; `apps/workflo-cli` deps now declare `sandbox-runtime` + `workflo-supervisor` so the CLI suite can import its own client |
| capability-dependent tests | the Landlock tests asserted a *non-Linux* posture (`assert probe_abi() == 0`), so they failed on any Landlock host. They now branch on `probe_abi()` and assert the supported path — verified green on this Linux host **and** with Landlock forced unavailable |
| missing artifact | the bench-harness test now skips with an explicit reason instead of failing on a directory that was never committed |

### P2 — production fails closed

`apps/control-plane/app/core/startup_guards.py`, wired into `create_app()`:

| Condition | Result |
| --- | --- |
| `PRODUCTION=true` or `ENVIRONMENT=production` with the default `jwt_secret` | `ProductionConfigError`, process exits 1 |
| ... with `RLS_ENABLED=false` | same |
| ... with no usable KEK (`MASTER_KEK_HEX` empty, malformed, or an unavailable provider) | same |
| fully configured production | starts normally |
| tests | 20 new tests (each variable driven away from a *valid* production config in turn); deleting the guard call from `create_app()` turns one red; control-plane suite 123 passed |

### P3 — tests, boundaries, dead weight

| Item | Result |
| --- | --- |
| tests writing tracked files | the suite appended sample incidents to the committed `backend/data/writeback.jsonl`. `WRITEBACK_DIR` now makes the mirror's confinement base explicit (traversal rejection unchanged), the test conftest points it at a temp dir, and a regression test fails if that redirection is removed. Verified: full suite leaves the tree clean, and it passes with the data files absent (fresh-clone parity) |
| untracked generated state | `backend/data/**`, `data/`, and `frontend/tsconfig.tsbuildinfo` were tracked; now untracked + ignored (files kept on disk) |
| dead shims removed | `app/services/{datahub_adapter,datahub_client,mock_store}.py`, `app/core/config.py` (this also removes the `WRITERBACK_PATH` typo), and `app/models.py` (shadowed by the `models/` package) — all verified to have zero importers |
| unused deps | `slowapi` + the five `opentelemetry-*` packages removed from `backend/requirements.txt` (zero imports repo-wide) |
| boundaries | `PRODUCT_BOUNDARIES.md` — every top-level directory classified Active / Supporting / Legacy / Quarantine with the evidence used |
| config that could not work | the three issue templates were Markdown templates saved as `.yml`, which GitHub parses as issue *forms*; renamed to `.md` with `about:` |

### Defects found *because* the gates became real

1. `DataHubGMSClient.__init__` called `.rstrip("/")` on a pydantic `AnyHttpUrl` → `AttributeError` on every real (non-mock) DataHub connection. mypy had reported it all along.
2. `FutureScenario.scenario_type` was missing `assign_owner`, so `generate_futures()` raised `ValidationError` for any asset without an owner — the product's flagship scenario — reachable from `/future-search`.
3. LLM-supplied `action_type`/`severity` were passed straight into literal-typed models in `_tool_write_back`, aborting the whole agent task on an unexpected value (previously hidden behind `# type: ignore`).

### Verified state after the pass

backend 170 · control-plane 123 · CLI 119 · supervisor 12 · sandbox-runtime +
schema 475 · root vitest 9 · three Next apps tsc+build green · `ruff` and `mypy`
clean (backend) · `pnpm install --frozen-lockfile` + `check` + `test` green from a
clean checkout.

Nothing in the P3 "Quarantine" list was deleted — those need an owner's call.
The website redesign gate is met: clean build, clean dependency graph, green CI,
fail-closed production config, documented boundaries.

---

## 14. P4 preparation (2026-10-08, follow-up)

Review feedback on §13 raised two release blockers and one framing correction;
both are closed and the framing is adopted.

### Blocker 1 — the skipped benchmark test

"Missing implementation -> SKIP -> green" is not an acceptable state for a test
guarding the model-serving economics, so the harness now exists:
**`bench/model-serving/bench_inference.py`** (throughput, latency percentiles,
decode throughput, and unit cost across concurrency levels, against any
OpenAI-compatible endpoint — `infra/vllm` locally). The test no longer skips; a
missing harness is a hard failure.

Two deliberate choices. It does not invent a cost figure: the hourly instance
rate is a required, recorded assumption, and every cost number is labelled an
estimate, because no infra cost exists anywhere in the repo. And it exercises
failure paths, not just the happy path.

What has been verified: the test passes against a local stub server, and a dead
endpoint exits 1 with the partial report retained (the "model unavailable"
negative path, N8 in `P4_ACCEPTANCE.md`).

The stub answers after a fixed 50 ms. The throughput printed during that check
(about 19 / 39 / 77 rps at concurrency 1 / 2 / 4) therefore validates the
harness's arithmetic and nothing else. It is **not a model measurement**. Cost
per request is `hourly / (rps x 3600)`, so it scales inversely with throughput
by construction. The first real figures come from running the harness against
vLLM (P4 item 6).

### Blocker 2 — quarantine disposition

Every previously-ambiguous item now has an explicit state (KEEP / MERGE /
MIGRATE / ARCHIVE / DELETE) with evidence — see `PRODUCT_BOUNDARIES.md`. The
double-nested extraction was **flattened**, and the finding that changed the
disposition is the kit's own README: *"Standalone scaffolding for the
LoRA-adapter path... Meant to be merged into the real sandbox worker once
adapters exist."* That makes it **MERGE**, and P4-relevant — `safety_gate.py` is
the compile-check gate between generated code and the sandbox, `model_router.py`
is the adapter routing. Its 24 mock-based tests passed but no CI ran them; a new
`ai-integration` CI job now does.

### The gate that could still lie

`linux-gate.yml` returns 0 whenever the integration tests *skip* — which is what
happens when provisioning half-fails (no root, no bwrap/nft/dnsmasq, no runtime
image, no Landlock). A security gate that reports success after verifying
nothing is exactly the false green this work exists to remove. Both suites now
emit junit reports and assert: no silent skips in the integration gate, and a
minimum executed count in each. Verified against fabricated reports — 33
collected / 33 skipped / 0 failed now exits 1.

### Defect found by re-running with full dependencies

With chromadb installed (fresh setup, offline), `TestContextStore` failed for a
real reason: ChromaDB's default embedder **downloads its model on first use**, so
inside the `--network none` sandbox this product runs in, every upsert/query
fails. The in-memory fallback only engaged when chromadb was *absent*, and both
`_index_document` and `retrieve_context` swallowed the exception — so RAG
silently returned nothing while the store looked healthy. Readiness is now
probed and every downgrade is logged; two regression tests pin it, and removing
the probe fails them. This is the fourth real defect the honest gates exposed.

### Framing

Repo integrity is not product readiness. The remaining proof is real execution:
sandbox -> model -> exploration -> confirmation -> receipt -> independent
verification. That chain, its negative paths, and the runnable subset are
specified in **`P4_ACCEPTANCE.md`**; nothing there is claimed as passing that
was not run.

---

## 15. Review pass — 2026-11-27 (backup workspace)

**Method:** installed all 20 Python projects editable into one interpreter
(none of them were installed; 12 of 18 suites failed at *collection* with
`ModuleNotFoundError`, which is an environment gap presenting as a code
defect), then ran every suite + the type checkers. Security review concentrated
on the control plane's authentication and authorization paths, because that is
the only code in the tree that decides "may this caller see this row".

### 15.1 Baseline measured, not assumed

| Suite | Result after install |
| --- | --- |
| `apps/control-plane` | 158 passed, 1 skipped (**170** after this pass) |
| `apps/workflo-cli` | 126 passed |
| `apps/worker-engine` | 202 passed, **2 failed** |
| `apps/agent-cli` | 34 passed |
| `apps/sandbox-executor` | 55 passed |
| `apps/validation-cli` | 64 passed, 4 deselected |
| `packages/workflo-schema` | 285 passed |
| `packages/sandbox-runtime` | 309 passed, 35 skipped, **1 flaky** |
| `packages/sandbox-isolation` | 85 passed |
| `packages/probe-engine` | 23 passed |
| `packages/cortex-auth` | 42 passed |
| `packages/workflo-utils` | 37 passed |
| `packages/workflo-datahub` | 19 passed |
| `supervisor` | 12 skipped (Unix sockets — Windows host) |
| `worker` | 143 passed, 2 skipped |
| `backend` | 171 passed, **1 failed** (needs `chromadb`) |
| `workflo-ai-integration` | 116 passed, 1 skipped |

The two `worker-engine` failures are platform assumptions, not product defects:
`os.getuid()` does not exist on Windows and `/usr/local/bin/llama-server` is a
Linux path, in tests not marked Linux-only. The `backend` failure is a missing
optional dependency (`chromadb`) in a test of the *degradation* path.

### 15.2 Findings and what was done about them

| # | Severity | Finding | Disposition |
| --- | --- | --- | --- |
| 1 | **Critical** | `GET /v1/runs/{id}/artifacts`, `/results`, `/report` had **no authentication and no tenant check**. `artifacts_router` is mounted at `/v1` with no global dependency, and the handlers themselves took no `Depends`. Any anonymous caller holding or guessing a run id could read another tenant's test results, assertion text, captured errors and artifact storage paths (broken object-level authorization, OWASP A01). | **Fixed** — `require_api_key` on all three + ownership check returning 404 on mismatch (indistinguishable from missing). 9 regression tests. |
| 2 | **High** | `POST /v1/keys` accepted an **anonymous, client-supplied `project_id`** outside production — an unauthenticated write that mints an admin-capable key for any tenant's project id, auto-creating the project if absent. `is_production()` was the only guard, so staging was wide open. | **Fixed** — default-closed `ALLOW_ANONYMOUS_KEY_BOOTSTRAP` flag for local dev, and an authenticated caller can only mint keys for its own project (`project_id` in the body is ignored). 2 regression tests. |
| 3 | **High** | `verify_bearer_token` selected **every** `OAuthToken` row and ran PBKDF2-HMAC-SHA256 (100k iterations) against each one, per request, across all tenants. O(total tokens) CPU per request, triggerable at will by any caller holding one valid token. | **Fixed** — candidate set scoped by the `sub` claim of the already-verified JWT, revoked rows excluded in SQL. |
| 4 | **High** | Same all-rows + PBKDF2 pattern in `oauth.py` `_handle_refresh_grant` and `oauth_revoke`, on **unauthenticated** endpoints: no credential is needed to make the server hash-loop over the whole token table. | **Mitigated** — per-IP rate ceiling (`check_credential_rate_limit`, 120/min) on both endpoints. A full fix needs a deterministic lookup digest column; see 15.3. |
| 5 | Medium | `api_key_service.validate_key` still scans every API-key row across all tenants, revealing each row under *its own* project context to do so. Correctness is fine (PBKDF2 still decides), but it is the same O(n) amplification for the API-key path, which is the *primary* auth path. | **Documented**, fix designed in 15.3 (needs a schema column). |
| 6 | Medium | No reproducible Python bootstrap: ~20 separate setuptools projects, no lockfile, no workspace, and README install steps that only cover 5 of them. | **Fixed** — `scripts/python-env.sh` (`install` / `test` / `list`) + `make python-install`, `make python-test`. |
| 7 | Low | `security.py` docstring claimed `X-API-Key` takes precedence over `X-Workflo-Key`; the code checks `X-Workflo-Key` first. | **Fixed** — precedence is now the `_API_KEY_HEADERS` tuple, used by both the required and optional dependencies so they cannot drift. |
| 8 | Low | `apps/worker-engine` has 2 tests that can only pass on Linux but are collected everywhere. | Documented; mark with the existing `linux` marker. |
| 9 | Low | `packages/sandbox-runtime` has one flaky test (passes on re-run; not reproducible in two attempts). | Documented. |
| 10 | Process | No `[tool.ruff]` / `[tool.mypy]` anywhere, so `ruff` with current defaults reports **222** findings in the control plane alone — all style noise that hides real findings. | Documented; ruleset is a decision, not a cleanup (see 15.4). |

### 15.3 Designed, not yet implemented: credential lookup indices

The PBKDF2 columns use a **random per-value salt**, which is correct for storage
but makes the hash unusable as a lookup key — hence every verifier scans the
table. The fix is a deterministic, indexed lookup column:

```
api_keys.lookup_digest            -- HMAC-SHA256(lookup_key, raw_key)
oauth_tokens.access_lookup_digest -- HMAC-SHA256(lookup_key, raw_access)
oauth_tokens.refresh_lookup_digest
```

`lookup_key` must be a **dedicated** secret (not `jwt_secret`): rotating
`jwt_secret` must not invalidate every issued credential, and rotating
`lookup_key` does. Verifiers become `WHERE lookup_digest = :d`, then one PBKDF2
compare. Rows with a NULL digest (pre-migration) keep the bounded scan path
until backfilled. This is the correct fix for findings 4 and 5 and should land
with its migration before any multi-tenant deployment.

### 15.4 What this pass did **not** review

Stated plainly so nobody mistakes a green suite for a cleared codebase:

- `client/`, `frontend/`, `website/`, `apps/dashboard/` — no JavaScript/TypeScript
  read in this pass; they hold no server-side authorization logic, but they are
  unreviewed.
- `backend/` business logic (Cortex) — exercised by its suite, not read line by
  line. It is a separate product surface per `PRODUCT_BOUNDARIES.md`.
- `packages/sandbox-runtime/` kernel isolation code (bwrap/cgroups/netns/Landlock)
  — the security claims there are only provable by the real-namespace integration
  gate on Linux, which did not run here (35 skips on this host).
- `worker/` was reviewed in the previous pass (protocol, capability, framing);
  this pass only re-ran its suite.

### 15.5 Restructure: the decision this repo keeps deferring

The tree still carries **three products** (`PRODUCT_BOUNDARIES.md`), and the
duplication is structural, not cosmetic:

- two Python backends (`backend/`, `apps/control-plane/`),
- three CLIs (`workflo-cli`, `agent-cli`, `validation-cli`) — and **two of them
  register the same `workflo` console script**, so installing both silently
  clobbers one entry point,
- four frontends (`client/`, `frontend/`, `apps/dashboard/`, `website/`),
- 20 Python projects with no workspace tool, and 6 vendored wheels plus a
  3.7 MB `records.json` committed as fixtures.

Deleting a product is an owner decision, so this pass does not delete anything.
The order that *is* safe to execute, once the owner picks one product name:

1. Pick ONE Python backend and ONE CLI; archive the others by moving them under
   `archive/` in a single commit (history preserved, imports unchanged).
2. Rename the losing `workflo` entry point (immediate, one-line fix, no
   behaviour change) — this is the only structural defect in the list that is
   actively dangerous today.
3. Introduce `pyproject.toml` workspace tooling (uv) so the 20 projects resolve
   from one lockfile instead of 20 editable installs.
4. Move committed binary/fixture bulk (`records.json`, wheels) to a release artifact, then delete from the tree.

### 15.6 Follow-up pass: unauthenticated credential bootstrap

An AST sweep of every control-plane route (44 endpoints) for a missing auth
dependency found one more anonymous credential path:

- `POST /v1/auth/demo-token` returned a **fixed** API key carrying
  `run_tests`, `read_reports` and `admin` on project `default`. It was gated
  only on `is_production()`, i.e. on the deployment *label*: any staging,
  demo or self-serve host left at `ENVIRONMENT=development` handed an
  admin credential to an anonymous caller. Now default-closed behind
  `enable_demo_token` (production still always refuses), matching the
  `allow_anonymous_key_bootstrap` fix in 15.2, with regression tests for both
  the closed and opted-in paths. The CLI's keyless `--via-api` path now says
  which flag to set instead of reporting a bare HTTP 404.

The same sweep surfaced two lower-severity items that were left as designed
and are recorded, not fixed:

- `GET /v1/key-provisioning/{key_id}` is intentionally unauthenticated so any
  verifier can resolve a signing key. It returns the public key plus
  `user_id`, `organization_id` and `device_id`, so it is an anonymous
  identifier-enumeration surface for anyone holding a key id.
- `GET /v1/inference/health` discloses the configured upstream model name.

### 15.7 Second follow-up: sandbox isolation and the evidence/receipt path

Scope: `sandbox_runtime` network/teardown/bwrap/Landlock code,
`sandbox_isolation` transparency, receipt signing/verification, evidence
binding and the key directory, plus the control-plane dispatch path that
feeds them. Default Docker and bwrap behaviour is dev/CI only; the
Firecracker/KVM path is the production boundary and was **not** re-reviewed
here (unchanged by this pass).

#### Flaky transparency API test — root cause, not a test defect

`test_completed_run_appends_and_proves_inclusion` passed alone and failed in
the full suite. `DispatchService._finalize_success` called
`RunService.complete_run()` (committing `status = "completed"`) **before**
appending to the transparency log, so a reader polling in that window saw a
completed run whose ledger entry did not exist yet — exactly what the test
asserts. Two things were wrong and both are fixed:

- The append now happens **before** the completion commit. It stays
  best-effort (exceptions swallowed and surfaced in the audit trail), so a
  ledger write failure still cannot fail a finished run.
- `LocalTransparencyLog` serialised appends with an **instance** lock, but
  the control plane builds a fresh instance per append/proof call, so the
  lock never covered the real contention. Appends now take a cross-process
  file lock (`fcntl`/`msvcrt`) and reload the log under that lock before
  appending, so neither a second process nor a second instance can drop an
  entry. `merkle_root` / `verify_inclusion` were re-checked against RFC 6962
  and are correct; they are unchanged. Regression test:
  `test_concurrent_instances_append_without_colliding`.

#### Sandbox isolation fixes

- **Predictable `/tmp` network state.** nftables ruleset, dnsmasq conf, log
  and pid files used `/tmp/workflo-<sandbox_id>-*` names, which another local
  user could pre-create (symlink or clobber) between setup and use. They now
  live in a per-netns directory `/run/workflo/<netns>`, removed during
  teardown. A follow-up commit on the same branch strengthened this from
  "create and chmod 0700" to "create and then verify": an existing path that
  is not a directory, is not owned by the service uid, or is not exactly
  `0700` is rejected with `PermissionError` instead of being chmod'ed (chmod
  would preserve an attacker's ownership and keep the files replaceable), and
  the state directory now requires a POSIX runtime. Covered by
  `test_network_state_dir.py`.
- **Teardown verification misread empty output.**
  `verify_network_namespace_removed` treated empty `nft list` output as a
  live namespace; empty output now means "no rules", not "namespace
  present". The check still fails closed on anything it cannot parse.
- **Duplicated `_RULE_OPEN_FLAGS` block** in `sandbox_runtime/landlock.py`
  (two identical definitions, a merge artifact). Behaviour was unaffected —
  the second shadowed the first with the same value — but the dead copy is
  removed so the file has one source of truth for the `O_PATH|O_CLOEXEC`
  open flags.

#### Verified sound (no change)

- `landlock_exec.py` fails closed in both directions: `hardened` refuses to
  exec when Landlock is unavailable, invalid **or** apply-failed, and
  `compatible` continues loudly while recording the reduced isolation. An
  unreadable rules file returns 125 in both modes rather than degrading to
  "no Landlock". ABI masking happens before ruleset creation, and file rules
  are masked to file-rights so `/dev/null` no longer fails `ENOTDIR`.
- `Supervisor._landlock_outcome()` is fail-closed: no status files at all,
  an unreadable file, or any non-`LANDLOCK_APPLIED` status all reduce the
  attestation instead of reporting success.
- `receipt_signer` covers the key fingerprint in the signed payload, so a
  receipt cannot be re-attributed to a different key.
- `verify_receipts` rejects duplicate JSON keys, keeps `UNSUPPORTED_VERSION`
  distinct from `CORRUPT`, and treats an unrecognised failed check as a
  **hard** failure rather than downgrading it.

#### Recorded, not fixed

- **Evidence directory digests do not cover file names.**
  `evidence_binding._hash_directory` hashes file *contents* in sorted walk
  order, so renaming a file inside `logs/`, `traces/` or `artifacts/` keeps
  every digest valid, and a missing directory is indistinguishable from an
  empty one (both hash to the genesis constant). Cross-directory moves *are*
  caught, because both directory digests and the bundle digest change.
  Fixing this means hashing relative paths too, which changes the receipt
  format and invalidates every receipt already produced; it needs a version
  bump, not a quiet patch.
- **Claim #7 trusts the directory's `status` field alone.**
  `key_directory.check_key_status` reports `active`/`revoked` from the
  response body without comparing the directory's published key material to
  the fingerprint that actually signed the receipt. Unless the caller also
  passes `--fingerprint`, a directory answering `active` for a key id whose
  key differs from the signer still passes. The fingerprint comparison
  itself is correct when supplied.
- **`--key-directory` accepts any scheme and follows redirects.**
  `urllib.request.urlopen` will also open `file://` bases and follow HTTP
  redirects to another host. Only a locally supplied verifier argument is
  affected (the sandbox never reaches this code), so this is a hardening
  note, not an isolation hole.
- **Receipt parsing read the file twice** (strict duplicate-key scan after
  the main parse), which allowed the two checks to describe different bytes
  if the file were swapped between reads. Fixed in this pass: the file is
  read once and both parses use the same text.

#### Verification

- `apps/control-plane`: 185 passed, 1 skipped.
- `packages/sandbox-runtime`: 313 passed, 36 skipped.
- `packages/sandbox-isolation`: 85 passed (22 in `test_transparency.py`).
- Windows-only known gaps were unchanged by this pass (`os.getuid` in
  worker-engine, a missing `llama-server` binary, `chromadb` in
  `test_autopilot.py`).
- No security gate, sandbox flag, receipt schema or claim count was softened
  to make any of this pass.

### 15.8 Third follow-up: receipt assembly, evidence collector, teardown proof

Scope: `supervisor._build_receipt` / `_teardown` / `_landlock_outcome`,
`evidence.EvidenceCollector`, `teardown_proof`, `ephemeral_fs`,
`network_policy`, and the Docker executor path that consumes them. The
namespace runtime and the Docker executor are development/CI surfaces; this
pass says nothing about the Firecracker/KVM production boundary, which it did
not touch.

#### Fixed: the receipt claimed a tmpfs wipe that may not have happened

`ephemeral_fs.mount_tmpfs` mounts a real tmpfs only as root; everywhere else
it falls back to a plain directory on the host filesystem and sets
`_is_real_tmpfs = False`. Its own docstring promises that "the receipt MUST
reflect that the ephemeral guarantee is degraded", but the executor built the
proof with a literal:

```python
proof = build_teardown_proof(..., filesystem_wipe_method="tmpfs_umount")
```

Nothing read `_is_real_tmpfs`, so every non-root/CI/Windows run signed a
receipt claiming the code was destroyed by unmounting a RAM-backed filesystem
when it had actually sat on disk and been `rmtree`'d. That is the difference
between the architectural claim "your code never existed on a persistent
medium" and "we deleted a file".

Fix: `EphemeralMount` now carries a real `real_tmpfs` field (replacing the
`type: ignore` attribute poke) plus a `wipe_method` property, and the executor
records `mount.wipe_method` — `tmpfs_umount` for a real mount, `host_rmtree`
for the fallback. The field is a free-form string in the schema, so no
contract change was needed, and the change can only ever report less than the
old constant. Regression test:
`test_ephemeral_fs_reports_the_wipe_that_actually_happened`.

#### Recorded, not fixed (needs an owner decision)

- **`security_attestation.seccomp_applied` is a hardcoded `True`.** The schema
  documents it as "True when syscall allowlists were compiled and passed to
  every sandbox", and the attestation model's docstring says these values are
  "derived from observed outcomes … not from configuration intent". Every
  current workload call site does pass
  `seccomp_profile=get_seccomp_profile(...)`, so the literal is *currently*
  accurate — but nothing verifies it, `bwrap.build_bwrap_args` treats seccomp
  as optional (`if config.seccomp_profile is not None`), and any future call
  site that omits a profile would still produce a receipt attesting `True`.
  `network_isolated` has the same shape, derived as
  `network_config is not None` rather than from observed netns/nftables state.
  This is quoted evidence in a signed document, so per the path-ownership and
  security-review rules it needs an owner-approved change with two reviews
  rather than a drive-by edit. Suggested fix: thread the launched configs into
  the attestation and set `seccomp_applied` only when every launch actually
  carried a profile.
- **Producer-side and verifier-side evidence checks disagree on blank lines.**
  `evidence.compute_evidence_digests` / the outside verifier skip empty lines
  in `events.jsonl`; `evidence.verify_evidence_bundle` does not, so a blank
  line makes the producer-side check raise `JSONDecodeError` instead of
  returning `False`, while the verifier accepts the bundle. The verifier is
  the trust boundary and is currently the *more lenient* of the two; they
  should be made to agree deliberately.
- **Same-named evidence files are overwritten silently.**
  `EvidenceCollector.write_log`/`write_artifact` truncate
  `logs/<name>.log` and `artifacts/<name>`, so a second write inside one run
  replaces the first with no ledger event. Only the final bytes are bound by
  the bundle digest.
- **`verify_container_gone(None)` returns `True`** ("vacuously gone"). Correct
  for a run that never created a container, but it means a lost container id
  reads as a successful teardown rather than an unknown. Its docstring also
  says "three attempts with 200ms backoff" while the code sleeps 0.5s.
- **The ephemeral fallback is not recorded in the lifecycle events** even
  though `mount_tmpfs` says the executor must log it. The receipt field is now
  honest; the ledger still has no `ephemeral_fallback` event.

#### Verified sound

- Receipt assembly fails closed on missing observations: with no teardown
  verification the proof reports `container_removed=False` and
  `filesystem_removed=False`, and with no canary result it reports
  `request_succeeded=True`, which the verifier classifies as a hard failure.
  Neither defaults to "probably fine".
- `teardown_proof_fields` derives `container_removed` from three verified
  facts (processes terminated, cgroup removed, netns deleted), not from a
  cleanup command's exit status.
- Cgroup teardown drains `cgroup.procs` **and** `cgroup.threads` against a
  bounded deadline and reports `drained=False` with the surviving pids instead
  of asserting success.
- Redaction runs before `finalize()` and `build_binding()`, so the manifest and
  the signed binding cover the redacted bundle that a verifier recomputes.
- `network_policy.build_isolation_args` defaults to `network_mode: none`, adds
  hosts only for a control-plane endpoint resolved at creation, refuses to
  start when that resolution fails, and deliberately ignores
  `allowed_egress_hosts`.

#### Verification

- `apps/sandbox-executor`: 55 passed (identical to the pre-change baseline).
- `packages/sandbox-isolation`: 87 passed, including the new regression test.
- No schema, canonicalization, gate or claim count was changed.
