import { describe, expect, it } from "vitest";
import { GatewayResultSchema } from "../src/tool-gateway";

describe("GatewayResultSchema", () => {
  it("accepts authorized decision", () => {
    const parsed = GatewayResultSchema.safeParse({
      requestId: "550e8400-e29b-41d4-a716-446655440000",
      tool: "http_request",
      decision: "authorized",
      occurredAt: new Date().toISOString()
    });
    expect(parsed.success).toBe(true);
  });

  it("accepts denied decision with reason and policyId", () => {
    const parsed = GatewayResultSchema.safeParse({
      requestId: "550e8400-e29b-41d4-a716-446655440000",
      tool: "http_request",
      decision: "denied",
      reason: "External URL not in allowlist.",
      policyId: "net-egress-deny",
      occurredAt: new Date().toISOString()
    });
    expect(parsed.success).toBe(true);
  });

  it("is structurally representable for denied events", () => {
    const denied = GatewayResultSchema.parse({
      requestId: "550e8400-e29b-41d4-a716-446655440000",
      tool: "read_app_logs",
      decision: "denied",
      reason: "Log access outside scope.",
      occurredAt: new Date().toISOString()
    });
    expect(denied.decision).toBe("denied");
    expect(typeof denied.reason).toBe("string");
  });

  it("rejects invalid decision value", () => {
    const parsed = GatewayResultSchema.safeParse({
      requestId: "550e8400-e29b-41d4-a716-446655440000",
      tool: "http_request",
      decision: "maybe",
      occurredAt: new Date().toISOString()
    });
    expect(parsed.success).toBe(false);
  });

  it("rejects reason over 500 chars", () => {
    const parsed = GatewayResultSchema.safeParse({
      requestId: "550e8400-e29b-41d4-a716-446655440000",
      tool: "http_request",
      decision: "denied",
      reason: "x".repeat(501),
      occurredAt: new Date().toISOString()
    });
    expect(parsed.success).toBe(false);
  });

  it("rejects extra fields (strict)", () => {
    const parsed = GatewayResultSchema.safeParse({
      requestId: "550e8400-e29b-41d4-a716-446655440000",
      tool: "http_request",
      decision: "authorized",
      internalNote: "bypass for admin",
      occurredAt: new Date().toISOString()
    });
    expect(parsed.success).toBe(false);
  });
});
