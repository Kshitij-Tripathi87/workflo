# workflo Flag Audit Checklist

Purpose: settle, with evidence not memory, which flags are (a) real and working,
(b) present but stubbed/heuristic-only, or (c) not implemented at all — before any
AI-integration work is scoped against them. Run `audit_flags.py` first to get a
first-pass automated report, then fill in the "AI-driven?" column below by hand,
since only a human (or a code read) can currently tell whether output came from
a model call or a static tool.

**Audited:** 2026-08-15 against this repo's CLI (`python -m workflo_cli.main run --help`
+ `--dry-run` per flag) and source under `apps/worker-engine`, `packages/probe-engine`,
`packages/sandbox-isolation`.

## How to use this

1. Run: `python audit_flags.py --workflo-bin workflo --repo <a-real-test-repo-url> --src-path /path/to/workflo/source`
2. Paste the generated report table below into the "Automated result" column.
3. For every flag, open the source file that implements it and check: does it
   construct a prompt and call an LLM endpoint, or does it call a static
   tool (Hypothesis, a hardcoded template, nothing)? Record in "AI-driven?".
4. Anything marked "Not implemented" or "Static only" becomes real scope for
   the AI-integration plan — not a bug to fix, a feature to build for the first time.

## Checklist

| Flag | Automated result (exit code / output) | AI-driven? (Y/N/Partial — cite the code path) | Verdict |
|---|---|---|---|
| `--test` | dry-run exit 0; `probe_groups: ["surface"]`; image `workflo-worker:latest` | **N** — native pytest only (`tenant_shield_worker/executor.py`) | **Working, deterministic** — leave alone |
| `--deep-test` | dry-run exit 0; `probe_groups: ["deep"]`; auto-selects `workflo-worker-deep:latest` | **Y (embedded Ollama)** — `_run_model_stage` → `ModelServer` (Ollama + Qwen2.5-Coder) → `generate_from_model_output` → pytest file. No LoRA adapters / no Hypothesis yet. | **Working, AI-driven (embedded)** — first real AI path; retrofit target for test-gen LoRA |
| `--aggressive-test` | dry-run exit 0; `probe_groups: ["aggressive"]`; same deep worker image | **Partial** — same `_run_model_stage` as deep; prompt tier label differs. **No Hypothesis property loop** yet. | **Working, AI-driven but not hybrid** — scope: wire reasoning adapter → Hypothesis |
| `--security` | dry-run exit 0; `probe_groups: ["security"]`; base worker image | **N for generation** — static `probe_engine` cross-tenant templates + canary + teardown. Model stage **not** started for security-only (`needs_model_stage` requires deep/aggressive). | **Working, static-only (probes)** — canary + teardown (P3/P4) proven in isolation package; AI security-reason adapter is net-new |
| `--web` | dry-run exit 0; `probe_groups: ["web"]`; needs `--start-command`/`--port`; `workflo-worker-web:latest` | **N** — Playwright (`tenant_shield_worker/web/`) | **Working, deterministic** — defer AI; not on 4-week critical path |
| `--dry-run` | exit 0; prints plan JSON, no Docker | **N** | **Working, deterministic** |
| Reporting (post-run narrative) | `WORKFLO_REPORT:` JSON on stdout; CLI prints counts; no plain-English narrative adapter | **N** — structured counts/findings only | **Static structured report** — reporting LoRA is net-new |

## Verdict definitions

- **Working, deterministic** — does what it claims, no AI needed, leave it alone.
- **Working, AI-driven** — confirmed a model call happens and its output is used.
  Record which model/endpoint, and whether output is validated before use.
- **Working, static-only (mislabeled as AI)** — flag exists and runs but its
  "generated edge cases" or similar are template/Hypothesis output with no model
  call. This is the most important category to catch before any public claim.
- **Stubbed** — flag is parsed by the CLI but does nothing meaningfully different
  from `--test`.
- **Not implemented** — flag doesn't exist in the CLI at all (like the earlier
  `--quick-test`/`--path` case). Confirm this the same way: try running it and
  read the actual error, don't assume from documentation or memory.

## Existing Ollama path — validation (confirmed 2026-08-15)

**Question:** does today's Ollama output reach pytest unvalidated?

**Answer: No — it is shape-validated. It is not execution-validated.**

Pipeline in `apps/worker-engine/.../executor.py` → `_run_model_stage`:

1. `ModelServer.generate(prompt)` → free-form string (`/api/generate`)
2. `generate_from_model_output(raw)` (`probe_adapter.py`):
   - YAML/JSON parse
   - coerce to list of dicts
   - **Pydantic `ProbeSpec(**item)`** — missing/wrong fields raise `ModelOutputInvalid`
