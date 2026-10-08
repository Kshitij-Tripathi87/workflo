# Workflo — Locked Manifests

These are **frozen** contracts and invariants. They must not change during the rebuild without an explicit ADR.

---

## Frozen Constitution Recap

1. **Sandbox** = `bwrap` + `netns` + `cgroups v2` + `seccomp` + `Landlock` (NOT Docker).
2. **Model** = `qwen3-4b-4bit` via OpenAI-compatible inference gateway. No Claude/GPT fallback.
3. **Explorer** is the only model-using role. All other roles are deterministic.
4. **No hidden chain-of-thought** in UI/API events.
5. **Default-deny ToolGateway** with only `http_request` and `read_app_logs`. No DB tool. No arbitrary filesystem. No unrestricted shell.
6. **Internal Merkle transparency log** is the product boundary. Rekor/Sigstore later as interop.
7. **No fabricated execution.** Runtime and ledger are authoritative.

---

## Locked Schemas (v2026-09-30)

### `PublicAgentEventSchema`
- 8 roles: `ORCHESTRATOR | PROVISIONER | INGESTOR | EXECUTOR | EXPLORER | TOOL_GATEWAY | JUDGE | NOTARY`
- 20 kinds: `MISSION_ACCEPTED | STATE_CHANGE | REPO_INGESTED | SANDBOX_PROVISIONED | APP_STARTED | APP_HEALTHY | TEST_RESULTS | TOOL_PROPOSED | TOOL_AUTHORIZED | TOOL_DENIED | TOOL_EXECUTED | OBSERVATION | HYPOTHESIS | REPRODUCTION | CONTROL | FINDING_CONFIRMED | FINDING_UNCONFIRMED | RECEIPT_SIGNED | TEARDOWN_VERIFIED | RUN_FAILED`
- 5 statuses: `info | success | denied | error | timeout`
- strict mode: **any extra key rejected** (this kills CoT leakage by construction)
- Field length caps: `action ≤ 200`, `summary ≤ 500`, `rationale ≤ 500`, `observationSummary ≤ 2000`, `policyId ≤ 200`

### `ExplorerProposalSchema`
- tools: `http_request | read_app_logs | browser_probe`
- `http_request.path`:
  - must match `^/[a-zA-Z0-9\-._~:/?#@!$&'()*+,;=%[\]]*$`
  - must NOT start with `//` (scheme-relative rejection)
- `read_app_logs.tail ≤ 500`, `filter ≤ 200`
- `browser_probe`: `action ≤ 200`, `target ≤ 500`
- Top-level: `action`, `rationale (≤500)`, `expected_signal (≤500)` — strict mode, **no CoT fields**

### `GatewayResultSchema`
- `decision: authorized | denied` — **no third state**
- `reason ≤ 500`, `policyId ≤ 200`
- strict mode

### `JudgeDecisionSchema`
- `verdict: CONFIRMED | UNCONFIRMED | INSUFFICIENT_CONTROL | ERROR`
- `confidence?: low | medium | high`
- `evidenceRefs: eventId[]` — defaults to `[]`
- strict mode

### `ReceiptV4Schema`
- `receipt_version: 4` (literal)
- `repository.provider: "github"` (literal)
- `run_report.{lifecycle, tests, findings[]}` — all required
- `sandbox.{isolation_attestation, teardown_proof, canary_check}` — all required (objects)
- `inference_provenance.{model_id, request_ids[], input_tokens ≥ 0, output_tokens ≥ 0, inference_seconds ≥ 0, source_code_included}`
- `transparency.{log_id, checkpoint ≥ 0, merkle_root, inclusion_proof[]}`
- strict mode throughout

### `RunStateSchema`
`CREATED → INGESTING → PROVISIONING → EXECUTING → EXPLORING → JUDGING → NOTARIZING → COMPLETED | FAILED`

---

## Hard Rules (Tested)

1. Explorer emits proposals only; cannot execute.
2. ToolGateway is default-deny; `decision: "denied"` is final.
3. Judge is deterministic; no model invocation.
4. Notary cannot fabricate: every receipt references existing ledger events.
5. Frontend cannot create or "verify" receipts — only display backend results.
6. Evidence is append-only (no UPDATE/DELETE on `evidence_events`).
7. Tampered receipt ⇒ signature/hashchain mismatch ⇒ verification fails.
8. Denied proposals NEVER become `TOOL_EXECUTED`.
9. No CoT fields (`thought`, `reasoning`, `internal`, `chain`) — strict schemas reject them.
10. Paths are relative-only: no `http://`, no `//`, no drive letters.

---

## Known Limitations (Accepted for MVP)

- `browser_probe` is in the schema but cut from MVP default budget.
- Policy editing UI is out of scope for MVP.
- External transparency (Rekor/Sigstore) deferred.
- Multi-region deployment deferred.
- HSM/KMS signing deferred (file-based key provider for dev).

---

## Baseline Test Report

- ✅ `pnpm lint` — clean
- ✅ `pnpm typecheck` — clean (strict mode)
- ✅ `pnpm test` — 40/40 passing in `@workflo/contracts`

**Test matrix:**
| File | Tests | Coverage |
|------|-------|----------|
| `explorer.test.ts` | 12 | relative paths, scheme-relative rejection, CoT rejection, tail limits, unknown tools, missing fields, length caps |
| `agent-events.test.ts` | 13 | valid event, denied, optional fields, CoT ×3, length caps, role/kind validation, UUID, causal parent |
| `tool-gateway.test.ts` | 6 | authorized, denied, structural representability, invalid decision, length caps, strict |
| `receipt.test.ts` | 9 | valid, wrong version, wrong provider, invalid URL, negative tokens/checkpoint, tamper, missing keys |

---

**Locked on:** 2026-09-30 (Day 1+2 gate passed)
