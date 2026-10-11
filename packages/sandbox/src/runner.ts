import { execFile, spawn, type ChildProcess } from "node:child_process";

/**
 * Execution seam: all OS interaction flows through SandboxRunner.
 * Tests inject fakes; production uses NODE—but only on Linux.
 */

export interface ExecResult {
  code: number;
  stdout: string;
  stderr: string;
  signal?: NodeJS.Signals | null;
}

export interface SpawnHandle {
  pid: number;
  process: ChildProcess;
  wait: () => Promise<ExecResult>;
  kill: (signal?: NodeJS.Signals) => boolean;
}

export interface SandboxRunner {
  exec(cmd: string, args: string[], opts?: { input?: string; timeoutMs?: number }): Promise<ExecResult>;
  spawn(cmd: string, args: string[], opts?: { env?: NodeJS.ProcessEnv; cwd?: string }): SpawnHandle;
  writeFile(path: string, content: string): Promise<void>;
  readFile(path: string): Promise<string>;
  exists(path: string): Promise<boolean>;
  removeTree(path: string): Promise<void>;
  mkdir(path: string): Promise<void>;
}

export class NodeSandboxRunner implements SandboxRunner {
  exec(cmd: string, args: string[], opts?: { input?: string; timeoutMs?: number }): Promise<ExecResult> {
    return new Promise((resolve, reject) => {
      const child = execFile(
        cmd,
        args,
        { timeout: opts?.timeoutMs ?? 30_000, maxBuffer: 8 * 1024 * 1024 },
        (error, stdout, stderr) => {
          const err = error as (Error & { code?: number | string; signal?: NodeJS.Signals }) | null;
          resolve({
            code: typeof err?.code === "number" ? err.code : err ? 1 : 0,
            stdout: String(stdout),
            stderr: String(stderr),
            signal: err?.signal ?? null,
          });
        },
      );
      if (opts?.input !== undefined && child.stdin) {
        child.stdin.write(opts.input);
        child.stdin.end();
      }
      child.on("error", reject);
    });
  }

  spawn(cmd: string, args: string[], opts?: { env?: NodeJS.ProcessEnv; cwd?: string }): SpawnHandle {
    const child = spawn(cmd, args, {
      stdio: ["ignore", "pipe", "pipe"],
      env: opts?.env,
      cwd: opts?.cwd,
    });
    const stdoutChunks: Buffer[] = [];
    const stderrChunks: Buffer[] = [];
    child.stdout?.on("data", (c: Buffer) => stdoutChunks.push(c));
    child.stderr?.on("data", (c: Buffer) => stderrChunks.push(c));

    const wait = () =>
      new Promise<ExecResult>((resolve, reject) => {
        child.on("error", reject);
        child.on("exit", (code, signal) => {
          resolve({
            code: code ?? -1,
            stdout: Buffer.concat(stdoutChunks).toString("utf8"),
            stderr: Buffer.concat(stderrChunks).toString("utf8"),
            signal,
          });
        });
      });

    return {
      pid: child.pid ?? -1,
      process: child,
      wait,
      kill: (signal = "SIGKILL") => child.kill(signal),
    };
  }

  async writeFile(path: string, content: string): Promise<void> {
    const { writeFile } = await import("node:fs/promises");
    await writeFile(path, content, "utf8");
  }

  async readFile(path: string): Promise<string> {
    const { readFile } = await import("node:fs/promises");
    return readFile(path, "utf8");
  }

  async exists(path: string): Promise<boolean> {
    const { access } = await import("node:fs/promises");
    try {
      await access(path);
      return true;
    } catch {
      return false;
    }
  }

  async removeTree(path: string): Promise<void> {
    const { rm } = await import("node:fs/promises");
    await rm(path, { recursive: true, force: true });
  }

  async mkdir(path: string): Promise<void> {
    const { mkdir } = await import("node:fs/promises");
    await mkdir(path, { recursive: true });
  }
}
