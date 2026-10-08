# Workflo — Security Invariants

These are **hard rules** encoded as tests. They must never regress.

| Gate | Invariant | Enforcement |
|------|-----------|-------------|
| 1 | Explorer cannot execute | Explorer produces `ExplorerProposalSchema` only; no direct tool execution |
| 2 | ToolGateway can only authorize | `GatewayResultSchema` has no execution side-effects; decision is final |
| 3 | Judge cannot use the model | Judge is deterministic; no inference client imported |
| 4 | Notary cannot invent execution | Receipts reference existing `eventId`s from the ledger only |
| 5 | Frontend cannot create receipts | Receipts produced only by trusted backend (`packages/notary`) |
| 6 | Frontend cannot declare verification | Verification result comes only from `packages/verifier` |
| 7 | Evidence is append-only | `evidence_events` table has no UPDATE/DELETE triggers/roles |
| 8 | Tampered receipt fails | Any mutation invalidates `Ed25519` signature or hash chain |
| 9 | Denied actions remain denied | Denied `GatewayResult` cannot transition to `TOOL_EXECUTED` event |
| 10 | No hidden CoT in public API/UI | `PublicAgentEventSchema` rejects `thought`, `reasoning`, `internal`, etc. |

## Contract-Level Enforcement

- `ExplorerProposalSchema` strips unknown fields (strict mode).
- `PublicAgentEventSchema` uses `.strict()` and rejects extra keys.
- `HttpRequestArgsSchema.path` regex enforces relative paths only (`^/...`).
- `ReadAppLogsArgsSchema.tail` capped at `500`.
- `GatewayDecisionSchema` is enum: `authorized | denied` only.

## Runtime-Level Enforcement (to be implemented in later batches)

- ToolGateway default-deny policy engine
- Sandbox `bwrap` + `netns` + `cgroups` + `seccomp` + `Landlock`
- Observation Gateway redacts secrets and rejects source-bearing payloads
- Transparency log append-only JSONL + Merkle checkpoints

## Test Files

- `packages/contracts/tests/explorer.test.ts`
- `packages/contracts/tests/agent-events.test.ts`
- `packages/contracts/tests/tool-gateway.test.ts`
- `packages/contracts/tests/receipt.test.ts`
- `tests/security/explorer-cannot-execute.test.ts` (Day 14)
- `tests/security/receipt-tamper.test.ts` (Day 14)
- `tests/security/tool-gateway-deny.test.ts` (Day 14)
