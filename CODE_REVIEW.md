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
