import { describe, expect, it } from "vitest";
import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
import { probeHealth } from "../src/health";
import { classifyResult } from "../src/result";

describe("health probe against a real server", () => {
  it("READY only on 2xx; attempts are recorded", async () => {
    let hits = 0;
    const server = createServer((req, res) => {
      hits += 1;
      if (req.url === "/health" && hits >= 2) {
        res.writeHead(200, { "content-type": "application/json" });
        res.end('{"ok":true}');
      } else {
        res.writeHead(503);
        res.end();
      }
    });
    await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
    const port = (server.address() as AddressInfo).port;

    const result = await probeHealth({
      url: `http://127.0.0.1:${port}/health`,
      timeoutMs: 5000,
      intervalMs: 50,
    });
    await new Promise<void>((r) => server.close(() => r()));

    expect(result.state).toBe("READY");
    expect(result.attempts.length).toBeGreaterThanOrEqual(2);
    expect(result.attempts[0]!.ok).toBe(false);
    expect(result.attempts.at(-1)!.ok).toBe(true);
    expect(result.attempts.at(-1)!.latencyMs).toBeGreaterThanOrEqual(0);
    expect(result.attempts[0]!.target).toContain("/health");
  });

  it("READY_TIMEOUT when nothing listens", async () => {
    const result = await probeHealth({
      url: "http://127.0.0.1:49999/health",
      timeoutMs: 600,
      intervalMs: 100,
    });
    expect(result.state).toBe("READY_TIMEOUT");
    expect(result.attempts.length).toBeGreaterThan(2);
  });

  it("CRASHED short-circuits when isAlive goes false", async () => {
    let alive = true;
    const p = probeHealth({
      url: "http://127.0.0.1:49998/health",
      timeoutMs: 5000,
      intervalMs: 100,
      isAlive: () => alive,
    });
    setTimeout(() => { alive = false; }, 150);
    const result = await p;
    expect(result.state).toBe("CRASHED");
  });
});

describe("result taxonomy", () => {
  it("distinguishes all five outcomes", () => {
    expect(classifyResult({ spawned: false, timedOut: false, durationMs: 0 }).outcome).toBe("NOT_RUN");
    expect(classifyResult({ spawned: true, timedOut: true, durationMs: 100 }).outcome).toBe("TIMEOUT");
    expect(classifyResult({
      spawned: true, timedOut: false, durationMs: 5,
      result: { code: 0, stdout: "ok", stderr: "" },
    }).outcome).toBe("PASSED");
    expect(classifyResult({
      spawned: true, timedOut: false, durationMs: 5,
      result: { code: 1, stdout: "", stderr: "assert failed" },
    }).outcome).toBe("FAILED");
    expect(classifyResult({ spawned: true, timedOut: false, durationMs: 0 }).outcome).toBe("ERROR");
  });

  it("signal kill counts as TIMEOUT (wall-clock kill)", () => {
    expect(classifyResult({
      spawned: true, timedOut: false, durationMs: 10,
      result: { code: -1, stdout: "", stderr: "", signal: "SIGKILL" },
    }).outcome).toBe("TIMEOUT");
  });
});
