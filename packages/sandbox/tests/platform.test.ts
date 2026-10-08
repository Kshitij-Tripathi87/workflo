import { describe, expect, it } from "vitest";
import { detectSupport } from "../src/platform";

describe("platform capability detection", () => {
  it("non-Linux is unsupported with explicit reasons", async () => {
    const support = await detectSupport({ platform: "win32" });
    expect(support.supported).toBe(false);
    expect(support.checks.linux).toBe(false);
    expect(support.reasons.join(" ")).toContain("linux");
  });

  it("linux + bwrap + cgroup v2 + userns → supported", async () => {
    const support = await detectSupport({
      platform: "linux",
      exec: async (cmd, args) =>
        cmd === "bwrap" ? { code: 0, stdout: "bubblewrap 0.9.0" }
          : args[0] === "-c" ? { code: 0, stdout: "1" }
          : { code: 1, stdout: "" },
      exists: async (p) => p === "/sys/fs/cgroup/cgroup.controllers",
    });
    expect(support.supported).toBe(true);
    expect(support.reasons).toEqual([]);
  });

  it("missing bwrap → unsupported", async () => {
    const support = await detectSupport({
      platform: "linux",
      exec: async () => ({ code: 1, stdout: "" }),
      exists: async () => true,
    });
    expect(support.supported).toBe(false);
    expect(support.reasons.join(" ")).toContain("bwrap");
  });

  it("unprivileged userns disabled → unsupported", async () => {
    const support = await detectSupport({
      platform: "linux",
      exec: async (cmd, args) =>
        cmd === "bwrap" ? { code: 0, stdout: "v" }
          : args[0] === "-c" ? { code: 0, stdout: "0" }
          : { code: 1, stdout: "" },
      exists: async () => true,
    });
    expect(support.supported).toBe(false);
    expect(support.reasons.join(" ")).toContain("user namespaces");
  });
});

describe("linux integration gate (skipped off-Linux; runs in CI)", () => {
  const isLinux = process.platform === "linux";

  it.skipIf(!isLinux)("real bwrap canary: egress probe fails inside --unshare-net", async () => {
    const support = await detectSupport();
    expect(support.supported).toBe(true);
    // The actual canary: getent without a network namespace must not resolve.
    const { execFile } = await import("node:child_process");
    const code: number = await new Promise((resolve) => {
      execFile(
        "bwrap",
        ["--unshare-net", "--die-with-parent", "--", "getent", "hosts", "example.com"],
        (err) => resolve(err ? 1 : 0),
      );
    });
    expect(code).not.toBe(0);
  });
});
