import type { Db, TenantContext, TenantSession } from "@workflo/db";

/**
 * Idempotent consumer processing.
 *
 * Dedup identity: (consumer_id, event_id) persisted in consumer_offsets.
 * Processing semantics: handler runs in the SAME transaction as the offset
 * mark → handler state changes and the mark commit atomically
 * (effectively-once). Live delivery, replay and worker restarts are safe.
 */

export type ConsumerOutcome = "processed" | "duplicate";

export async function processOnce(
  db: Db,
  ctx: TenantContext,
  consumerId: string,
  eventId: string,
  handler: (session: TenantSession) => Promise<void>,
): Promise<ConsumerOutcome> {
  return db.withTenant(ctx, async (s) => {
    const { rowCount } = await s.query(
      `INSERT INTO consumer_offsets (consumer_id, event_id, organization_id)
       VALUES ($1, $2, $3)
       ON CONFLICT (consumer_id, event_id) DO NOTHING`,
      [consumerId, eventId, ctx.orgId],
    );
    if (!rowCount) return "duplicate";
    await handler(s);
    return "processed";
  });
}

/** List event ids already consumed by a consumer (debugging/replay tooling). */
export async function consumedEvents(
  db: Db,
  ctx: TenantContext,
  consumerId: string,
): Promise<string[]> {
  return db.withTenant(ctx, async (s) => {
    const { rows } = await s.query<{ event_id: string }>(
      `SELECT event_id FROM consumer_offsets WHERE consumer_id = $1 ORDER BY processed_at`,
      [consumerId],
    );
    return rows.map((r) => r.event_id);
  });
}
