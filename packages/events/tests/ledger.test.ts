import { describe, expect, it } from "vitest";
import { randomUUID } from "node:crypto";
import { EvidenceLedger, GENESIS_HASH, InMemoryEventBus } from "../src";
import { PublicAgentEventSchema } from "@workflo/contracts";
import { appDb, makeRunFixture, superDb } from "./helpers";
import type { Db } from "@workflo/db";

async function seedThreeEvents(db: Db, label: string) {
  const t = await makeRunFixture(db, label);
  const ledger = new EvidenceLedger(db);
  const kinds = [
    { kind: "MISSION_ACCEPTED", role: "ORCHESTRATOR" },
    { kind: "SANDBOX_PROVISIONED", role: "PROVISIONER" },
    { kind: "OBSERVATION", role: "EXPLORER" },
  ] as const;
  for (let i = 0; i < kinds.length; i++) {
    await ledger.appendEvent(t.ctx, {
      runId: t.runId,
      kind: kinds[i]!.kind,
      role: kinds[i]!.role,
      status: "info",
      summary: `event ${i + 1}`,
      payload: { i: i + 1 },
    });
  }
  return { t, ledger };
}

/** Simulate an attacker with raw DML rights (backup corruption, stolen superuser):
 * bypass the append-only trigger, mutate, re-enable. */
async function tamper(sql: string, params: unknown[] = []) {
  const sdb = superDb();
  try {
    await sdb.system(async (c) => {
      await c.query(`ALTER TABLE evidence_events DISABLE TRIGGER evidence_events_append_only`);
      await c.query(sql, params);
      await c.query(`ALTER TABLE evidence_events ENABLE TRIGGER evidence_events_append_only`);
    });
  } finally {
    await sdb.close();
  }
}

describe("ledger: normal chain", () => {
  it("append 3 events → chain verifies VALID with correct linkage", async () => {
    const db = appDb();
    try {
      const { t, ledger } = await seedThreeEvents(db, "chain-ok");
      const events = await ledger.getRunEvents(t.ctx, t.runId);
      expect(events).toHaveLength(3);
      expect(events[0]!.prev_hash).toBe(GENESIS_HASH);
      expect(events[1]!.prev_hash).toBe(events[0]!.hash);
      expect(events[2]!.prev_hash).toBe(events[1]!.hash);
      expect(events.map((e) => Number(e.run_seq))).toEqual([1, 2, 3]);

      const result = await ledger.verifyRunChain(t.ctx, t.runId);
      expect(result.valid).toBe(true);
      expect(result.eventCount).toBe(3);

      const withHead = await ledger.verifyRunChain(t.ctx, t.runId, {
        expectedHeadHash: events[2]!.hash,
      });
      expect(withHead.valid).toBe(true);
    } finally {
      await db.close();
    }
  });

  it("append is atomic: a mismatched prevHash writes nothing", async () => {
    const db = appDb();
    try {
      const { t } = await seedThreeEvents(db, "chain-atomic");
      const { evidence } = await import("@workflo/db");
      await expect(
        db.withTenant(t.ctx, (s) =>
          evidence.appendEvent(s, {
            eventId: randomUUID(),
            runId: t.runId,
            runSeq: 4,
            prevHash: "f".repeat(64),
            hash: "e".repeat(64),
            kind: "OBSERVATION",
            role: "EXPLORER",
            status: "info",
            summary: "bad link",
            occurredAt: new Date(),
          }),
        ),
      ).rejects.toThrow(/chain conflict/);

      const count = await db.withTenant(t.ctx, async (s) => {
        const { rows } = await s.query<{ n: string }>(
          `SELECT count(*)::text AS n FROM evidence_events WHERE run_id = $1`,
          [t.runId],
        );
        return Number(rows[0]!.n);
      });
      expect(count).toBe(3);
    } finally {
      await db.close();
    }
  });
});

