import {
  PublicAgentEventSchema,
  type AgentEventKind,
  type AgentRole,
  type AgentEventStatus,
} from "@workflo/contracts";
import type { TenantSession } from "../client";

/**
 * Class C — append-only evidence ledger.
 *
 * Columns mirror PublicAgentEventSchema exactly. Writes go through the
 * append_evidence_event() SECURITY DEFINER function, which locks the run,
 * validates chain linkage (prev_hash + run_seq) and inserts atomically.
 * The application role cannot INSERT raw rows.
 *
 * Hash computation lives in @workflo/events (hash-chain.ts); this module is
 * the thin, validated write path.
 */

/** Fields that would smuggle hidden chain-of-thought. Rejected outright. */
export const FORBIDDEN_EVENT_FIELDS = [
  "thought",
  "thoughts",
  "reasoning",
  "internal",
  "chain",
  "chain_of_thought",
  "chainOfThought",
  "scratchpad",
  "cot",
] as const;

function assertNoHiddenFields(input: object): void {
  for (const key of FORBIDDEN_EVENT_FIELDS) {
    if (key in input) {
      throw new Error(
        `forbidden field "${key}" in evidence event (no hidden chain-of-thought)`,
      );
    }
  }
}

export interface EvidenceEventRow {
  id: string;
  seq: string;
  run_seq: string | null;
  organization_id: string;
  project_id: string;
  run_id: string;
  event_type: AgentEventKind;
  role: AgentRole;
  status: AgentEventStatus;
  parent_event_id: string | null;
  request_id: string | null;
  action: string | null;
  summary: string;
  rationale: string | null;
  observation_summary: string | null;
  policy_id: string | null;
  payload: Record<string, unknown>;
  prev_hash: string | null;
  hash: string | null;
  occurred_at: Date;
  created_at: Date;
}

export interface AppendEventInput {
  eventId: string;
  runId: string;
  runSeq: number;
  prevHash: string;
  hash: string;
  kind: AgentEventKind;
  role: AgentRole;
  status: AgentEventStatus;
  summary: string;
  occurredAt: Date;
  parentEventId?: string | null;
  requestId?: string | undefined;
  action?: string | undefined;
  rationale?: string | undefined;
  observationSummary?: string | undefined;
  policyId?: string | undefined;
  payload?: Record<string, unknown> | undefined;
}

/**
 * Append one chain-validated event. Contract fields are validated via zod;
 * chain linkage is enforced by the database function.
 */
export async function appendEvent(
  s: TenantSession,
  input: AppendEventInput,
): Promise<EvidenceEventRow> {
  assertNoHiddenFields(input);
  if (input.payload) assertNoHiddenFields(input.payload);

  PublicAgentEventSchema.parse({
    eventId: input.eventId,
    runId: input.runId,
    parentEventId: input.parentEventId ?? null,
    role: input.role,
    kind: input.kind,
    status: input.status,
    action: input.action,
    summary: input.summary,
    rationale: input.rationale,
    observationSummary: input.observationSummary,
    policyId: input.policyId,
    requestId: input.requestId,
    occurredAt: input.occurredAt,
  });

  const { rows } = await s.query<EvidenceEventRow>(
    `SELECT * FROM append_evidence_event($1::jsonb)`,
    [
      JSON.stringify({
        id: input.eventId,
        run_id: input.runId,
        run_seq: input.runSeq,
        prev_hash: input.prevHash,
        hash: input.hash,
        event_type: input.kind,
        role: input.role,
        status: input.status,
        parent_event_id: input.parentEventId ?? null,
        request_id: input.requestId ?? null,
        action: input.action ?? null,
        summary: input.summary,
        rationale: input.rationale ?? null,
        observation_summary: input.observationSummary ?? null,
        policy_id: input.policyId ?? null,
        payload: input.payload ?? {},
        occurred_at: input.occurredAt.toISOString(),
      }),
    ],
  );
  return rows[0]!;
}

export async function listRunEvents(
  s: TenantSession,
  runId: string,
): Promise<EvidenceEventRow[]> {
  const { rows } = await s.query<EvidenceEventRow>(
    `SELECT * FROM evidence_events WHERE run_id = $1 ORDER BY seq`,
    [runId],
  );
  return rows;
}

/** Latest chained event in a run (used by the ledger to extend the chain). */
export async function latestChainedEvent(
  s: TenantSession,
  runId: string,
): Promise<EvidenceEventRow | null> {
  const { rows } = await s.query<EvidenceEventRow>(
    `SELECT * FROM evidence_events
     WHERE run_id = $1 AND hash IS NOT NULL AND run_seq IS NOT NULL
     ORDER BY run_seq DESC LIMIT 1`,
    [runId],
  );
  return rows[0] ?? null;
}
