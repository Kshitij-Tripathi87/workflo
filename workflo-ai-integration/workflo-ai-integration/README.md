# workflo AI integration — scaffolding

Standalone scaffolding for the LoRA-adapter path. Fully tested against mocks.
Meant to be merged into the real sandbox worker once adapters exist.

```
audit/
  FLAG_AUDIT_CHECKLIST.md   # filled from real CLI + source (2026-08-15)
  audit_flags.py            # automated first-pass: probes flags + greps source
serving/
  docker-compose.llamacpp.yml   # DEFAULT: llama-server, CPU, three LoRAs at start
  .optional-gpu-path/           # vLLM multi-LoRA — documented upgrade only
src/
  schemas.py                # structured output contracts (WriteTestCall, etc.)
  safety_gate.py            # compile-check gate — nothing generated reaches
                             # pytest without passing through here
  model_router.py           # flag -> adapter -> validated-output routing
tests/
  test_model_router.py      # llama-server mocks (discovery, lora field, schema)
  test_safety_gate.py       # compile / import / expression checks
```

Run tests: `pip install -r requirements.txt && python -m pytest tests/ -v`

## Serving backend

**Default: llama.cpp `llama-server`** — CPU-only, MIT, $0 GPU cost.
All three adapters load at container startup (`--lora` + `--lora-init-without-apply`,
scale 0.0). Each request activates exactly one via the `lora` field. No shared
mutable load/unload state.

**Optional: vLLM** under `serving/.optional-gpu-path/` if volume ever justifies
GPU rental. `generate_for_flag` / `generate_report` stay the same either way.

Adapter discovery is defensive: `GET /lora-adapters`, match by filename
substring — not hardcoded ids. Structured output uses sampler `json_schema`
plus Pydantic + compile-check. Pydantic stays load-bearing (llama.cpp can
silently fall back on bad schemas — ggml-org/llama.cpp#19051).

Open decisions before training locks:
1. ~~Chat template~~ — **closed**: pull from live Ollama Modelfile for
   `qwen2.5-coder:7b-instruct-q4_K_m` (ChatML). See `serving/CHAT_TEMPLATE.md`.
   Prefer staying on this base for MMVP rather than jumping to Qwen3 cold.
2. PEFT→GGUF — stub script at `scripts/convert_peft_to_gguf.sh` (`--dry-run`
   prints the plan; conversion tool still to pin).

### Existing Ollama path is already gated (shape, not execution)

`--deep-test` / `--aggressive-test` already call Ollama. Output does **not**
flow straight into pytest: `generate_from_model_output` → Pydantic `ProbeSpec`
→ worker-written `test_workflo_generated.py`. The remaining gap is that those
generated tests are pass-through (`assert True`), not real execution ground
truth — close that in parallel with adapter training; do not block on adding a
ProbeSpec gate that already exists. Full write-up:
`audit/FLAG_AUDIT_CHECKLIST.md` § "Existing Ollama path".

## P4 / P5 — not the AI feature, still in scope

AI wiring must not weaken the sandbox contract:

| # | Promise | Implication for this package |
|---|---|---|
| **P4** | Sandbox destroyed, no residue | `:ro` mounts of `./models` / `./adapters` are static assets (OK). **Deliberate omission:** no `--slot-save-path` in `docker-compose.llamacpp.yml` — that flag would persist prompt-cache (repo content) outside teardown. Same verifiable class of guarantee as "no external inference API". Runtime Ollama wipe → `model_inference_teardown` stays required for the live path. |
| **P5** | Signed, tamper-evident receipt every run | Model output reaches the receipt only as structured findings **after** real pytest/Hypothesis execution — never as an unsigned model claim |

See `docs/workflo/sandbox_contract.md` and `audit/FLAG_AUDIT_CHECKLIST.md`.

## Two tracks

### Track 1 — audit (done for Part A unknowns)

`FLAG_AUDIT_CHECKLIST.md` is filled. Headline:

- `--test` — deterministic, no AI
- `--deep-test` / `--aggressive-test` — **exist**, embedded Ollama today; LoRA retrofit
- `--security` — canary + teardown + static probes; AI probe generation is net-new
- `--web` — exists, defer AI
- Reporting — structured JSON only; narrative adapter is net-new

Re-run anytime:

```
python audit/audit_flags.py --workflo-bin workflo \
  --repo https://github.com/pallets/click.git \
  --src-path /path/to/workflo/source \
  --out audit_report
```

### Track 2 — model router (ready to wire)

- `--deep-test` → `test-gen` → validated `WriteTestCall`
- `--security` / `--aggressive-test` → `reasoning` → validated `ProposeInvariantCall`
- Post-run reporting → `reporting` → `ReportNarrative` (structured JSON in only)

Every path through `generate_for_flag()` ends in a validated object or
`GenerationValidationError`. Bad generations are discarded, never reported.

## What's NOT in here yet

1. **No trained adapters.** Paths under `/adapters/*.gguf` are placeholders.
2. **Not wired into the real worker.** Today's deep tier still uses
   `tenant_shield_worker.model.ModelServer` (Ollama). Swap that call site to
   `ModelRouter` once GGUF adapters exist — keep P4 wipe + P5 signing unchanged.
3. **No live llama-server e2e in CI.** Mocks prove plumbing; held-out eval
   proves model quality.
