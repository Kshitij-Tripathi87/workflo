# ADR-0001 — Adopt the brief's architecture decisions as the baseline

**Status:** Accepted · 2026-11-11
**Source:** WORKFLO A–Z Product Engineering Brief v1.0, §"Architecture decisions to freeze"

## Decision

The fourteen decisions below are adopted unchanged and are referenced by their brief IDs throughout this repository. New repository ADRs continue from ADR-0015.

| ID | Decision | Status in brief | Effect here |
|---|---|---|---|
| ADR-001 | Dedicated microVM per run attempt | Mandatory | Drives ADR-0022; blocks G3 until proven on real KVM |
| ADR-002 | No customer project execution on the host | Mandatory | Host APIs stay typed (`ProvisionSandbox`, `VerifyResourcesRemoved`, …); no `execute_command` |
| ADR-003 | Project-aware agents and inference run inside guest by default | Mandatory default | `workflo-ai-integration` model runtime belongs in the guest image; no cloud fallback for source-bearing inference |
| ADR-004 | Default-deny network access | Mandatory | Per-run egress allowlist; gateway failure fails closed; blocks G4 |
| ADR-005 | Immutable, versioned execution policy | Mandatory | Drives ADR-0019; `policy_digest` is part of the run contract and receipt |
| ADR-006 | Durable run orchestration | Required | Phase 2: transactional outbox + durable workflow; in-process path demoted to dev mode |
| ADR-007 | PostgreSQL is authoritative for product state | Required | All lifecycle/evidence/receipt records persist in PostgreSQL; object storage holds artifacts only |
| ADR-008 | Redis is not the source of truth | Required | Redis remains cache/fan-out only |
| ADR-009 | Independent evidence validation and receipt signing | Mandatory | Drives ADR-0018/0020; guest never signs; validation precedes signing |
| ADR-010 | KMS/HSM-backed signing keys outside the guest | Mandatory | Signer identity in receipt v5; file-based keys are labeled dev-only |
| ADR-011 | Teardown verification is a separate result | Mandatory | `TrustVerificationStatus` is independent of execution status |
| ADR-012 | Remediation and patch verification use a new sandbox | Mandatory | Drives ADR-0021 |
| ADR-013 | Customer-controlled execution is the initial deployment preference | Recommended | Deployment docs must state data flow per mode |
| ADR-014 | Next.js + FastAPI + PostgreSQL remain the primary application stack | Recommended | Anchors the canonical-tree decision (ADR-0015) |

## Consequences

- Any test or document that contradicts one of these decisions is a defect, not an alternative.
- Changes to these decisions require a superseding ADR pair (one for the brief ID, one for local implementation) and an explicit owner sign-off.
