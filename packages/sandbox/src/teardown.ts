import { cgroupLayout, cgroupKillWrite } from "./cgroups";
import type { SandboxSpec } from "./spec";
import type { SandboxRunner } from "./runner";
import type { ProcessScope } from "./process-scope";
import type { TeardownProof } from "./attestation";

/**
 * Teardown — destroy the sandbox, then PROVE it is gone.
 *
 * A teardown that "ran commands" is a claim. What we produce is verification:
 * after teardown, each artifact is checked from outside the sandbox.
 */
export interface TeardownInput {
  spec: SandboxSpec;
  scope: ProcessScope;
  runner: SandboxRunner;
  /** Extra probe hooks for tests. */
  probes?: {
    processGone?: (pid: number) => Promise<boolean>;
    pathExists?: (path: string) => Promise<boolean>;
  };
}

export async function teardown(input: TeardownInput): Promise<TeardownProof> {
  const { spec, scope, runner } = input;

  // 1. Kill everything we know about.
  scope.killAll("SIGKILL");
  await scope.waitAll(5000);

  // 2. Freeze-kill via cgroup (catches anything that escaped the scope).
  const kill = cgroupKillWrite(spec.sandboxId);
  await runner.writeFile(kill.file, kill.value).catch(() => undefined);

  // 3. Remove cgroup + workspace.
  const layout = cgroupLayout(spec.sandboxId);
  await runner.removeTree(layout.path).catch(() => undefined);
  await runner.removeTree(spec.workspaceDir).catch(() => undefined);

  // 4. Verify — from outside the sandbox.
  const exists = input.probes?.pathExists ?? ((p: string) => runner.exists(p));

  const checks = {
    processesGone: scope.size === 0 || (await scopePidsGone(scope, input.probes?.processGone)),
    cgroupGone: !(await exists(layout.path)),
    netnsGone: !(await exists(`/var/run/netns/wf-${spec.sandboxId}`)),
    workspaceRemoved: !(await exists(spec.workspaceDir)),
  };

  return {
    sandboxId: spec.sandboxId,
    endedAt: new Date().toISOString(),
    checks,
    verified: Object.values(checks).every(Boolean),
  };
}

async function scopePidsGone(
  scope: ProcessScope,
  probe?: (pid: number) => Promise<boolean>,
): Promise<boolean> {
  if (!probe) return scope.size === 0;
  const results = await Promise.all(scope.list().map(probe));
  return results.every(Boolean);
}
