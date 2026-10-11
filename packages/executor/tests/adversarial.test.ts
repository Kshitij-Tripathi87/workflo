import { describe, expect, it } from "vitest";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { EvidenceLedger } from "@workflo/events";
import { runExecutionPipeline } from "../src/lifecycle";
import { appDb, makeExecFixture } from "./helpers";
import {
  createFixtureRemote,
  CRASH_FIXTURE_FILES,
  HANG_FIXTURE_FILES,
  TESTFAIL_FIXTURE_FILES,
  CHILD_DAEMON_FIXTURE_FILES,
} from "./fixtures";
import { pidAlive } from "../src/process-utils";

describe("adversarial execution paths", () => {
  it("app crashes at startup → CRASHED → run FAILED → teardown still verified", async () => {
    const db = appDb();
    const remote = await createFixtureRemote(CRASH_FIXTURE_FILES, "crash");
    try {
      const t = await makeExecFixture(db, "crash");
      const ledger = new EvidenceLedger(db);
      const report = await runExecutionPipeline({
        ctx: t.ctx, db, ledger, runner: t.runner, runId: t.runId,
        ingest: { url: remote.url, ref: "main", destRoot: t.destRoot, sandboxId: "sbx-crash" },
        sandboxMode: "unsandboxed-test-runner",
        health: { port: 49101, timeoutMs: 5000, intervalMs: 150 },
        testTimeoutMs: 15_000,
      });

      expect(report.readiness).toBe("CRASHED");
      expect(report.testOutcome).toBe("NOT_RUN");
      expect(report.finalState).toBe("FAILED");
      expect(report.teardownVerified).toBe(true);

      const events = await ledger.getRunEvents(t.ctx, t.runId);
      expect(events.map((e) => e.event_type)).toContain("RUN_FAILED");
      expect(events.at(-1)!.event_type).toBe("TEARDOWN_VERIFIED");

      const verify = await ledger.verifyRunChain(t.ctx, t.runId);
      expect(verify.valid).toBe(true);
    } finally {
      await remote.cleanup();
      await db.close();
    }
  }, 120_000);

  it("app never listens → READY_TIMEOUT → FAILED", async () => {
    const db = appDb();
    const remote = await createFixtureRemote(HANG_FIXTURE_FILES, "hang");
    try {
      const t = await makeExecFixture(db, "hang");
      const ledger = new EvidenceLedger(db);
      const report = await runExecutionPipeline({
        ctx: t.ctx, db, ledger, runner: t.runner, runId: t.runId,
        ingest: { url: remote.url, ref: "main", destRoot: t.destRoot, sandboxId: "sbx-hang" },
        sandboxMode: "unsandboxed-test-runner",
        health: { port: 49102, timeoutMs: 2500, intervalMs: 200 },
        testTimeoutMs: 15_000,
      });

      expect(report.readiness).toBe("READY_TIMEOUT");
      expect(report.testOutcome).toBe("NOT_RUN");
      expect(report.finalState).toBe("FAILED");
      expect(report.teardownVerified).toBe(true);
    } finally {
      await remote.cleanup();
      await db.close();
    }
  }, 120_000);

  it("tests fail → TEST_RESULTS FAILED, run is NOT infra-failed", async () => {
    const db = appDb();
    const remote = await createFixtureRemote(TESTFAIL_FIXTURE_FILES, "testfail");
    try {
      const t = await makeExecFixture(db, "testfail");
      const ledger = new EvidenceLedger(db);
      const report = await runExecutionPipeline({
        ctx: t.ctx, db, ledger, runner: t.runner, runId: t.runId,
        ingest: { url: remote.url, ref: "main", destRoot: t.destRoot, sandboxId: "sbx-testfail" },
        sandboxMode: "unsandboxed-test-runner",
        health: { port: 49103, timeoutMs: 10_000, intervalMs: 150 },
        testTimeoutMs: 30_000,
      });

      expect(report.readiness).toBe("READY");
      expect(report.testOutcome).toBe("FAILED");
      expect(report.finalState).toBe("EXECUTING"); // not infra failure
      expect(report.teardownVerified).toBe(true);

      const events = await ledger.getRunEvents(t.ctx, t.runId);
      const testEvent = events.find((e) => e.event_type === "TEST_RESULTS");
      expect((testEvent!.payload as { outcome: string }).outcome).toBe("FAILED");
      expect(events.some((e) => e.event_type === "RUN_FAILED")).toBe(false);
    } finally {
      await remote.cleanup();
      await db.close();
    }
  }, 120_000);

  it("child daemon does not survive teardown", async () => {
    const db = appDb();
    const remote = await createFixtureRemote(CHILD_DAEMON_FIXTURE_FILES, "daemon");
    try {
      const t = await makeExecFixture(db, "daemon");
      const pidFile = path.join(t.destRoot, "child.pid");
      const ledger = new EvidenceLedger(db);
      const report = await runExecutionPipeline({
        ctx: t.ctx, db, ledger, runner: t.runner, runId: t.runId,
        ingest: { url: remote.url, ref: "main", destRoot: t.destRoot, sandboxId: "sbx-daemon" },
        sandboxMode: "unsandboxed-test-runner",
        extraEnv: { WORKFLO_CHILD_PID_FILE: pidFile },
        health: { port: 49104, timeoutMs: 10_000, intervalMs: 150 },
        testTimeoutMs: 30_000,
      });
      expect(report.readiness).toBe("READY");
      expect(report.testOutcome).toBe("PASSED");
      expect(report.teardownVerified).toBe(true);

      // The daemon child pid must be dead.
      const daemonPid = Number(await readFile(pidFile, "utf8"));
      expect(Number.isInteger(daemonPid)).toBe(true);
      expect(await pidAlive(t.runner, daemonPid)).toBe(false);
    } finally {
      await remote.cleanup();
      await db.close();
    }
  }, 120_000);
});
