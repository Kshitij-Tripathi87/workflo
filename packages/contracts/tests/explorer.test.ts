import { describe, expect, it } from "vitest";
import { ExplorerProposalSchema } from "../src/explorer";

describe("ExplorerProposalSchema", () => {
  it("accepts a valid relative http proposal", () => {
    const parsed = ExplorerProposalSchema.safeParse({
      action: {
        tool: "http_request",
        arguments: {
          method: "GET",
          path: "/api/users"
        }
      },
      rationale: "Probe users endpoint without credentials.",
      expected_signal: "Authentication should be required."
    });

    expect(parsed.success).toBe(true);
  });

  it("rejects absolute URLs", () => {
    const parsed = ExplorerProposalSchema.safeParse({
      action: {
        tool: "http_request",
        arguments: {
          method: "GET",
          path: "https://evil.com/exfil"
        }
      },
      rationale: "This should fail.",
      expected_signal: "Denied by policy."
    });

    expect(parsed.success).toBe(false);
  });

  it("rejects hidden chain-of-thought fields", () => {
    const parsed = ExplorerProposalSchema.safeParse({
      action: {
        tool: "http_request",
        arguments: {
          method: "GET",
          path: "/api/users"
        }
      },
      rationale: "Probe users endpoint.",
      expected_signal: "Should require auth.",
      thought: "I am thinking about bypassing auth..."
    });

    expect(parsed.success).toBe(false);
  });

  it("accepts read_app_logs with valid args", () => {
    const parsed = ExplorerProposalSchema.safeParse({
      action: {
        tool: "read_app_logs",
        arguments: { tail: 100, filter: "error" }
      },
      rationale: "Check recent errors.",
      expected_signal: "No 5xx in last 100 lines."
    });
    expect(parsed.success).toBe(true);
  });

  it("rejects read_app_logs with tail over 500", () => {
    const parsed = ExplorerProposalSchema.safeParse({
      action: {
        tool: "read_app_logs",
        arguments: { tail: 501 }
      },
      rationale: "Too much.",
      expected_signal: "Fail."
    });
    expect(parsed.success).toBe(false);
  });

  it("accepts browser_probe with valid args", () => {
    const parsed = ExplorerProposalSchema.safeParse({
      action: {
        tool: "browser_probe",
        arguments: { action: "click", target: "#submit" }
      },
      rationale: "Submit form.",
      expected_signal: "Form submits."
    });
    expect(parsed.success).toBe(true);
  });

  it("rejects path without leading slash", () => {
    const parsed = ExplorerProposalSchema.safeParse({
      action: {
        tool: "http_request",
        arguments: { method: "GET", path: "api/users" }
      },
      rationale: "Missing slash.",
      expected_signal: "Fail."
    });
    expect(parsed.success).toBe(false);
  });

  it("rejects path with scheme-relative URL", () => {
    const parsed = ExplorerProposalSchema.safeParse({
      action: {
        tool: "http_request",
        arguments: { method: "GET", path: "//evil.com/x" }
      },
      rationale: "Scheme-relative.",
      expected_signal: "Fail."
    });
    expect(parsed.success).toBe(false);
  });

  it("rejects unknown tool name", () => {
    const parsed = ExplorerProposalSchema.safeParse({
      action: {
        tool: "shell_exec",
        arguments: { cmd: "rm -rf /" }
      },
      rationale: "Arbitrary shell.",
      expected_signal: "Denied."
    });
    expect(parsed.success).toBe(false);
  });

  it("rejects missing rationale", () => {
    const parsed = ExplorerProposalSchema.safeParse({
      action: {
        tool: "http_request",
        arguments: { method: "GET", path: "/api/users" }
      },
      expected_signal: "Auth required."
    });
    expect(parsed.success).toBe(false);
  });

  it("rejects missing expected_signal", () => {
    const parsed = ExplorerProposalSchema.safeParse({
      action: {
        tool: "http_request",
        arguments: { method: "GET", path: "/api/users" }
      },
      rationale: "Probe."
    });
    expect(parsed.success).toBe(false);
  });

  it("rejects rationale over 500 chars", () => {
    const parsed = ExplorerProposalSchema.safeParse({
      action: {
        tool: "http_request",
        arguments: { method: "GET", path: "/api/users" }
      },
      rationale: "x".repeat(501),
      expected_signal: "Auth."
    });
    expect(parsed.success).toBe(false);
  });
});
