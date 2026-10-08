import { z } from "zod";
import type { ExecResult } from "@workflo/sandbox";

/**
 * Result taxonomy — distinct operational facts, never collapsed.
 *   PASSED   command ran, exit 0
 *   FAILED   command ran, non-zero exit (assertion failures)
 *   ERROR    command could not start / infra error
 *   TIMEOUT  exceeded wall clock
 *   NOT_RUN  never attempted (preconditions unmet or command absent)
 */
export const TestOutcomeSchema = z.enum([
  "PASSED",
  "FAILED",
  "ERROR",
  "TIMEOUT",
  "NOT_RUN",
]);
export type TestOutcome = z.infer<typeof TestOutcomeSchema>;

export interface TestRunResult {
  outcome: TestOutcome;
  exitCode: number | null;
  durationMs: number;
  stdoutTail: string;
  stderrTail: string;
}

export function tail(s: string, max = 4000): string {
  return s.length <= max ? s : s.slice(s.length - max);
}

export function classifyResult(opts: {
  spawned: boolean;
  timedOut: boolean;
  result?: ExecResult;
  durationMs: number;
}): TestRunResult {
  if (!opts.spawned) {
    return { outcome: "NOT_RUN", exitCode: null, durationMs: opts.durationMs, stdoutTail: "", stderrTail: "" };
  }
  if (opts.timedOut || opts.result?.signal === "SIGKILL" || opts.result?.signal === "SIGTERM") {
    return {
      outcome: "TIMEOUT",
      exitCode: opts.result?.code ?? null,
      durationMs: opts.durationMs,
      stdoutTail: tail(opts.result?.stdout ?? ""),
      stderrTail: tail(opts.result?.stderr ?? ""),
    };
  }
  const res = opts.result;
  if (!res) return { outcome: "ERROR", exitCode: null, durationMs: opts.durationMs, stdoutTail: "", stderrTail: "" };
  return {
    outcome: res.code === 0 ? "PASSED" : "FAILED",
    exitCode: res.code,
    durationMs: opts.durationMs,
    stdoutTail: tail(res.stdout),
    stderrTail: tail(res.stderr),
  };
}
