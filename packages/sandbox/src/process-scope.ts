import type { SpawnHandle } from "./runner";

/**
 * Process scope — every spawned workload/process tied to a sandbox id is
 * registered here. teardown() can then prove that nothing outlived the run.
 */
export class ProcessScope {
  private readonly handles = new Map<number, SpawnHandle>();

  constructor(readonly sandboxId: string) {}

  register(handle: SpawnHandle): void {
    if (handle.pid > 0) this.handles.set(handle.pid, handle);
  }

  list(): number[] {
    return [...this.handles.keys()];
  }

  killAll(signal: NodeJS.Signals = "SIGKILL"): void {
    for (const handle of this.handles.values()) {
      try {
        handle.kill(signal);
      } catch {
        // already exited
      }
    }
  }

  async waitAll(timeoutMs: number): Promise<{ exited: number[]; timedOut: number[] }> {
    const exiting = [...this.handles.entries()].map(async ([pid, handle]) => {
      const result = await Promise.race([
        handle.wait().then(() => true).catch(() => true),
        new Promise<false>((resolve) => setTimeout(() => resolve(false), timeoutMs)),
      ]);
      return { pid, exited: result };
    });
    const results = await Promise.all(exiting);
    return {
      exited: results.filter((r) => r.exited).map((r) => r.pid),
      timedOut: results.filter((r) => !r.exited).map((r) => r.pid),
    };
  }

  unregister(pid: number): void {
    this.handles.delete(pid);
  }

  get size(): number {
    return this.handles.size;
  }
}
