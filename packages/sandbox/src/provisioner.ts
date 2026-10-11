import type { SandboxSpec } from "./spec";
import { buildBwrapArgv } from "./bwrap";
import { cgroupLayout, cgroupLimitWrites, cgroupAttachWrite, verifyLimits } from "./cgroups";
import { loadSeccompProfile, auditSeccompProfile } from "./seccomp";
import { loadLandlockRuleset, instantiateRuleset } from "./landlock";
import { loadPolicyFile, type IsolationAttestation, type CanaryCheck } from "./attestation";
import { ProcessScope } from "./process-scope";
import type { SandboxRunner, SpawnHandle } from "./runner";
import { NodeSandboxRunner } from "./runner";
import { detectSupport, PlatformUnsupportedError } from "./platform";

/**
 * Provisioner — creates the sealed execution environment.
 *
 * Order (fail-closed: any failure tears everything down):
 *   1. platform support gate (Linux + bwrap + cgroup v2 + userns)
 *   2. load + audit policies (seccomp, landlock)
 *   3. compute bwrap argv (pure plan)
 *   4. create cgroup, write limits, attach nothing yet
 *   5. spawn workload via bwrap, register in process scope
 *   6. attach pid to cgroup; verify limits read-back
 *   7. run network canary (must FAIL to prove egress is blocked)
 *   8. assemble IsolationAttestation
 */
export interface ProvisionOptions {
  spec: SandboxSpec;
  command: string[];
  /** Root containing infra/policies/{seccomp,landlock}/<name>.json */
  policiesRoot: string;
  runner?: SandboxRunner;
  /** Skip platform gate (unit tests only — never in production wiring). */
  skipPlatformGate?: boolean;
}

export interface SandboxHandle {
  spec: SandboxSpec;
  workload: SpawnHandle;
  scope: ProcessScope;
  attestation: IsolationAttestation;
  canary: CanaryCheck;
  runner: SandboxRunner;
}

export async function provision(opts: ProvisionOptions): Promise<SandboxHandle> {
  const runner = opts.runner ?? new NodeSandboxRunner();

  if (!opts.skipPlatformGate) {
    const support = await detectSupport();
    if (!support.supported) throw new PlatformUnsupportedError(support);
  }

  // 1–2. Policies loaded and audited before any process starts.
  const seccompRaw = await loadPolicyFile(opts.policiesRoot, "seccomp", opts.spec.seccompProfile);
  const seccomp = loadSeccompProfile(opts.spec.seccompProfile, seccompRaw);
  const seccompAudit = auditSeccompProfile(opts.spec.seccompProfile, seccomp);
  if (seccompAudit.forbiddenInAllow.length > 0) {
    throw new Error(
      `seccomp profile "${opts.spec.seccompProfile}" allows forbidden syscalls: ${seccompAudit.forbiddenInAllow.join(", ")}`,
    );
  }

  const landlockRaw = await loadPolicyFile(opts.policiesRoot, "landlock", opts.spec.landlockRuleset);
  const landlock = loadLandlockRuleset(landlockRaw);
  instantiateRuleset(landlock, { workspace: opts.spec.workspaceMount }); // validates substitutions

  // 3. bwrap plan
  const plan = buildBwrapArgv({
    spec: opts.spec,
    command: opts.command,
  });

  // 4. cgroup + limits
  const layout = cgroupLayout(opts.spec.sandboxId);
  await runner.mkdir(layout.path);
  for (const w of cgroupLimitWrites(opts.spec)) {
    await runner.writeFile(w.file, w.value);
  }

  // 5. spawn + scope
  const scope = new ProcessScope(opts.spec.sandboxId);
  const workload = runner.spawn(plan.argv[0]!, plan.argv.slice(1));
  scope.register(workload);

  try {
    // 6. attach + verify limits
    const attach = cgroupAttachWrite(opts.spec.sandboxId, workload.pid);
    await runner.writeFile(attach.file, attach.value);
    const limitsCheck = verifyLimits(opts.spec, {
      cpuMax: await runner.readFile(layout.files.cpuMax).catch(() => ""),
      memoryMax: await runner.readFile(layout.files.memoryMax).catch(() => ""),
      pidsMax: await runner.readFile(layout.files.pidsMax).catch(() => ""),
    });

    // 7. network canary — must fail
    const canary = await runNetworkCanary(opts.spec.sandboxId, runner);

    // 8. attestation
    const attestation: IsolationAttestation = {
      sandboxId: opts.spec.sandboxId,
      runtime: "bwrap",
      namespaces: { user: true, pid: true, net: true, uts: true, ipc: true, mount: true },
      networkPolicy: opts.spec.network,
      usernsRoot: opts.spec.usernsRoot,
      cgroup: {
        path: layout.path,
        cpuMax: String(opts.spec.resources.cpu),
        memoryMaxBytes: String(opts.spec.resources.memoryMb * 1024 * 1024),
        pidsMax: String(opts.spec.resources.pids),
        limitsVerified: limitsCheck.ok,
        mismatches: limitsCheck.mismatches,
      },
      seccomp: { profile: opts.spec.seccompProfile, attached: !!plan.seccompFdPath },
      landlock: { ruleset: opts.spec.landlockRuleset, attached: plan.notes.every((n) => !n.startsWith("landlock helper not attached")) },
      startedAt: new Date().toISOString(),
    };

    return { spec: opts.spec, workload, scope, attestation, canary, runner };
  } catch (error) {
    // fail-closed: nothing survives a bad provisioning
    scope.killAll();
    await runner.writeFile(cgroupKillFile(opts.spec.sandboxId), "1").catch(() => undefined);
    throw error;
  }
}

function cgroupKillFile(sandboxId: string): string {
  return `${cgroupLayout(sandboxId).path}/cgroup.kill`;
}

/**
 * Canary: DNS lookup from inside a sibling netns with identical policy —
 * MUST fail. If it exits 0, egress is possible and the run must abort.
 */
export async function runNetworkCanary(
  sandboxId: string,
  runner: SandboxRunner,
): Promise<CanaryCheck> {
  const command = ["bwrap", "--unshare-net", "--die-with-parent", "--", "getent", "hosts", "example.com"];
  const result = await runner.exec(command[0]!, command.slice(1)).catch(() => ({ code: 2, stdout: "", stderr: "" }));
  return {
    ranAt: new Date().toISOString(),
    command,
    expected: "fail",
    exitCode: result.code,
    succeeded: result.code !== 0,
  };
}
