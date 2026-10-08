import { describe, expect, it } from "vitest";
import {
  EvidenceLedger,
  processOnce,
  consumedEvents,
  rebuildRunProjection,
  readRunProjection,
  reduceEvents,
} from "../src";
import { appDb, makeRunFixture } from "./helpers";

describe("consumer idempotency", () => {
  it("processing the same event three times runs the handler once", async () => {
    const db = appDb();
    try {
      const t = await makeRunFixture(db, "idem");
      const ledger = new EvidenceLedger(db);
      const ev = await ledger.appendEvent(t.ctx, {
        runId: t.runId,
        kind: "TOOL_DENIED",
        role: "TOOL_GATEWAY",
        status: "denied",
        summary: "denied external call",
        policyId: "net-egress-deny",
      });

      let calls = 0;
      const handler = async () => {
        calls += 1;
      };

      const r1 = await processOnce(db, t.ctx, "test-consumer", ev.id, handler);
      const r2 = await processOnce(db, t.ctx, "test-consumer", ev.id, handler);
      const r3 = await processOnce(db, t.ctx, "test-consumer", ev.id, handler);

      expect([r1, r2, r3]).toEqual(["processed", "duplicate", "duplicate"]);
      expect(calls).toBe(1);

      // a different consumer identity must still process the event
      const r4 = await processOnce(db, t.ctx, "other-consumer", ev.id, handler);
      expect(r4).toBe("processed");
      expect(calls).toBe(2);

      expect(await consumedEvents(db, t.ctx, "test-consumer")).toEqual([ev.id]);
    } finally {
      await db.close();
    }
  });
});

describe("projections: replayable derived state", () => {
  it("rebuilds identical state after the projection row is dropped", async () => {
    const db = appDb();
    try {
      const t = await makeRunFixture(db, "proj");
      const ledger = new EvidenceLedger(db);

      await ledger.appendEvent(t.ctx, {
        runId: t.runId,
        kind: "MISSION_ACCEPTED",
        role: "ORCHESTRATOR",
        status: "info",
        summary: "mission accepted",
      });
      await ledger.appendEvent(t.ctx, {
        runId: t.runId,
        kind: "STATE_CHANGE",
        role: "ORCHESTRATOR",
        status: "info",
        summary: "entering EXPLORING",
        payload: { to: "EXPLORING" },
      });
      await ledger.appendEvent(t.ctx, {
        runId: t.runId,
        kind: "TOOL_DENIED",
        role: "TOOL_GATEWAY",
        status: "denied",
        summary: "blocked",
      });

      const first = await rebuildRunProjection(db, t.ctx, t.runId, ledger);
      expect(first.lifecycle).toBe("EXPLORING");
      expect(first.counts["TOOL_DENIED"]).toBe(1);
      expect(first.denied).toBe(1);
      expect(first.lastRunSeq).toBe(3);

      const stored = await readRunProjection(db, t.ctx, t.runId);
      expect(stored).toEqual(first);

      // Corrupt/drop the projection and rebuild from the ledger.
      await db.withTenant(t.ctx, async (s) => {
        await s.query(
          `UPDATE run_projections SET state = '{"corrupted":true}'::jsonb WHERE run_id = $1`,
          [t.runId],
        );
        return null;
      });
      await db.withTenant(t.ctx, async (s) => {
        await s.query(`DELETE FROM run_projections WHERE run_id = $1`, [t.runId]);
        return null;
      });

      const rebuilt = await rebuildRunProjection(db, t.ctx, t.runId, ledger);
      expect(rebuilt).toEqual(first);
    } finally {
      await db.close();
    }
  });

  it("reducer is pure over event order", async () => {
    const db = appDb();
    try {
      const t = await makeRunFixture(db, "proj-pure");
      const ledger = new EvidenceLedger(db);
      await ledger.appendEvent(t.ctx, {
        runId: t.runId,
        kind: "FINDING_CONFIRMED",
        role: "JUDGE",
        status: "success",
        summary: "j",
      });
      const events = await ledger.getRunEvents(t.ctx, t.runId);
      const a = reduceEvents(events);
      const b = reduceEvents([...events]);
      expect(a).toEqual(b);
      expect(a.findingsConfirmed).toBe(1);
    } finally {
      await db.close();
    }
  });
});
