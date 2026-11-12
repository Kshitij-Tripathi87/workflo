# ADR-0016 — Canonical JSON profile and evidence-chain format

**Status:** Proposed · 2026-11-11
**Context:** two incompatible evidence hashes exist today —
Python `sandbox_runtime/evidence.py`: `sha256(f"{event_id}{timestamp}{event_type}{json.dumps(data, sort_keys=True)}{prev_hash}")`, genesis `"0"*64`;
TypeScript `packages/events/hash-chain.ts`: `sha256(canonicalJson(boundRecord))`, genesis `sha256("workflo:evidence:genesis:v1")`.

## Decision

**One canonical serialization profile is frozen for every hashed structure** (events, evidence manifests, receipts payloads, policy digests, approval bindings):

1. **Serialization = RFC 8785 (JCS) subset**, exactly as implemented in `packages/events/src/hash-chain.ts`:
   - object keys sorted by code unit; no insignificant whitespace;
   - strings serialized as JSON strings in UTF-8 (no `\uXXXX` escaping of printable non-ASCII);
   - `null` preserved; keys with `undefined` (absent) values do not exist in the canonical form;
   - arrays preserve order.
2. **Numbers in hashed structures are integers or strings only.** Floating point is forbidden in any structure that participates in a digest. Durations use integer milliseconds (or integer seconds where the field name says seconds); sizes use integer bytes. This eliminates cross-language float-formatting divergence.
3. **Timestamps in hashed structures are strings**: ISO-8601 UTC with millisecond precision, `YYYY-MM-DDTHH:MM:SS.mmmZ`. No timezone offsets, no sub-millisecond precision, no locale forms.
4. **Digests are self-describing**: `sha256:<64 lowercase hex>`. (Legacy bare-hex fingerprints from receipts v1–v4 remain valid in their legacy context only.)
5. **Evidence chain format `workflo.evidence.chain.v2`** (new runs):
   - genesis: `H(0) = sha256("workflo:evidence:genesis:v1")` (the constant already used by the TS ledger);
   - link: `H(n) = sha256(canonical_json(bound_record(n)))` where `bound_record` carries the event's identity, tenancy, attempt, sequence, type, producer, occurred_at, payload digest, and `prev_hash`;
   - the chain is bound into the receipt as `evidence_ledger_root` **plus** an external head anchor/checkpoint (`evidence_ledger_checkpoint`) — pure chain math cannot detect a self-consistent forged tail.
6. **Legacy chains are preserved for verification**: receipts v1–v4 keep their original Python ledger format and verification code path forever. New runs do not emit the legacy format.

## Consequences

- `workflo_schema.contracts.canonical` provides the Python implementation (with tests against the frozen rules). Cross-language fixture tests (Python ↔ TS) are a Phase 1 follow-up task and a CI requirement before any cross-language digest is trusted.
- Existing Python evidence files remain verifiable; the v2 chain applies forward.
- Reviewers can require "no float in hashed structure" mechanically: the canonical serializer raises on `float`.

## Alternatives considered

- Continue two formats: rejected — the brief requires one event/evidence contract and cross-verification.
- Pure RFC 8785 including its number algorithms: rejected as unnecessary once floats are banned from hashed structures.