describe("ledger: adversarial tamper detection", () => {
  it("Test 2 — payload modified → INVALID", async () => {
    const db = appDb();
    try {
      const { t, ledger } = await seedThreeEvents(db, "tamper-payload");
      const events = await ledger.getRunEvents(t.ctx, t.runId);
      await tamper(
        `UPDATE evidence_events SET payload = '{"i":99}' WHERE id = $1`,
        [events[1]!.id],
      );
      const result = await ledger.verifyRunChain(t.ctx, t.runId);
      expect(result.valid).toBe(false);
      expect(result.firstInvalidEventId).toBe(events[1]!.id);
      expect(result.reason).toContain("hash mismatch");
    } finally {
      await db.close();
    }
  });

  it("Test 3 — event_type (metadata) modified → INVALID", async () => {
    const db = appDb();
    try {
      const { t, ledger } = await seedThreeEvents(db, "tamper-meta");
      const events = await ledger.getRunEvents(t.ctx, t.runId);
      await tamper(
        `UPDATE evidence_events SET event_type = 'TOOL_DENIED' WHERE id = $1`,
        [events[1]!.id],
      );
      const result = await ledger.verifyRunChain(t.ctx, t.runId);
      expect(result.valid).toBe(false);
      expect(result.reason).toContain("hash mismatch");
    } finally {
      await db.close();
    }
  });

  it("Test 4 — sequence modified → INVALID", async () => {
    const db = appDb();
    try {
      const { t, ledger } = await seedThreeEvents(db, "tamper-seq");
      const events = await ledger.getRunEvents(t.ctx, t.runId);
      await tamper(
        `UPDATE evidence_events SET run_seq = 99 WHERE id = $1`,
        [events[1]!.id],
      );
      const result = await ledger.verifyRunChain(t.ctx, t.runId);
      expect(result.valid).toBe(false);
      expect(result.reason).toMatch(/sequence|linkage/i);
    } finally {
      await db.close();
    }
  });

  it("Test 5 — previous hash modified → INVALID", async () => {
    const db = appDb();
    try {
      const { t, ledger } = await seedThreeEvents(db, "tamper-prev");
      const events = await ledger.getRunEvents(t.ctx, t.runId);
      await tamper(
        `UPDATE evidence_events SET prev_hash = $2 WHERE id = $1`,
        [events[2]!.id, "a".repeat(64)],
      );
      const result = await ledger.verifyRunChain(t.ctx, t.runId);
      expect(result.valid).toBe(false);
      expect(result.firstInvalidEventId).toBe(events[2]!.id);
      expect(result.reason).toContain("prev_hash");
    } finally {
      await db.close();
    }
  });

  it("Test 6 — middle event deleted → INVALID (gap)", async () => {
    const db = appDb();
    try {
      const { t, ledger } = await seedThreeEvents(db, "tamper-delete");
      const events = await ledger.getRunEvents(t.ctx, t.runId);
      await tamper(`DELETE FROM evidence_events WHERE id = $1`, [events[1]!.id]);
      const result = await ledger.verifyRunChain(t.ctx, t.runId);
      expect(result.valid).toBe(false);
      expect(result.reason).toMatch(/sequence|linkage/i);
    } finally {
      await db.close();
    }
  });

  it("Test 7 — reordered events → INVALID", async () => {
    const db = appDb();
    try {
      const { t, ledger } = await seedThreeEvents(db, "tamper-reorder");
      const events = await ledger.getRunEvents(t.ctx, t.runId);
      await tamper(
        `UPDATE evidence_events SET run_seq = 20 WHERE id = $1`,
        [events[1]!.id],
      );
      await tamper(
        `UPDATE evidence_events SET run_seq = 2 WHERE id = $1`,
        [events[2]!.id],
      );
      await tamper(
        `UPDATE evidence_events SET run_seq = 3 WHERE id = $1`,
        [events[1]!.id],
      );
      const result = await ledger.verifyRunChain(t.ctx, t.runId);
      expect(result.valid).toBe(false);
    } finally {
      await db.close();
    }
  });

  it("Test 8 — forged append: garbage link fails recompute; self-consistent tail fails anchor", async () => {
    const db = appDb();
    try {
      const { t, ledger } = await seedThreeEvents(db, "tamper-forge");
      const events = await ledger.getRunEvents(t.ctx, t.runId);
      const honestHead = events[2]!.hash;

      // Forgery A: wrong linkage/hash — fails at recomputation/anchor.
      const sdb = superDb();
      try {
        await sdb.system((c) =>
          c.query(
            `INSERT INTO evidence_events
              (organization_id, project_id, run_id, run_seq, event_type, role,
               status, summary, occurred_at, prev_hash, hash)
             VALUES ($1,$2,$3,4,'RUN_FAILED','ORCHESTRATOR','error','forged',
                     now(),$4,$5)`,
            [t.orgId, t.projectId, t.runId, honestHead, "f".repeat(64)],
          ),
        );
      } finally {
        await sdb.close();
      }

      const forged = await ledger.verifyRunChain(t.ctx, t.runId);
      expect(forged.valid).toBe(false);

      // Forgery B: attacker recomputes the hash correctly. Pure chain math
      // cannot detect this (internally consistent) — the external anchor
      // (expectedHeadHash = receipt ledger_root, Day 8+) is what catches it.
      {
        const sdb2 = superDb();
        try {
          await sdb2.system(async (c) => {
            await c.query(
              `ALTER TABLE evidence_events DISABLE TRIGGER evidence_events_append_only`,
            );
            try {
              await c.query(`DELETE FROM evidence_events WHERE summary = 'forged'`);
              const { computeEventHash } = await import("../src/hash-chain");
              const forgedId = randomUUID();
              const forgedHash = computeEventHash({
                eventId: forgedId,
                organizationId: t.orgId,
                projectId: t.projectId,
                runId: t.runId,
                runSeq: 4,
                kind: "RUN_FAILED",
                role: "ORCHESTRATOR",
                status: "error",
                parentEventId: null,
                requestId: null,
                action: null,
                summary: "forged tail",
                rationale: null,
                observationSummary: null,
                policyId: null,
                payload: {},
                occurredAt: new Date("2026-09-30T12:00:03.000Z"),
                prevHash: honestHead,
              });
              await c.query(
                `INSERT INTO evidence_events
                  (id, organization_id, project_id, run_id, run_seq, event_type,
                   role, status, summary, occurred_at, prev_hash, hash)
                 VALUES ($1,$2,$3,$4,4,'RUN_FAILED','ORCHESTRATOR','error',
                         'forged tail','2026-09-30T12:00:03.000Z',$5,$6)`,
                [forgedId, t.orgId, t.projectId, t.runId, honestHead, forgedHash],
              );
            } finally {
              await c.query(
                `ALTER TABLE evidence_events ENABLE TRIGGER evidence_events_append_only`,
              );
            }
          });
        } finally {
          await sdb2.close();
        }
      }

      const unanchored = await ledger.verifyRunChain(t.ctx, t.runId);
      expect(unanchored.valid).toBe(true); // self-consistent: chain math alone can't see it

      const anchored = await ledger.verifyRunChain(t.ctx, t.runId, {
        expectedHeadHash: honestHead,
      });
      expect(anchored.valid).toBe(false);
      expect(anchored.reason).toContain("head");
    } finally {
      await db.close();
    }
  });

  it("Test 9 — tenant isolation: A cannot read/append/verify B's chain", async () => {
    const db = appDb();
    try {
      const a = await makeRunFixture(db, "iso-a");
      const b = await makeRunFixture(db, "iso-b");
      const ledger = new EvidenceLedger(db);
      await ledger.appendEvent(b.ctx, {
        runId: b.runId,
        kind: "OBSERVATION",
        role: "EXECUTOR",
        status: "info",
        summary: "b data",
      });

      const read = await ledger.getRunEvents(a.ctx, b.runId);
      expect(read).toHaveLength(0);

      await expect(
        ledger.appendEvent(a.ctx, {
          runId: b.runId,
          kind: "OBSERVATION",
          role: "EXPLORER",
          status: "info",
          summary: "inject into B",
        }),
      ).rejects.toThrow(/run not found/);

      const verify = await ledger.verifyRunChain(a.ctx, b.runId);
      expect(verify.valid).toBe(true);
      expect(verify.eventCount).toBe(0); // A sees an empty world, not B's data
    } finally {
      await db.close();
    }
  });
});

