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

export interface ProcEntry {
  pid: number;
  ppid: number;
}

/**
 * listProcesses — snapshot of (pid, ppid) on the host.
 *
 * Returns [] on win32 (taskkill /T already walks the tree) or when ps is
 * unavailable; callers then fall back to the registered-pid answer.
 */
export async function listProcesses(runner: SandboxRunner): Promise<ProcEntry[]> {
  if (process.platform === "win32") return [];
  const res = await runner
    .exec("ps", ["-A", "-o", "pid=", "-o", "ppid="])
    .catch(() => ({ code: 1, stdout: "", stderr: "" }));
  if (res.code !== 0) return [];
  const entries: ProcEntry[] = [];
  for (const line of res.stdout.split("\n")) {
    const fields = line.trim().split(/\s+/);
    if (fields.length < 2) continue;
    const pid = Number(fields[0]);
    const ppid = Number(fields[1]);
    if (Number.isInteger(pid) && Number.isInteger(ppid) && pid > 0) {
      entries.push({ pid, ppid });
    }
  }
  return entries;
}

/**
 * collectDescendants — transitive children of `roots`.
 *
 * A child that detaches (setsid / detached spawn) leaves its parent's process
 * group, so a group kill misses it; and once its parent exits it is
 * reparented to init, so it can no longer be found by walking ppid. Callers
 * must snapshot the tree BEFORE signalling anything.
 */
export async function collectDescendants(
  runner: SandboxRunner,
  roots: number[],
): Promise<number[]> {
  const procs = await listProcesses(runner);
  if (procs.length === 0) return [];

  const childrenOf = new Map<number, number[]>();
  for (const { pid, ppid } of procs) {
    const siblings = childrenOf.get(ppid);
    if (siblings) siblings.push(pid);
    else childrenOf.set(ppid, [pid]);
  }

  const seen = new Set<number>(roots);
  const descendants: number[] = [];
  const queue = [...roots];
  while (queue.length > 0) {
    const pid = queue.shift() as number;
    for (const child of childrenOf.get(pid) ?? []) {
      if (seen.has(child)) continue;
      seen.add(child);
      descendants.push(child);
      queue.push(child);
    }
  }
  return descendants;
}

/** Kill a single pid (no process-group semantics). */
export async function killPid(runner: SandboxRunner, pid: number): Promise<void> {
  if (process.platform === "win32") return killTree(runner, pid);
  await runner
    .exec("sh", ["-c", `kill -KILL ${pid} 2>/dev/null || true`])
    .catch(() => undefined);
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
