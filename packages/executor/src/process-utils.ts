import { execFile } from "node:child_process";
import type { SandboxRunner, SpawnHandle } from "@workflo/sandbox";

/**
 * killTree — platform-aware process-tree kill.
 *   linux: kill the process group (children share pgid)
 *   win32: taskkill /T on the parent includes (non-detached) children
 *
 * Under the real sandbox (Linux + bwrap + pid ns + cgroup.kill), teardown is
 * airtight; killTree is the additional belt for the host runner.
 */
export async function killTree(runner: SandboxRunner, pid: number): Promise<void> {
  if (process.platform === "win32") {
    await runner.exec("taskkill", ["/PID", String(pid), "/T", "/F"]).catch(() => undefined);
    return;
  }
  await runner.exec("sh", ["-c", `kill -KILL -${pid} 2>/dev/null || kill -KILL ${pid} 2>/dev/null || true`]).catch(
    () => undefined,
  );
}

/** Whether a pid is still alive (platform-aware). */
export async function pidAlive(runner: SandboxRunner, pid: number): Promise<boolean> {
  if (process.platform === "win32") {
    const res = await runner
      .exec("tasklist", ["/FI", `PID eq ${pid}`, "/NH"])
      .catch(() => ({ code: 1, stdout: "", stderr: "" }));
    return res.stdout.includes(String(pid));
  }
  const res = await runner.exec("sh", ["-c", `kill -0 ${pid} 2>/dev/null && echo alive || echo dead`]);
  return res.stdout.trim() === "alive";
}

export type { SandboxRunner, SpawnHandle };
