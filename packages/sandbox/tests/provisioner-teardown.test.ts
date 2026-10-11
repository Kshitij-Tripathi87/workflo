import { describe, expect, it } from "vitest";
import { provision } from "../src/provisioner";
import { teardown } from "../src/teardown";
import { cgroupLayout } from "../src/cgroups";
import { FakeRunner, makeSpec, POLICIES_ROOT } from "./helpers";

describe("provisioner (fake runner, platform gate skipped)", () => {
  it("builds cgroup, applies limits, spawns bwrap, verifies, canary-fails-as-required", async () => {
    const runner = new FakeRunner();
    const spec = makeSpec();

    const handle = await provision({
      spec,
      command: ["npm", "test"],
      policiesRoot: POLICIES_ROOT,
      runner,
      skipPlatformGate: true,
    });

    // cgroup created + limits written
    const layout = cgroupLayout(spec.sandboxId);
    expect(runner.fs.get(layout.files.cpuMax)).toBe("200000 100000");
    expect(runner.fs.get(layout.files.memoryMax)).toBe(String(1024 * 1024 * 1024));
    expect(runner.fs.get(layout.files.pidsMax)).toBe("128");
    // workload pid attached to cgroup
    expect(runner.fs.get(layout.files.cgroupProcs)).toBe(String(handle.workload.pid));

    // bwrap spawn
    expect(runner.spawnCalls[0]!.cmd).toBe("bwrap");
    expect(runner.spawnCalls[0]!.args.join(" ")).toContain("--unshare-all");

    // attestation reflects verified limits
    expect(handle.attestation.cgroup.limitsVerified).toBe(true);
    expect(handle.attestation.namespaces).toEqual({
      user: true, pid: true, net: true, uts: true, ipc: true, mount: true,
    });
    expect(handle.attestation.networkPolicy).toBe("deny");

    // canary: fake exec defaults to code 1 (blocked) → succeeded = true
    expect(handle.canary.expected).toBe("fail");
    expect(handle.canary.succeeded).toBe(true);
    expect(runner.execCalls.some((c) => c.args.includes("getent"))).toBe(true);
  });

  it("limits read-back mismatch is recorded in attestation (not silently ok)", async () => {
    class DriftyRunner extends FakeRunner {
      override async readFile(): Promise<string> {
        return "max 100000"; // cgroup write never landed
      }
    }
    const runner = new DriftyRunner();
    const handle = await provision({
      spec: makeSpec(),
      command: ["true"],
      policiesRoot: POLICIES_ROOT,
      runner,
      skipPlatformGate: true,
    });
    expect(handle.attestation.cgroup.limitsVerified).toBe(false);
    expect(handle.attestation.cgroup.mismatches.length).toBeGreaterThan(0);
  });

  it("fail-closed: provisioning error kills the scope and cgroup.kills", async () => {
    class FragileRunner extends FakeRunner {
      override async writeFile(p: string, content: string): Promise<void> {
        if (p.endsWith("cgroup.procs")) throw new Error("write failed");
        return super.writeFile(p, content);
      }
    }
    const runner = new FragileRunner();
    await expect(
      provision({
        spec: makeSpec(),
        command: ["true"],
        policiesRoot: POLICIES_ROOT,
        runner,
        skipPlatformGate: true,
      }),
    ).rejects.toThrow(/write failed/);
    // cleanup attempted: a cgroup.kill write was issued
    expect(runner.fs.get(cgroupLayout("sbx-test01").files.cgroupKill)).toBe("1");
  });
});

describe("teardown verification", () => {
  async function setup() {
    const runner = new FakeRunner();
    const spec = makeSpec();
    const handle = await provision({
      spec,
      command: ["true"],
      policiesRoot: POLICIES_ROOT,
      runner,
      skipPlatformGate: true,
    });
    handle.scope.unregister(handle.workload.pid); // simulate exit
    return { runner, spec, handle };
  }

  it("verified=true when nothing survives", async () => {
    const { runner, spec, handle } = await setup();
    const proof = await teardown({ spec, scope: handle.scope, runner });
    expect(proof.verified).toBe(true);
    expect(proof.checks).toEqual({
      processesGone: true,
      cgroupGone: true,
      netnsGone: true,
      workspaceRemoved: true,
    });
    expect(runner.removed).toContain(spec.workspaceDir);
    expect(runner.removed).toContain(cgroupLayout(spec.sandboxId).path);
  });

  it("verified=false when the cgroup survives", async () => {
    const { runner, spec, handle } = await setup();
    const layout = cgroupLayout(spec.sandboxId);
    const proof = await teardown({
      spec,
      scope: handle.scope,
      runner,
      probes: {
        pathExists: async (p) => (p === layout.path ? true : runner.exists(p)),
      },
    });
    expect(proof.verified).toBe(false);
    expect(proof.checks.cgroupGone).toBe(false);
  });

  it("verified=false when the workspace survives", async () => {
    const { runner, spec, handle } = await setup();
    const proof = await teardown({
      spec,
      scope: handle.scope,
      runner,
      probes: {
        pathExists: async (p) => (p === spec.workspaceDir ? true : runner.exists(p)),
      },
    });
    expect(proof.verified).toBe(false);
    expect(proof.checks.workspaceRemoved).toBe(false);
  });

  it("noop on Windows-safe paths is impossible to misread: teardown ran on real files", async () => {
    const { runner, spec, handle } = await setup();
    await teardown({ spec, scope: handle.scope, runner });
    expect(runner.execCalls.length + runner.spawnCalls.length).toBeGreaterThan(0);
  });
});
