/**
 * Health probe: polls a real HTTP endpoint until READY or deadlined.
 * "Process exists" is never a readiness signal — only a 2xx is.
 */

export interface HealthAttempt {
  at: string;
  target: string;
  latencyMs: number;
  ok: boolean;
  detail: string;
}

export interface HealthResult {
  state: "READY" | "READY_TIMEOUT" | "CRASHED";
  attempts: HealthAttempt[];
}

export interface HealthOptions {
  url: string;
  timeoutMs: number;
  intervalMs?: number;
  /** Set externally to short-circuit polling when the app process dies. */
  isAlive?: () => boolean;
  fetchFn?: typeof fetch;
}

export async function probeHealth(opts: HealthOptions): Promise<HealthResult> {
  const started = Date.now();
  const interval = opts.intervalMs ?? 250;
  const fetchFn = opts.fetchFn ?? fetch;
  const attempts: HealthAttempt[] = [];

  while (Date.now() - started < opts.timeoutMs) {
    if (opts.isAlive && !opts.isAlive()) {
      return { state: "CRASHED", attempts };
    }
    const attemptStart = Date.now();
    let ok = false;
    let detail = "";
    try {
      const res = await fetchFn(opts.url, { signal: AbortSignal.timeout(4000) });
      ok = res.ok;
      detail = `HTTP ${res.status}`;
    } catch (error) {
      detail = error instanceof Error ? error.name : "connection error";
    }
    attempts.push({
      at: new Date().toISOString(),
      target: opts.url,
      latencyMs: Date.now() - attemptStart,
      ok,
      detail,
    });
    if (ok) return { state: "READY", attempts };
    await new Promise((r) => setTimeout(r, interval));
  }
  return { state: "READY_TIMEOUT", attempts };
}
