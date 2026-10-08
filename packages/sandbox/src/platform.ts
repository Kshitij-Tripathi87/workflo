import { execFile } from "node:child_process";
import { access, constants } from "node:fs/promises";
import os from "node:os";

/**
 * Platform capability detection. The sandbox is Linux-only; everything else
 * must produce a clear PlatformUnsupported result — never a fake sandbox.
 */

export interface SandboxSupport {
  supported: boolean;
  reasons: string[];
  checks: {
    linux: boolean;
    bwrap: boolean;
    cgroupV2: boolean;
    unprivilegedUserns: boolean;
  };
}

export class PlatformUnsupportedError extends Error {
  constructor(public readonly support: SandboxSupport) {
    super(
      `workflo sandbox requires Linux (bwrap + cgroups v2 + user namespaces). ` +
      `Missing: ${support.reasons.join(", ") || "unknown"}`,
    );
    this.name = "PlatformUnsupportedError";
  }
}

export async function detectSupport(options?: {
  exec?: (cmd: string, args: string[]) => Promise<{ code: number; stdout: string }>;
  exists?: (path: string) => Promise<boolean>;
  platform?: NodeJS.Platform;
}): Promise<SandboxSupport> {
  const platform = options?.platform ?? os.platform();

  const defaultExec = (cmd: string, args: string[]) =>
    new Promise<{ code: number; stdout: string }>((resolve) => {
      execFile(cmd, args, { timeout: 5000 }, (error, stdout) => {
        resolve({ code: error ? 1 : 0, stdout: String(stdout ?? "") });
      });
    });
  const defaultExists = async (p: string) => {
    try {
      await access(p, constants.R_OK);
      return true;
    } catch {
      return false;
    }
  };

  const exec = options?.exec ?? defaultExec;
  const exists = options?.exists ?? defaultExists;

  const isLinux = platform === "linux";
  const checks = {
    linux: isLinux,
    bwrap: false,
    cgroupV2: false,
    unprivilegedUserns: false,
  };
  const reasons: string[] = [];

  if (!isLinux) {
    reasons.push(`platform is ${platform}, sandbox requires linux`);
    return { supported: false, reasons, checks };
  }

  const bwrapCheck = await exec("bwrap", ["--version"]);
  checks.bwrap = bwrapCheck.code === 0;
  if (!checks.bwrap) reasons.push("bubblewrap (bwrap) not found on PATH");

  checks.cgroupV2 = await exists(`${CGROUP_SENTINEL}`);
  if (!checks.cgroupV2) reasons.push("cgroups v2 not mounted at /sys/fs/cgroup/cgroup.controllers");

  const usernsCheck = await exec("sh", [
    "-c",
    "cat /proc/sys/kernel/unprivileged_userns_clone 2>/dev/null || echo 1",
  ]);
  checks.unprivilegedUserns = usernsCheck.stdout.trim() !== "0";
  if (!checks.unprivilegedUserns) reasons.push("unprivileged user namespaces disabled");

  return { supported: reasons.length === 0, reasons, checks };
}

const CGROUP_SENTINEL = "/sys/fs/cgroup/cgroup.controllers";
