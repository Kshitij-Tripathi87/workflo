import { describe, expect, it } from "vitest";
import { ReceiptV4Schema } from "../src/receipt";

const validReceipt = {
  receipt_version: 4,
  run_id: "550e8400-e29b-41d4-a716-446655440001",
  sandbox_id: "sbx-01",
  issued_at: new Date().toISOString(),
  repository: {
    provider: "github",
    url: "https://github.com/org/repo",
    ref: "main",
    commit_sha: "abc123"
  },
  mission: "Verify checkout flow.",
  run_report: {
    lifecycle: "COMPLETED",
    tests: { passed: 10, failed: 0 },
    findings: []
  },
  agent_activity: [],
  evidence: { ledger_root: "sha256:abc" },
  sandbox: {
    isolation_attestation: { netns: true },
    teardown_proof: { verified: true },
    canary_check: { blocked: true }
  },
  inference_provenance: {
    model_id: "qwen3-4b-4bit",
    request_ids: ["req-1"],
    input_tokens: 100,
    output_tokens: 50,
    inference_seconds: 1.2,
    source_code_included: false
  },
  transparency: {
    log_id: "log-01",
    checkpoint: 1,
    merkle_root: "sha256:root",
    inclusion_proof: ["sha256:leaf"]
  }
};

describe("ReceiptV4Schema", () => {
  it("accepts a valid receipt", () => {
    const parsed = ReceiptV4Schema.safeParse(validReceipt);
    expect(parsed.success).toBe(true);
  });

  it("rejects wrong receipt_version", () => {
    const parsed = ReceiptV4Schema.safeParse({ ...validReceipt, receipt_version: 3 });
    expect(parsed.success).toBe(false);
  });

  it("rejects non-github provider", () => {
    const parsed = ReceiptV4Schema.safeParse({
      ...validReceipt,
      repository: { ...validReceipt.repository, provider: "gitlab" }
    });
    expect(parsed.success).toBe(false);
  });

  it("rejects invalid repository url", () => {
    const parsed = ReceiptV4Schema.safeParse({
      ...validReceipt,
      repository: { ...validReceipt.repository, url: "not-a-url" }
    });
    expect(parsed.success).toBe(false);
  });

  it("rejects negative tokens in inference", () => {
    const parsed = ReceiptV4Schema.safeParse({
      ...validReceipt,
      inference_provenance: { ...validReceipt.inference_provenance, input_tokens: -1 }
    });
    expect(parsed.success).toBe(false);
  });

  it("rejects negative checkpoint", () => {
    const parsed = ReceiptV4Schema.safeParse({
      ...validReceipt,
      transparency: { ...validReceipt.transparency, checkpoint: -1 }
    });
    expect(parsed.success).toBe(false);
  });

  it("rejects tampered mission (extra field)", () => {
    const parsed = ReceiptV4Schema.safeParse({
      ...validReceipt,
      tampered: true
    });
    expect(parsed.success).toBe(false);
  });

  it("rejects missing transparency", () => {
    const { transparency, ...rest } = validReceipt;
    const parsed = ReceiptV4Schema.safeParse(rest);
    expect(parsed.success).toBe(false);
  });

  it("rejects missing sandbox proof field keys", () => {
    const { isolation_attestation, ...sandboxRest } = validReceipt.sandbox;
    const parsed = ReceiptV4Schema.safeParse({
      ...validReceipt,
      sandbox: sandboxRest
    });
    expect(parsed.success).toBe(false);
  });
});
