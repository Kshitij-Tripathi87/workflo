import { randomUUID } from "node:crypto";
import {
  PublicAgentEventSchema,
  type AgentEventKind,
  type AgentRole,
  type AgentEventStatus,
  type PublicAgentEvent,
} from "@workflo/contracts";
import type { Db, TenantContext, EvidenceEventRow } from "@workflo/db";
import { evidence } from "@workflo/db";
import {
  GENESIS_HASH,
  computeEventHash,
  chainInputFromRow,
  hashBoundRecord,
  buildBoundRecord,
} from "./hash-chain";
import type { EventBus } from "./bus";

/**
 * The evidence ledger is the AUTHORITATIVE record of a run's history.
 *
 *   operation → validate contract → hash (binds metadata + prev) → SQL fn
 *   (lock run, verify chain head, allocate seq, insert) → commit → publish
 *
 * The bus runs AFTER commit. If publish fails the event remains durable and
 * consumers recover with replayRun().
 */

export interface LedgerAppendInput {
  runId: string;
  kind: AgentEventKind;
  role: AgentRole;
  status: AgentEventStatus;
  summary: string;
  occurredAt?: Date;
  parentEventId?: string | null;
  requestId?: string;
  action?: string;
  rationale?: string;
  observationSummary?: string;
  policyId?: string;
  payload?: Record<string, unknown>;
}

export type LedgerEvent = EvidenceEventRow & {
  run_seq: string;
  prev_hash: string;
  hash: string;
};

export interface ChainVerification {
  valid: boolean;
  runId: string;
  eventCount: number;
  firstInvalidEventId?: string | undefined;
  expectedHash?: string | undefined;
  actualHash?: string | undefined;
  reason?: string | undefined;
}

const MAX_APPEND_ATTEMPTS = 5;

function isChainConflict(error: unknown): boolean {
  return (
    error instanceof Error &&
    error.message.includes("evidence chain conflict")
  );
}

export function toPublicEvent(row: EvidenceEventRow): PublicAgentEvent {
  return PublicAgentEventSchema.parse({
    eventId: row.id,
    runId: row.run_id,
    parentEventId: row.parent_event_id,
    role: row.role,
    kind: row.event_type,
    status: row.status,
    action: row.action ?? undefined,
    summary: row.summary,
    rationale: row.rationale ?? undefined,
    observationSummary: row.observation_summary ?? undefined,
    policyId: row.policy_id ?? undefined,
    requestId: row.request_id ?? undefined,
    occurredAt: row.occurred_at,
  });
}

export class EvidenceLedger {
  constructor(
    private readonly db: Db,
    private readonly bus?: EventBus,
  ) {}

  /**
   * Atomically: read chain head → compute hash → insert via
   * append_evidence_event() (which re-validates under the run row lock).
   * Stale-head races surface as 'evidence chain conflict' and are retried
   * with a fresh read.
   */
  async appendEvent(
    ctx: TenantContext,
    input: LedgerAppendInput,
  ): Promise<LedgerEvent> {
    let lastError: unknown;
    for (let attempt = 0; attempt < MAX_APPEND_ATTEMPTS; attempt++) {
      try {
        const row = await this.db.withTenant(ctx, async (s) => {
          // Serialize appends for this run BEFORE reading the chain head.
          // Advisory lock: no UPDATE privilege needed, auto-released at
          // COMMIT; the SQL function takes the same lock for direct callers.
          await s.query(
            `SELECT pg_advisory_xact_lock(hashtextextended($1::text, 0))`,
            [input.runId],
          );

          const { rows: runRows } = await s.query<{ project_id: string }>(
            `SELECT project_id FROM runs WHERE id = $1`,
            [input.runId],
          );
          if (!runRows[0]) throw new Error("run not found");

          const latest = await evidence.latestChainedEvent(s, input.runId);
          const runSeq = latest ? Number(latest.run_seq) + 1 : 1;
          const prevHash = latest?.hash ?? GENESIS_HASH;
          const eventId = randomUUID();
          const occurredAt = input.occurredAt ?? new Date();

          // Contract validation BEFORE writing (strict: no CoT keys survive).
          PublicAgentEventSchema.parse({
            eventId,
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
            occurredAt,
          });

          const hash = computeEventHash({
            eventId,
            organizationId: ctx.orgId,
            projectId: runRows[0].project_id,
            runId: input.runId,
            runSeq,
            kind: input.kind,
            role: input.role,
            status: input.status,
            parentEventId: input.parentEventId ?? null,
            requestId: input.requestId ?? null,
            action: input.action ?? null,
            summary: input.summary,
            rationale: input.rationale ?? null,
            observationSummary: input.observationSummary ?? null,
            policyId: input.policyId ?? null,
            payload: input.payload ?? {},
            occurredAt,
            prevHash,
          });

          return evidence.appendEvent(s, {
            eventId,
            runId: input.runId,
            runSeq,
            prevHash,
            hash,
            kind: input.kind,
            role: input.role,
            status: input.status,
            summary: input.summary,
            occurredAt,
            parentEventId: input.parentEventId ?? null,
            requestId: input.requestId,
            action: input.action,
            rationale: input.rationale,
            observationSummary: input.observationSummary,
            policyId: input.policyId,
            payload: input.payload,
          });
        });

        // Publish AFTER commit. Delivery failures never unwrite the ledger.
        if (this.bus) {
          try {
            await this.bus.publish(toPublicEvent(row));
          } catch {
            // recorded durably; a replay consumer will pick it up
          }
        }
        return row as LedgerEvent;
      } catch (error) {
        lastError = error;
        if (!isChainConflict(error)) throw error;
      }
    }
    throw lastError instanceof Error ? lastError : new Error(String(lastError));
  }