describe("ledger: bus durability invariant", () => {
  it("bus publish failure does not unwrite the ledger; replay recovers", async () => {
    const db = appDb();
    try {
      const t = await makeRunFixture(db, "bus-durable");
      const bus = new InMemoryEventBus();
      await bus.subscribe(async () => {
        throw new Error("subscriber down");
      });
      const ledger = new EvidenceLedger(db, bus);

      const ev = await ledger.appendEvent(t.ctx, {
        runId: t.runId,
        kind: "APP_STARTED",
        role: "EXECUTOR",
        status: "success",
        summary: "app up",
      });

      const stored = await ledger.getEvent(t.ctx, ev.id);
      expect(stored).not.toBeNull();

      const replayed: string[] = [];
      const replayBus = new InMemoryEventBus();
      await replayBus.subscribe(async (e) => {
        replayed.push(e.eventId);
      });
      const storedEvent = PublicAgentEventSchema.parse({
        eventId: stored!.id,
        runId: stored!.run_id,
        parentEventId: null,
        role: stored!.role,
        kind: stored!.event_type,
        status: stored!.status,
        summary: stored!.summary,
        occurredAt: stored!.occurred_at,
      });
      await replayBus.publish(storedEvent);
      expect(replayed).toEqual([ev.id]);
    } finally {
      await db.close();
    }
  });
});
