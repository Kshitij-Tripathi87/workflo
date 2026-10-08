import { randomUUID } from "node:crypto";
import path from "node:path";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { spawn, execFile } from "node:child_process";
import { Db, runs, missions, projects, type TenantContext } from "@workflo/db";
import type { SandboxRunner, ExecResult, SpawnHandle } from "@workflo/sandbox";
import { PG_PORT } from "./global-setup";

export const APP_URL = `postgres://workflo_app:workflo@127.0.0.1:${PG_PORT}/workflo_executor_test`;
export const SUPER_URL = `postgres://postgres:postgres@127.0.0.1:${PG_PORT}/workflo_executor_test`;

export function appDb(): Db {
  return Db.fromUrl(APP_URL, { max: 8 });
}

/**
 * LocalTestRunner — TEST ONLY. Hosts workloads via raw child_process so the
 * executor's phases/health/teardown logic can be exercised on this machine.
 * It makes NO sandbox claims; pipeline callers must pass
 * sandboxMode: "unsandboxed-test-runner".
 *
 * On Windows, npm/node commands run via `cmd /c` so .cmd shims resolve.
 */
export class LocalTestRunner implements SandboxRunner {
  private wrap(cmd: string, args: string[]): [string, string[]] {
    if (process.platform === "win32") return ["cmd.exe", ["/c", cmd, ...args]];
    return [cmd, args];
  }

  exec(cmd: string, args: string[], opts?: { input?: string; timeoutMs?: number }): Promise<ExecResult> {
    const [c, a] = this.wrap(cmd, args);
    return new Promise((resolve) => {
      execFile(c, a, { timeout: opts?.timeoutMs ?? 30_000 }, (error, stdout, stderr) => {
        const code = error && typeof error.code === "number" ? error.code : error ? 1 : 0;
        resolve({ code, stdout: String(stdout), stderr: String(stderr), signal: null });
      });
    });
  }

  spawn(cmd: string, args: string[], opts?: { env?: NodeJS.ProcessEnv; cwd?: string }): SpawnHandle {
    const [c, a] = this.wrap(cmd, args);
    const child = spawn(c, a, {
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, ...(opts?.env ?? {}) },
      cwd: opts?.cwd ?? this.cwd,
    });
    const out: Buffer[] = [];
    const err: Buffer[] = [];
    child.stdout?.on("data", (d: Buffer) => out.push(d));
    child.stderr?.on("data", (d: Buffer) => err.push(d));
    return {
      pid: child.pid ?? -1,
      process: child,
      wait: () =>
        new Promise((resolve, reject) => {
          child.on("error", reject);
          child.on("exit", (code, signal) =>
            resolve({
              code: code ?? -1,
              stdout: Buffer.concat(out).toString("utf8"),
              stderr: Buffer.concat(err).toString("utf8"),
              signal,
            }),
          );
        }),
      kill: (signal = "SIGKILL") => child.kill(signal),
    };
  }

  cwd?: string;
  lib = true;

  async writeFile(p: string, content: string): Promise<void> {
    const { writeFile } = await import("node:fs/promises");
    await writeFile(p, content, "utf8");
  }
  async readFile(p: string): Promise<string> {
    const { readFile } = await import("node:fs/promises");
    return readFile(p, "utf8");
  }
  async exists(p: string): Promise<boolean> {
    try {
      const { access } = await import("node:fs/promises");
      await access(p);
      return true;
    } catch {
      return false;
    }
  }
  async removeTree(p: string): Promise<void> {
    await rm(p, { recursive: true, force: true });
  }
  async mkdir(p: string): Promise<void> {
    const { mkdir } = await import("node:fs/promises");
    await mkdir(p, { recursive: true });
  }
}

export interface ExecFixture {
  ctx: TenantContext & { projectId: string };
  orgId: string;
  projectId: string;
  missionId: string;
  runId: string;
  destRoot: string;
  runner: LocalTestRunner;
  cleanup: () => Promise<void>;
}

export async function makeExecFixture(db: Db, label: string): Promise<ExecFixture> {
  const orgId = randomUUID();
  const userId = randomUUID();
  const sysDb = Db.fromUrl(SUPER_URL, { max: 2 });
  try {
    await sysDb.system(async (c) => {
      await c.query(`INSERT INTO organizations (id, name, slug) VALUES ($1, $2, $3)`, [
        orgId, label, `${label}-${randomUUID().slice(0, 6)}`,
      ]);
      await c.query(`INSERT INTO users (id, email) VALUES ($1, $2)`, [
        userId, `${label}-${randomUUID().slice(0, 6)}@example.com`,
      ]);
    });
  } finally {
    await sysDb.close();
  }

  const ctxBase: TenantContext = { orgId, userId };
  const destRoot = await mkdtemp(path.join(tmpdir(), `wf-exec-${label}-`));
  const runner = new LocalTestRunner();

  const ids = await db.withTenant(ctxBase, async (s) => {
    await s.query(
      `INSERT INTO memberships (organization_id, user_id, role) VALUES ($1, $2, 'owner')`,
      [orgId, userId],
    );
    const project = await projects.createProject(s, `${label}-proj`, `p-${randomUUID().slice(0, 6)}`);
    const mission = await missions.createMission(s, {
      projectId: project.id, title: `${label}-mission`, intent: "verify",
    });
    const run = await runs.createRun(s, { projectId: project.id, missionId: mission.id });
    return { projectId: project.id, missionId: mission.id, runId: run.id };
  });

  return {
    ctx: { ...ctxBase, projectId: ids.projectId },
    orgId,
    ...ids,
    destRoot,
    runner,
    cleanup: async () => {
      await rm(destRoot, { recursive: true, force: true });
    },
  };
}
