import { createHash } from "node:crypto";
import type { EvidenceEventRow } from "@workflo/db";

/**
 * Evidence hash chain.
 *
 *   H(0) = GENESIS_HASH  (sha256 of "workflo:evidence:genesis:v1")
 *   H(n) = SHA256( canonicalJson( boundRecord(n, H(n-1)) ) )
 *
 * The bound record includes event identity, tenancy, sequence, type, role,
 * status, timestamps, the full contract payload AND the previous hash —
 * mutating any field anywhere breaks every link after it.
 */

export const CHAIN_VERSION = 1;

export const GENESIS_HASH =
  "70cf1f39fae1b99f421d5265cda76dd56907e8d4966b27ad9035d1301a822b74";

/**
 * Deterministic JSON serialization (RFC 8785 subset):
 *  - object keys sorted by code unit
 *  - no insignificant whitespace
 *  - finite numbers only
 *  - Dates normalized to ISO-8601 UTC with millisecond precision
 *  - undefined / functions / symbols / bigint are rejected
 */
export function canonicalJson(value: unknown): string {
  if (value === null) return "null";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      throw new Error("non-finite number cannot be canonicalized");
    }
    return JSON.stringify(value);
  }
  if (typeof value === "string") return JSON.stringify(value);
  if (value instanceof Date) return JSON.stringify(value.toISOString());
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalJson(item)).join(",")}]`;
  }
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    const keys = Object.keys(record)
      .filter((k) => record[k] !== undefined)
      .sort();
    const body = keys
      .map((k) => `${JSON.stringify(k)}:${canonicalJson(record[k])}`)
      .join(",");
    return `{${body}}`;
  }
  throw new Error(`value of type ${typeof value} cannot be canonicalized`);
}

/** The full set of fields bound into the hash. */
export interface ChainBoundRecord {
  v: number;
  event_id: string;
  organization_id: string;
  project_id: string;
  run_id: string;
  run_seq: number;
  event_type: string;
  role: string;
  status: string;
  parent_event_id: string | null;
  request_id: string | null;
  action: string | null;
  summary: string;
  rationale: string | null;
  observation_summary: string | null;
  policy_id: string | null;
  payload: unknown;
  occurred_at: string;
  prev_hash: string;
}

export interface ChainInput {
  eventId: string;
  organizationId: string;
  projectId: string;
  runId: string;
  runSeq: number;
  kind: string;
  role: string;
  status: string;
  parentEventId: string | null;
  requestId: string | null;
  action: string | null;
  summary: string;
  rationale: string | null;
  observationSummary: string | null;
  policyId: string | null;
  payload: unknown;
  occurredAt: Date;
  prevHash: string;
}

export function buildBoundRecord(input: ChainInput): ChainBoundRecord {
  return {
    v: CHAIN_VERSION,
    event_id: input.eventId,
    organization_id: input.organizationId,
    project_id: input.projectId,
    run_id: input.runId,
    run_seq: input.runSeq,
    event_type: input.kind,
    role: input.role,
    status: input.status,
    parent_event_id: input.parentEventId,
    request_id: input.requestId,
    action: input.action,
    summary: input.summary,
    rationale: input.rationale,
    observation_summary: input.observationSummary,
    policy_id: input.policyId,
    payload: input.payload ?? {},
    occurred_at: input.occurredAt.toISOString(),
    prev_hash: input.prevHash,
  };
}

export function hashBoundRecord(record: ChainBoundRecord): string {
  return createHash("sha256").update(canonicalJson(record), "utf8").digest("hex");
}

export function computeEventHash(input: ChainInput): string {
  return hashBoundRecord(buildBoundRecord(input));
}

/** Rebuild the bound record from a stored ledger row (for verification). */
export function chainInputFromRow(row: EvidenceEventRow): ChainInput {
  return {
    eventId: row.id,
    organizationId: row.organization_id,
    projectId: row.project_id,
    runId: row.run_id,
    runSeq: Number(row.run_seq),
    kind: row.event_type,
    role: row.role,
    status: row.status,
    parentEventId: row.parent_event_id,
    requestId: row.request_id,
    action: row.action,
    summary: row.summary,
    rationale: row.rationale,
    observationSummary: row.observation_summary,
    policyId: row.policy_id,
    payload: row.payload,
    occurredAt:
      row.occurred_at instanceof Date
        ? row.occurred_at
        : new Date(row.occurred_at),
    prevHash: row.prev_hash ?? "",
  };
}
