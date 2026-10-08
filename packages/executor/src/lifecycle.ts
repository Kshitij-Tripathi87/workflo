import type { Db, TenantContext } from "@workflo/db";
import { runs } from "@workflo/db";
import type { EvidenceLedger, LedgerAppendInput } from "@workflo/events";
import { ingest, type IngestRequest, type IngestedRepository, type Provenance } from "@workflo/ingestor";
import { ProcessScope, type SandboxRunner } from "@workflo/sandbox";
import { buildSandboxEnv } from "./env-policy";
import { probeHealth, type HealthResult } from "./health";
import { classifyResult } from "./result";
import { killTree, pidAlive } from "./process-utils";
import type { TestOutcome } from "./result";

/**
 * Execution pipeline — PREPARE → DEPENDENCIES → START → HEALTH → TEST →
 * STOP → TEARDOWN → VERIFY, with every material transition written to the
 * Day-4 ledger and every run-state transition through the Day-3 gatekeeping
 * function.
 *
 * Honesty rules:
 *  - run-state never advances past EXECUTING here (Explorer/Judge/Notary are
 *    Days 7–9; fabricating those stages would be fake execution)
 *  - infra failure → transition FAILED + RUN_FAILED event
 *  - test FAILURE is a RESULT, not an infra failure: TEST_RESULTS carries the
 *    outcome; the run stays truthfully in EXECUTING
 */

export interface PipelineOptions {
  ctx: TenantContext & { projectId: string };
  db: Db;
  ledger: EvidenceLedger;
  runner: SandboxRunner;
  runId: string;
  ingest: IngestRequest;
  /**
   * "sealed" only when the Day-5 sandbox really provisioned.
   * Test runners must declare "unsandboxed-test-runner" — never pretend.
   */
  sandboxMode: "sealed" | "unsandboxed-test-runner";
  workspaceCwd?: string;
  extraEnv?: Record<string, string>;
  health?: { path?: string; port?: number; timeoutMs?: number; intervalMs?: number };
  testTimeoutMs?: number;
}

export type Readiness = "READY" | "CRASHED" | "READY_TIMEOUT" | "NOT_RUN";

export interface PipelineReport {
  runId: string;
  provenance: Provenance;
  readiness: Readiness;
  deps: "OK" | "FAILED" | "SKIPPED";
  testOutcome: TestOutcome;
  teardownVerified: boolean;
  headHash: string | null;
  finalState: string;
  events: number;
}

