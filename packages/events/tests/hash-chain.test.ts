import { describe, expect, it } from "vitest";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import {
  GENESIS_HASH,
  canonicalJson,
  computeEventHash,
  buildBoundRecord,
  CHAIN_VERSION,
} from "../src/hash-chain";

const baseInput = {
  eventId: "550e8400-e29b-41d4-a716-446655440000",
  organizationId: "550e8400-e29b-41d4-a716-446655440001",
  projectId: "550e8400-e29b-41d4-a716-446655440002",
  runId: "550e8400-e29b-41d4-a716-446655440003",
  runSeq: 7,
  kind: "OBSERVATION",
  role: "EXPLORER",
  status: "info",
  parentEventId: null,
  requestId: null,
  action: "http_request",
  summary: "observed 401",
  rationale: null,
  observationSummary: null,
  policyId: null,
  payload: { status: 401, path: "/api/admin" },
  occurredAt: new Date("2026-09-30T12:00:00.000Z"),
  prevHash: GENESIS_HASH,
};

describe("canonicalJson", () => {
  it("is stable across key insertion order", () => {
    const a = canonicalJson({ b: 1, a: { d: 4, c: 3 }, z: [2, 1] });
    const b = canonicalJson({ z: [2, 1], a: { c: 3, d: 4 }, b: 1 });
    expect(a).toBe(b);
    expect(a).toBe('{"a":{"c":3,"d":4},"b":1,"z":[2,1]}');
  });

  it("normalizes dates to ISO-8601 ms", () => {
    expect(canonicalJson(new Date("2026-09-30T12:00:00.250Z"))).toBe(
      '"2026-09-30T12:00:00.250Z"',
    );
  });

  it("rejects non-finite numbers, undefined, functions, bigint", () => {
    expect(() => canonicalJson(Number.NaN)).toThrow();
    expect(() => canonicalJson(Infinity)).toThrow();
    expect(() => canonicalJson({ a: undefined })).not.toThrow(); // keys with undefined are dropped
    expect(() => canonicalJson(undefined)).toThrow();
    expect(() => canonicalJson(() => 1)).toThrow();
    expect(() => canonicalJson(1n)).toThrow();
  });

  it("escapes strings exactly like JSON", () => {
    expect(canonicalJson('a"b\\c\n')).toBe('"a\\"b\\\\c\\n"');
  });
});

describe("genesis anchor", () => {
  it("matches sha256('workflo:evidence:genesis:v1')", () => {
    expect(
      createHash("sha256").update("workflo:evidence:genesis:v1").digest("hex"),
    ).toBe(GENESIS_HASH);
  });

  it("matches the constant hardcoded in migration 0002", async () => {
    const migration = await readFile(
      path.resolve(
        path.dirname(fileURLToPath(import.meta.url)),
        "..",
        "..",
        "db",
        "migrations",
        "0002_evidence_chain.sql",
      ),
      "utf8",
    );
    expect(migration).toContain(GENESIS_HASH);
  });
});

describe("hash binding", () => {
  it("binds metadata: any single-field mutation changes the hash", () => {
    const original = computeEventHash(baseInput);

    const mutations: Array<[string, Partial<typeof baseInput>]> = [
      ["eventId", { eventId: "550e8400-e29b-41d4-a716-446655440099" }],
      ["organizationId", { organizationId: "550e8400-e29b-41d4-a716-446655440099" }],
      ["projectId", { projectId: "550e8400-e29b-41d4-a716-446655440099" }],
      ["runId", { runId: "550e8400-e29b-41d4-a716-446655440099" }],
      ["runSeq", { runSeq: 8 }],
      ["kind", { kind: "TOOL_DENIED" }],
      ["role", { role: "JUDGE" }],
      ["status", { status: "denied" }],
      ["summary", { summary: "observed 200" }],
      ["payload", { payload: { status: 200, path: "/api/admin" } }],
      ["occurredAt", { occurredAt: new Date("2026-09-30T12:00:01.000Z") }],
      ["prevHash", { prevHash: "0".repeat(64) }],
    ];

    for (const [field, patch] of mutations) {
      const mutated = computeEventHash({ ...baseInput, ...patch });
      expect(mutated, `mutation of ${field} must change the hash`).not.toBe(original);
    }
  });

  it("hash is deterministic across calls", () => {
    expect(computeEventHash(baseInput)).toBe(computeEventHash(baseInput));
    expect(buildBoundRecord(baseInput).v).toBe(CHAIN_VERSION);
  });
});
