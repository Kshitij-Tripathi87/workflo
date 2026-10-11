import { describe, expect, it } from "vitest";
import { EvidenceLedger } from "@workflo/events";
import { runs } from "@workflo/db";
import { runExecutionPipeline } from "../src/lifecycle";
import { appDb, makeExecFixture } from "./helpers";
import {
  createFixtureRemote,
  NODE_FIXTURE_FILES,
  CRASH_FIXTURE_FILES,
  HANG_FIXTURE_FILES,
  TESTFAIL_FIXTURE_FILES,
} from "./fixtures";

describe("golden path: fixture repo → READY → tests PASS → teardown VERIFIED → chain VALID", () => {
  it("full pipeline emits a verifiable ledger", async () => {
    const db = appDb();
    const remote = await createFixtureRemote(NODE_FIXTURE_FILES, "golden");
    try {
      const t = await makeExecFixture(db, "golden");
      const ledger = new EvidenceLedger(db);

      const report = await runExecutionPipeline({
        ctx: t.ctx,
        db,
        ledger,
        runner: t.runner,
        runId: t.runId,
        ingest: {
          url: remote.url,
          ref: "main",
          destRoot: t.destRoot,
          sandboxId: "sbx-golden",
        },
        sandboxMode: "unsandboxed-test-runner",
        extraEnv: { WORKFLO_RUN_ID: t.runId },
        health: { port: 49105, timeoutMs: 12_000, intervalMs: 150 },
        testTimeoutMs: 60_000,
      });

      // Golden assertions
      expect(report.readiness).toBe("READY");
      expect(report.testOutcome).toBe("PASSED");
      expect(report.deps).toBe("SKIPPED"); // fixture has no deps
      expect(report.teardownVerified).toBe(true);
      expect(report.headHash).toMatch(/^[a-f0-9]{64}$/);
      expect(report.provenance.commitSha).toMatch(/^[0-9a-f]{40}$/);
      expect(report.finalState).toBe("EXECUTING"); // Explorer/Judge/Notary are Days 7-9

      // Event surface: the full lifecycle hit the ledger
      const events = await ledger.getRunEvents(t.ctx, t.runId);
      const kinds = events.map((e) => e.event_type);
      expect(kinds).toContain("REPO_INGESTED");
      expect(kinds).toContain("APP_STARTED");
      expect(kinds).toContain("APP_HEALTHY");
      expect(kinds).toContain("TEST_RESULTS");
      expect(kinds).toContain("TEARDOWN_VERIFIED");
      expect(kinds.lastIndexOf("TEARDOWN_VERIFIED")).toBe(kinds.length - 1);

      // No CoT-class leakage in any payload
      for (const e of events) {
        expect(JSON.stringify(e.payload)).not.toMatch(/chain.?of.?thought/i);
      }

      // Chain integrity
      const verify = await ledger.verifyRunChain(t.ctx, t.runId, {
        expectedHeadHash: report.headHash!,
      });
      expect(verify.valid).toBe(true);
      expect(verify.eventCount).toBe(events.length);
    } finally {
      await remote.cleanup();
      await db.close();
    }
  }, 180_000);
});