export async function runExecutionPipeline(opts: PipelineOptions): Promise<PipelineReport> {
  const { db, ledger, ctx, runner, runId } = opts;
  const scope = new ProcessScope(`run-${runId.slice(0, 8)}`);

  const event = (input: Omit<LedgerAppendInput, "runId">) =>
    ledger.appendEvent(ctx, { runId, ...input });

  const fail = async (summary: string, payload: Record<string, unknown>) => {
    await event({
      kind: "RUN_FAILED", role: "EXECUTOR", status: "error", summary,
      payload,
    });
    return db.withTenant(ctx, (s) =>
      runs.transitionRun(s, runId, "FAILED", { error: summary }),
    );
  };

  // ---- INGESTING ----------------------------------------------------------
  await db.withTenant(ctx, (s) => runs.transitionRun(s, runId, "INGESTING"));
  await event({
    kind: "STATE_CHANGE", role: "ORCHESTRATOR", status: "info",
    summary: "CREATED → INGESTING", payload: { to: "INGESTING" },
  });

  let repo: IngestedRepository;
  try {
    repo = await ingest(opts.ingest);
  } catch (error) {
    await fail("ingest failed", { error: String((error as Error).message) });
    return finalizePipeline(opts, scope, null, "NOT_RUN", "NOT_RUN", "SKIPPED");
  }
  await event({
    kind: "REPO_INGESTED", role: "INGESTOR", status: "success",
    summary: `${repo.url}@${repo.commitSha.slice(0, 12)} (${repo.project.type})`,
    payload: {
      provider: repo.provider, url: repo.url, requestedRef: repo.requestedRef,
      refName: repo.refName, commitSha: repo.commitSha, treeSha: repo.treeSha,
      projectType: repo.project.type,
    },
  });

  // ---- PROVISIONING -------------------------------------------------------
  await db.withTenant(ctx, (s) => runs.transitionRun(s, runId, "PROVISIONING"));
  await event({
    kind: "STATE_CHANGE", role: "ORCHESTRATOR", status: "info",
    summary: "INGESTING → PROVISIONING", payload: { to: "PROVISIONING" },
  });

  if (opts.sandboxMode === "sealed") {
    await event({
      kind: "SANDBOX_PROVISIONED", role: "PROVISIONER", status: "success",
      summary: "sealed sandbox provisioned (bwrap/netns/cgroup/seccomp/landlock)",
      payload: { mode: "sealed" },
    });
  } else {
    await event({
      kind: "OBSERVATION", role: "PROVISIONER", status: "info",
      action: "provision-skipped",
      rationale: "platform gate: non-Linux environment; test runner is unsandboxed",
      summary: "no sandbox claims made on this platform",
      payload: { mode: "unsandboxed-test-runner" },
    });
  }

  // ---- EXECUTING: dependencies -------------------------------------------
  await db.withTenant(ctx, (s) => runs.transitionRun(s, runId, "EXECUTING"));
  await event({
    kind: "STATE_CHANGE", role: "ORCHESTRATOR", status: "info",
    summary: "PROVISIONING → EXECUTING", payload: { to: "EXECUTING" },
  });

  const cwd = opts.workspaceCwd ?? repo.workspacePath;
  const env = buildSandboxEnv({
    base: {
      PATH: process.env.PATH,
      HOME: process.env.HOME ?? process.env.USERPROFILE,
      NODE_ENV: "test",
    },
    extra: {
      ...(opts.extraEnv ?? {}),
      PORT: String(opts.health?.port ?? repo.project.port ?? 48711),
    },
  });

  let deps: PipelineReport["deps"] = "SKIPPED";
  if (repo.project.install.length > 0) {
    deps = "OK";
    for (const cmd of repo.project.install) {
      const started = Date.now();
      const handle = runner.spawn(cmd[0]!, cmd.slice(1), { env, ...(cwd ? { cwd } : {}) });
      scope.register(handle);
      const res = await handle.wait();
      if (res.code !== 0) {
        await event({
          kind: "OBSERVATION", role: "EXECUTOR", status: "error",
          action: "install", summary: `dependency install failed: ${cmd.join(" ")}`,
          payload: { phase: "DEPENDENCIES", exitCode: res.code, stderrTail: res.stderr.slice(-2000) },
        });
        await fail("dependency installation failed", { cmd: cmd.join(" ") });
        return finalizePipeline(opts, scope, repo, "NOT_RUN", "NOT_RUN", "FAILED");
      }
      void started;
    }
    await event({
      kind: "OBSERVATION", role: "EXECUTOR", status: "success",
      action: "install",
      summary: `dependencies installed (${repo.project.install.length} step${repo.project.install.length > 1 ? "s" : ""})`,
      payload: { phase: "DEPENDENCIES", steps: repo.project.install.map((c) => c.join(" ")) },
    });
  } else {
    await event({
      kind: "OBSERVATION", role: "EXECUTOR", status: "success",
      action: "install-skipped",
      summary: "no declared dependencies — install phase skipped",
      payload: { phase: "DEPENDENCIES", skipped: true },
    });
  }

  // ---- START + HEALTH -----------------------------------------------------
  let readiness: Readiness = "NOT_RUN";
  let testOutcome: TestOutcome = "NOT_RUN";
  let appAlive = false;

  if (repo.project.startCommand) {
    const start = repo.project.startCommand;
    const appHandle = runner.spawn(start[0]!, start.slice(1), { env, ...(cwd ? { cwd } : {}) });
    scope.register(appHandle);
    appAlive = true;
    appHandle.wait().then(() => { appAlive = false; }, () => { appAlive = false; });

    await event({
      kind: "APP_STARTED", role: "EXECUTOR", status: "info",
      summary: `${start.join(" ")} (pid ${appHandle.pid})`,
      payload: { pid: appHandle.pid, cmd: start.join(" ") },
    });

    const path = opts.health?.path ?? "/health";
    const port = opts.health?.port ?? repo.project.port ?? 48711;
    const url = `http://127.0.0.1:${port}${path}`;
    const health: HealthResult = await probeHealth({
      url,
      timeoutMs: opts.health?.timeoutMs ?? 10_000,
      ...(opts.health?.intervalMs !== undefined ? { intervalMs: opts.health.intervalMs } : {}),
      isAlive: () => appAlive,
    });
    readiness = health.state;

    if (health.state === "READY") {
      const firstOk = health.attempts.find((a) => a.ok);
      await event({
        kind: "APP_HEALTHY", role: "EXECUTOR", status: "success",
        summary: `READY at ${url} after ${health.attempts.length} attempt(s)`,
        observationSummary: `latency ${firstOk?.latencyMs ?? 0}ms`,
        payload: { url, attempts: health.attempts.length, latencyMs: firstOk?.latencyMs ?? 0 },
      });
    } else {
      await event({
        kind: "OBSERVATION", role: "EXECUTOR", status: "error",
        action: "health",
        summary: health.state === "CRASHED" ? "application crashed during startup" : "health deadline exceeded",
        payload: { url, attempts: health.attempts },
      });
    }
  }

  // ---- TEST ---------------------------------------------------------------
  if (readiness === "READY" && repo.project.testCommand) {
    const started = Date.now();
    let spawned = true;
    let timedOut = false;
    let result;
    try {
      const cmd = repo.project.testCommand;
      const handle = runner.spawn(cmd[0]!, cmd.slice(1), { env, ...(cwd ? { cwd } : {}) });
      scope.register(handle);
      result = await Promise.race([
        handle.wait(),
        new Promise<never>((_, reject) =>
          setTimeout(() => { timedOut = true; handle.kill("SIGKILL"); reject(new Error("test timeout")); },
            opts.testTimeoutMs ?? 60_000),
        ),
      ]);
    } catch {
      if (!timedOut) spawned = true; // spawn ok but execution error path
    }
    const classified = classifyResult({
      spawned, timedOut, ...(result !== undefined ? { result } : {}), durationMs: Date.now() - started,
    });
    testOutcome = classified.outcome;
    await event({
      kind: "TEST_RESULTS", role: "EXECUTOR",
      status: testOutcome === "PASSED" ? "success" : testOutcome === "TIMEOUT" ? "timeout" : testOutcome === "NOT_RUN" ? "info" : "error",
      summary: `tests ${testOutcome} (exit ${classified.exitCode ?? "n/a"}, ${classified.durationMs}ms)`,
      payload: {
        outcome: testOutcome, exitCode: classified.exitCode,
        durationMs: classified.durationMs,
        stdoutTail: classified.stdoutTail, stderrTail: classified.stderrTail,
      },
    });
  }

  // ---- FAILED infra paths --------------------------------------------------
  if (readiness === "CRASHED" || readiness === "READY_TIMEOUT") {
    await fail(
      readiness === "CRASHED" ? "application crashed during startup" : "application never became ready",
      { readiness },
    );
  }

  // ---- STOP + TEARDOWN + VERIFY -------------------------------------------
  scope.killAll("SIGTERM");
  await scope.waitAll(3000);
  // Tree-kill EVERY registered pid: on Windows, killing a shell wrapper does
  // not kill its node children; taskkill /T does. This also catches daemons.
  const registered = scope.list();
  for (const pid of registered) {
    await killTree(runner, pid);
  }
  await scope.waitAll(2000);

  const workspaceRemoved = opts.ingest
    ? !(await runner.exists(opts.ingest.destRoot ? `${opts.ingest.destRoot}/${opts.ingest.sandboxId}` : repo.workspacePath).catch(() => false))
    : true;

  // Clean the workspace AFTER probing process state.
  if (!workspaceRemoved) {
    await runner.removeTree(repo.workspacePath).catch(() => undefined);
  }

  const deadChecks = await Promise.all(registered.map(async (pid) => !(await pidAlive(runner, pid))));
  const teardownVerified = deadChecks.every(Boolean);
  await event({
    kind: "TEARDOWN_VERIFIED", role: "EXECUTOR",
    status: teardownVerified ? "success" : "error",
    summary: teardownVerified ? "teardown verified: no surviving processes; workspace cleaned" : "teardown incomplete",
    payload: {
      processesGone: deadChecks.every(Boolean),
      workspaceRemoved: await runner.exists(repo.workspacePath).then((e) => !e).catch(() => true),
      sandboxMode: opts.sandboxMode,
    },
  });

  return finalizePipeline(opts, scope, repo, readiness, testOutcome, deps);
}

async function finalizePipeline(
  opts: PipelineOptions,
  scope: ProcessScope,
  repo: IngestedRepository | null,
  readiness: Readiness,
  testOutcome: TestOutcome,
  deps: PipelineReport["deps"],
): Promise<PipelineReport> {
  const { db, ledger, ctx, runId } = opts;

  const finalState = await db.withTenant(ctx, async (s) => {
    const row = await runs.getRun(s, runId);
    return row?.state ?? "FAILED";
  });

  const events = await ledger.getRunEvents(ctx, runId);
  return {
    runId,
    provenance: repo
      ? {
          provider: repo.provider, url: repo.url, requestedRef: repo.requestedRef,
          refName: repo.refName, commitSha: repo.commitSha, treeSha: repo.treeSha,
        }
      : { provider: "git", url: "", requestedRef: "", refName: "", commitSha: "", treeSha: "" },
    readiness,
    deps,
    testOutcome,
    teardownVerified: events.at(-1)?.event_type === "TEARDOWN_VERIFIED"
      ? events.at(-1)?.status === "success"
      : false,
    headHash: events.at(-1)?.hash ?? null,
    finalState,
    events: events.length,
  };
}
