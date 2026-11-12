# ADR-0018 — Receipt v5: validated payload, isolated signer, DSSE envelope

**Status:** Proposed · 2026-11-11

## Context

Today the executor or CLI builds and signs a bespoke Ed25519 receipt (`SignedReceipt` v1–v4) immediately, with an ephemeral in-process key; the control plane appends the fingerprint to a Merkle transparency log and can serve inclusion proofs. The brief requires: guest never holds signing keys; a trusted evidence service validates run identity, source, policy, artifacts, event chain, result semantics, and teardown **before** a separate signer signs; the receipt binds ledger root + checkpoint; DSSE/in-toto-style attestation is the evaluation target; signature validity and factual validity are separate claims.

## Decision

1. **Receipt v5 (new runs)** is a structured payload + DSSE-style envelope:

   - Payload (`receipt_version: 5`, schema version "1") binds: run/attempt/organization/project/sandbox identity; source provider/ref/commit/snapshot digest; execution policy digest; runtime identity (runtime image digest, guest kernel/rootfs digests when available); model artifact digests; execution start/end (canonical ms timestamps); the **three-outcome** record; finding summary digest; evidence manifest digest; evidence ledger root + checkpoint + chain version; the **teardown verification record** (outcome + per-check results + verifier identity); a non-empty `limitations` list; signer identity.
   - Envelope: `payloadType: application/vnd.workflo.receipt.v5+json`, base64-encoded canonical payload bytes, `signatures: [{keyid, sig}]` (Ed25519 for the first release; algorithm agility reserved).
   - The payload is hashed and encoded using the canonical profile of ADR-0016.

2. **Validation-before-signing is structural.** The receipt payload cannot be constructed without the teardown verification record, the evidence manifest digest, the finding summary digest, and the outcome — so "sign now, validate later" is not representable. The signing service additionally refuses payloads whose evidence ledger head does not match the claimed root/checkpoint (enforced in the evidence service; tested with tamper cases).

3. **Signer isolation.** Signing keys live outside the guest and outside the ordinary worker in the target architecture (KMS/HSM-backed; ADR-010). In-process ephemeral signing is explicitly a **dev mode**: it must be marked in the receipt (`signer_identity.provider`), and production configuration must refuse it (fail-closed startup guard).

4. **One fingerprint definition.** `public_key_fingerprint = sha256(raw subjectPublicKey bytes)`. The control-plane key directory's PEM-text fingerprint is reconciled to this definition; the receipt v5 contract validates the pattern.

5. **Limitations are part of the contract.** Every receipt carries an explicit, non-empty limitations list (the receipt attests scope, not absolute correctness). Default list frozen in code.

6. **Legacy receipts v1–v4 keep verifying** with their original code paths; no re-signing, no silent migration. New capability work targets v5 only. The transparency log continues to anchor signed receipts (inclusion proof = external checkpoint interface).

## Consequences

- `workflo_schema.contracts.receipt` defines the structures now; the evidence service + signer service that enforce and produce them are Phase 6 work (Gate G10).
- Acceptance tests must include: tampered payload rejected; tampered ledger rejected; missing teardown record rejected; dev-mode signer refused in production; cross-run evidence reference rejected.

## Alternatives considered

- Reusing ReceiptV4Schema (TS): lacks attempt identity, policy/runtime/model digests, teardown record, and the validation gate.
- Signing with an in-sandbox key: violates invariant 7 (no signing key inside the sandbox) — rejected outright.
