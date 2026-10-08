import { describe, expect, it } from "vitest";
import { EvidenceLedger } from "../src";
import { Db } from "@workflo/db";
import { appDb, makeRunFixture, APP_URL } from "./helpers";

describe("ledger: concurrency", () => {
  it("12 concurrent appends to the same run serialize to a valid chain", async () => {
    const seedDb = appDb();
    const t = await makeRunFixture(seedDb, "concurrent");
    await seedDb.close();

    const N = 12;
    await Promise.all(
      Array.from({ length: N }, (_, i) => {
        const db = Db.fromUrl(APP_URL, { max: 2 });
        const ledger = new EvidenceLedger(db);
        return ledger
          .appendEvent(t.ctx, {
            runId: t.runId,
            kind: "OBSERVATION",
            role: "EXPLORER",
            status: "info",
            summary: `parallel ${i}`,
            payload: { i },
          })
          .finally(() => db.close());
      }),
    );

    const checkDb = appDb();
    try {
      const ledger = new EvidenceLedger(checkDb);
      const events = await ledger.getRunEvents(t.ctx, t.runId);
      expect(events).toHaveLength(N);
      const seqs = events.map((e) => Number(e.run_seq)).sort((a, b) => a - b);
      expect(seqs).toEqual(Array.from({ length: N }, (_, i) => i + 1));

      const result = await ledger.verifyRunChain(t.ctx, t.runId);
      expect(result.valid).toBe(true);
      expect(result.eventCount).toBe(N);
    } finally {
      await checkDb.close();
    }
  });
});
