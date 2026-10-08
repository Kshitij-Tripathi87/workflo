import path from "node:path";
import { fileURLToPath } from "node:url";
import type { ExecResult, SandboxRunner, SpawnHandle } from "../src/runner";
import type { SandboxSpec } from "../src/spec";
import { parseSandboxSpec } from "../src/spec";

export const POLICIES_ROOT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
  "..",
  "infra",
  "policies",
);

export function makeSpec(overrides: Record<string, unknown> = {}): SandboxSpec {
  return parseSandboxSpec({
    sandboxId: "sbx-test01",
    runId: "550e8400-e29b-41d4-a716-446655440000",
    workspaceDir: "/var/lib/workflo/sandboxes/sbx-test01",
    resources: { cpu: 2, memoryMb: 1024, pids: 128, timeoutSec: 600 },
    ...overrides,
  });
}

/** In-memory runner: records all effects, returns scripted exec results. */
export class FakeRunner implements SandboxRunner {
  readonly fs = new Map<string, string>();
  readonly removed: string[] = [];
  readonly execCalls: Array<{ cmd: string; args: string[] }> = [];
  readonly spawnCalls: Array<{ cmd: string; args: string[] }> = [];
  execResults: Array<Partial<ExecResult>> = [];
  spawned: SpawnHandle[] = [];
  nextPid = 1000;

  async exec(cmd: string, args: string[]): Promise<ExecResult> {
    this.execCalls.push({ cmd, args });
    const scripted = this.execResults.length ? this.execResults.shift()! : {};
    return { code: scripted.code ?? 1, stdout: scripted.stdout ?? "", stderr: scripted.stderr ?? "", signal: null };
  }

  spawn(cmd: string, args: string[]): SpawnHandle {
    this.spawnCalls.push({ cmd, args });
    const pid = this.nextPid++;
    const handle: SpawnHandle = {
      pid,
      process: null as unknown as SpawnHandle["process"],
      wait: async () => ({ code: 0, stdout: "", stderr: "", signal: null }),
      kill: () => true,
    };
    this.spawned.push(handle);
    return handle;
  }

  async writeFile(p: string, content: string): Promise<void> {
    this.fs.set(p, content);
  }

  async readFile(p: string): Promise<string> {
    const v = this.fs.get(p);
    if (v === undefined) throw new Error(`fake fs miss: ${p}`);
    return v;
  }

  async exists(p: string): Promise<boolean> {
    return this.fs.has(p);
  }

  async removeTree(p: string): Promise<void> {
    this.removed.push(p);
    for (const key of [...this.fs.keys()]) {
      if (key === p || key.startsWith(p + "/")) this.fs.delete(key);
    }
  }

  async mkdir(p: string): Promise<void> {
    this.fs.set(p, "<dir>");
  }
}
