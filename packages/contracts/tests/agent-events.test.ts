import { describe, expect, it } from "vitest";
import { PublicAgentEventSchema } from "../src/agent-events";

const baseEvent = {
  eventId: "550e8400-e29b-41d4-a716-446655440000",
  runId: "550e8400-e29b-41d4-a716-446655440001",
  parentEventId: null,
  role: "EXPLORER",
  kind: "OBSERVATION",
  status: "info",
  summary: "Observed response status 200.",
  occurredAt: new Date().toISOString()
};

describe("PublicAgentEventSchema", () => {
  it("accepts a valid event", () => {
    const parsed = PublicAgentEventSchema.safeParse(baseEvent);
    expect(parsed.success).toBe(true);
  });

  it("accepts denied status with action and policyId", () => {
    const parsed = PublicAgentEventSchema.safeParse({
      ...baseEvent,
      kind: "TOOL_DENIED",
      status: "denied",
      action: "http_request",
      policyId: "net-egress-deny",
      summary: "Denied external URL."
    });
    expect(parsed.success).toBe(true);
  });

  it("accepts optional fields when present", () => {
    const parsed = PublicAgentEventSchema.safeParse({
      ...baseEvent,
      action: "http_request",
      rationale: "Check endpoint.",
      observationSummary: "Got 401.",
      policyId: "auth-required",
      requestId: "550e8400-e29b-41d4-a716-446655440002"
    });
    expect(parsed.success).toBe(true);
  });

  it("rejects hidden CoT field 'thought'", () => {
    const parsed = PublicAgentEventSchema.safeParse({
      ...baseEvent,
      thought: "I should try to escalate privileges..."
    });
    expect(parsed.success).toBe(false);
  });

  it("rejects hidden CoT field 'reasoning'", () => {
    const parsed = PublicAgentEventSchema.safeParse({
      ...baseEvent,
      reasoning: "Step 1: probe. Step 2: exploit."
    });
    expect(parsed.success).toBe(false);
  });

  it("rejects hidden CoT field 'internal'", () => {
    const parsed = PublicAgentEventSchema.safeParse({
      ...baseEvent,
      internal: { chain: ["a", "b"] }
    });
    expect(parsed.success).toBe(false);
  });

  it("rejects summary over 500 chars", () => {
    const parsed = PublicAgentEventSchema.safeParse({
      ...baseEvent,
      summary: "x".repeat(501)
    });
    expect(parsed.success).toBe(false);
  });

  it("rejects observationSummary over 2000 chars", () => {
    const parsed = PublicAgentEventSchema.safeParse({
      ...baseEvent,
      observationSummary: "x".repeat(2001)
    });
    expect(parsed.success).toBe(false);
  });

  it("rejects action over 200 chars", () => {
    const parsed = PublicAgentEventSchema.safeParse({
      ...baseEvent,
      action: "x".repeat(201)
    });
    expect(parsed.success).toBe(false);
  });

  it("rejects invalid role", () => {
    const parsed = PublicAgentEventSchema.safeParse({
      ...baseEvent,
      role: "SUPERUSER"
    });
    expect(parsed.success).toBe(false);
  });

  it("rejects invalid kind", () => {
    const parsed = PublicAgentEventSchema.safeParse({
      ...baseEvent,
      kind: "SECRET_EXFILTRATED"
    });
    expect(parsed.success).toBe(false);
  });

  it("rejects non-uuid eventId", () => {
    const parsed = PublicAgentEventSchema.safeParse({
      ...baseEvent,
      eventId: "not-a-uuid"
    });
    expect(parsed.success).toBe(false);
  });

  it("accepts parentEventId as uuid for causal chains", () => {
    const parsed = PublicAgentEventSchema.safeParse({
      ...baseEvent,
      parentEventId: "550e8400-e29b-41d4-a716-446655440003"
    });
    expect(parsed.success).toBe(true);
  });
});