3. One correction-prompt retry, then fail the model stage explicitly
4. `_write_pytest_from_specs(specs)` — **worker-synthesized** pytest, not raw model code

So there is **no live "raw LLM text → pytest file" path**. The LoRA scaffolding's
compile-check gate is still right for the *future* free-form `WriteTestCall.content`
path; retrofitting adapters does not mean inventing the first gate from scratch.

What *is* missing (the real remaining risk for Part B's load-bearing design):

- Generated tests are **pass-through** (`assert True`) — see docstring on
  `_write_pytest_from_specs`. Schema-valid proposals always "pass" under pytest.
- Model proposals are recorded in the receipt `findings`, but pytest is not yet
  ground-truth for whether a probe actually catches a bug.
- Closing *that* gap (real probe execution / Hypothesis for aggressive) is the
  integration work — **in parallel with** locking base model/template, not blocked
  on inventing a ProbeSpec gate that already exists.

Base model already in production: `qwen2.5-coder:7b-instruct-q4_K_m`
(`ModelServerConfig.DEFAULT_MODEL` / `Dockerfile.deep`). Chat template is ChatML
(`serving/CHAT_TEMPLATE.md` in the AI scaffolding package).

## Acceptance-test infrastructure (gating, not a footnote)

Two questions that gate whether "seed a cross-tenant bug, confirm the probe
fails" can ever mean anything:

### 1. Shared boot mechanism?

**Yes at the primitive layer; not yet wired for probes.**

`tenant_shield_worker.web.app_starter.start_app_under_test` /
`stop_app_under_test` is already a generic boot-a-target-app helper
(shell-free, port-wait, early-exit vs timeout split). Only `run_web_stage`
calls it today. `ProbeRunner` should reuse that same primitive — not invent
a second boot path. What's missing is wiring: set `WORKFLO_API_BASE_URL`
after boot, and allow `start_command`/`port` when `--security` / deep
model probes need a live target (today those flags are `--web`-only in the CLI).

### 2. What is the real target app?

**Not `pallets/click`. Not live WorkFlow Pro staging.**

| Candidate | Verdict |
|---|---|
| `pallets/click` | Smoke-only — no tenants/API; cannot exercise ProbeRunner |
| `api.workflowpro.com` / staging WorkFlow Pro | External host — **unreachable under `--network none`** |
| `apps/worker-engine/tests/fixtures/sample_repo` | Surface pytest fixture only — same limitation as click |
| `tests/mock_server.py` | **Intended base** — stdlib `HTTPServer`, multi-tenant via `X-Tenant-ID`, `/api/v1/projects` CRUD, no DB/external deps, already seedable (remove the 403 on cross-tenant read). Can boot with `python tests/mock_server.py` + `start_app_under_test` |

Critical-path item this week (above more codegen polish): wire
`start_app_under_test` for probe tiers + promote `mock_server` into a
fixture app with a deliberate seedable isolation bug for the acceptance test.

## Project promises that are NOT the AI feature (still in scope)

These are sandbox-contract promises. AI work must not weaken them; wiring a
new serving backend must keep them green.

| # | Promise | Status in this repo | AI implication |
|---|---|---|---|
| **P4** | Sandbox destroyed after every run, no residue | `verify_container_gone` + `verify_ephemeral_gone` fail-closed; deep tier also wipes Ollama state via `wipe_model_state` / `model_inference_teardown` on the receipt | llama-server (or any successor) state dirs must be wiped or live only inside the destroyed container; never bind-mount writable host caches into the model service |
| **P5** | Every run produces a signed, tamper-evident receipt | `ReceiptSigner.sign()` Ed25519 over `canonical_payload()`; failure path also signs (P6) | Adapter output must reach the receipt only as structured findings after real pytest/Hypothesis execution — never as an unsigned model claim |

## Critical checks (do these regardless of the table above)

- [ ] Seed a real cross-tenant bug (e.g. remove a `tenant_id` filter on one
      endpoint in a disposable test repo) and confirm `--security` fails on it.
      If it doesn't, `--security`'s isolation-probe generation is not working
      regardless of what the CLI output claims.
- [ ] Run `--deep-test` and `--aggressive-test` against a repo with a known,
      human-identifiable edge case (e.g. an off-by-one in pagination) and check
      whether the generated tests catch it, and whether the generated code is
      plausible (would a reviewer believe a person wrote it) or clearly templated.
- [ ] Confirm zero outbound network calls happen during `--security`'s egress
      canary AND during any model-generation step — the model has to run inside
      the `--network none` sandbox, not phone out to a hosted API. This is the
      single most important thing to verify before writing any public copy about it.
- [ ] After any AI serving change: confirm P4 (`model_inference_teardown` /
      container+tmpfs gone) and P5 (`workflo verify` on the signed receipt) still
      pass on a deep-tier run.