  async getEvent(
    ctx: TenantContext,
    eventId: string,
  ): Promise<LedgerEvent | null> {
    return this.db.withTenant(ctx, async (s) => {
      const { rows } = await s.query<LedgerEvent>(
        `SELECT * FROM evidence_events WHERE id = $1`,
        [eventId],
      );
      return rows[0] ?? null;
    });
  }

  async getRunEvents(ctx: TenantContext, runId: string): Promise<LedgerEvent[]> {
    return this.db.withTenant(ctx, async (s) => {
      const { rows } = await s.query<LedgerEvent>(
        `SELECT * FROM evidence_events
         WHERE run_id = $1 AND hash IS NOT NULL AND run_seq IS NOT NULL
         ORDER BY run_seq`,
        [runId],
      );
      return rows;
    });
  }

  async getLatest(ctx: TenantContext, runId: string): Promise<LedgerEvent | null> {
    return this.db.withTenant(ctx, async (s) => {
      const row = await evidence.latestChainedEvent(s, runId);
      return (row as LedgerEvent | null) ?? null;
    });
  }

  /**
   * Recompute every hash from the stored rows and verify linkage/order.
   * Optional expectedHeadHash anchors the chain tip (receipt ledger_root).
   */
  async verifyRunChain(
    ctx: TenantContext,
    runId: string,
    opts?: { expectedHeadHash?: string },
  ): Promise<ChainVerification> {
    return this.db.withTenant(ctx, async (s) => {
      const { rows: events } = await s.query<LedgerEvent>(
        `SELECT * FROM evidence_events
         WHERE run_id = $1 AND hash IS NOT NULL AND run_seq IS NOT NULL
         ORDER BY run_seq`,
        [runId],
      );
      const { rows: unchained } = await s.query<{ n: string }>(
        `SELECT count(*)::text AS n FROM evidence_events
         WHERE run_id = $1 AND (hash IS NULL OR run_seq IS NULL)`,
        [runId],
      );

      if (Number(unchained[0]!.n) > 0) {
        return {
          valid: false,
          runId,
          eventCount: events.length,
          reason: "unchained ledger rows present",
        };
      }

      let prevHash = GENESIS_HASH;
      for (let i = 0; i < events.length; i++) {
        const row = events[i]!;
        const expectedSeq = i + 1;

        if (Number(row.run_seq) !== expectedSeq) {
          return {
            valid: false,
            runId,
            eventCount: events.length,
            firstInvalidEventId: row.id,
            reason: `sequence gap/reorder: expected ${expectedSeq}, found ${row.run_seq}`,
          };
        }

        if (row.prev_hash !== prevHash) {
          return {
            valid: false,
            runId,
            eventCount: events.length,
            firstInvalidEventId: row.id,
            expectedHash: prevHash,
            actualHash: row.prev_hash,
            reason: "prev_hash linkage broken",
          };
        }

        const recomputed = hashBoundRecord(
          buildBoundRecord(chainInputFromRow(row)),
        );
        if (recomputed !== row.hash) {
          return {
            valid: false,
            runId,
            eventCount: events.length,
            firstInvalidEventId: row.id,
            expectedHash: recomputed,
            actualHash: row.hash,
            reason: "hash mismatch: event content or metadata was modified",
          };
        }

        prevHash = row.hash;
      }

      if (opts?.expectedHeadHash) {
        const head = events[events.length - 1];
        if (!head || head.hash !== opts.expectedHeadHash) {
          return {
            valid: false,
            runId,
            eventCount: events.length,
            expectedHash: opts.expectedHeadHash,
            actualHash: head?.hash,
            reason: "chain head does not match expected anchor (forged append?)",
          };
        }
      }

      return { valid: true, runId, eventCount: events.length };
    });
  }
}
