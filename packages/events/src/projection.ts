import type { Db, TenantContext } from "@workflo/db";
import type { LedgerEvent } from "./ledger";
import { processOnce } from "./consumer";

/**
 * Run projections are DERIVED state.
 *
 *   Ledger (truth) → reduce → run_projections (rebuildable)
 *
 * The projector never writes back to the ledger. If the projection table is
 * corrupted or dropped, rebuildRunProjection() replays the ledger.
 */

export interface RunProjectionState {
  lifecycle: string;
  counts: Record<string, number>;
  denied: number;
  findingsConfirmed: number;
  findingsUnconfirmed: number;
  lastRunSeq: number;
}

function initialState(): RunProjectionState {
  return {
    lifecycle: "CREATED",
    counts: {},
    denied: 0,
    findingsConfirmed: 0,
    findingsUnconfirmed: 0,
    lastRunSeq: 0,
  };
}

/** Pure reducer over ordered events. */
export function reduceEvents(events: LedgerEvent[]): RunProjectionState {
  const state = initialState();
  for (const ev of events) {
    state.counts[ev.event_type] = (state.counts[ev.event_type] ?? 0) + 1;
    if (ev.status === "denied") state.denied += 1;
    if (ev.event_type === "STATE_CHANGE") {
      const to = (ev.payload as Record<string, unknown>).to;
      if (typeof to === "string") state.lifecycle = to;
    }
    if (ev.event_type === "FINDING_CONFIRMED") state.findingsConfirmed += 1;
    if (ev.event_type === "FINDING_UNCONFIRMED") state.findingsUnconfirmed += 1;
    if (ev.event_type === "RUN_FAILED") state.lifecycle = "FAILED";
    if (ev.event_type === "RECEIPT_SIGNED") state.lifecycle = "COMPLETED";
    state.lastRunSeq = Math.max(state.lastRunSeq, Number(ev.run_seq));
  }
  return state;
}

const PROJECTOR_CONSUMER = "run-projector";

/**
 * Rebuild (or advance) the projection for a run by replaying the ledger.
 * Idempotent: consumer offsets skip already-processed events, and the upsert
 * stores the full deterministic reduction.
 */
export async function rebuildRunProjection(
  db: Db,
  ctx: TenantContext & { projectId: string },
  runId: string,
  ledger: { getRunEvents(ctx: TenantContext, runId: string): Promise<LedgerEvent[]> },
): Promise<RunProjectionState> {
  const events = await ledger.getRunEvents(ctx, runId);
  const state = reduceEvents(events);

  const lastEvent = events[events.length - 1];
  await processOnce(db, ctx, PROJECTOR_CONSUMER, lastEvent?.id ?? runId, async (s) => {
    await s.query(
      `INSERT INTO run_projections (run_id, organization_id, project_id, state, last_run_seq, updated_at)
       VALUES ($1, $2, $3, $4::jsonb, $5, now())
       ON CONFLICT (run_id)
       DO UPDATE SET state = EXCLUDED.state, last_run_seq = EXCLUDED.last_run_seq, updated_at = now()`,
      [runId, ctx.orgId, ctx.projectId, JSON.stringify(state), state.lastRunSeq],
    );
  });

  return state;
}

export async function readRunProjection(
  db: Db,
  ctx: TenantContext,
  runId: string,
): Promise<RunProjectionState | null> {
  return db.withTenant(ctx, async (s) => {
    const { rows } = await s.query<{ state: RunProjectionState }>(
      `SELECT state FROM run_projections WHERE run_id = $1`,
      [runId],
    );
    return rows[0]?.state ?? null;
  });
}
