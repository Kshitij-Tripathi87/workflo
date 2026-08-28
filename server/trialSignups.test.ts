import { describe, expect, it } from "vitest";
import { TrialSignupInputError, normalizeTrialEmail, persistTrialSignup, requireTrialConsent } from "./trialSignups";

describe("trial email validation", () => {
  it("normalizes an email before a trial signup is persisted", () => {
    expect(normalizeTrialEmail("  TEAM@WORKFLO.TEST ")).toBe("team@workflo.test");
  });

  it("rejects missing and malformed email addresses", () => {
    expect(() => normalizeTrialEmail("not-an-email")).toThrow(TrialSignupInputError);
    expect(() => normalizeTrialEmail(undefined)).toThrow(TrialSignupInputError);
  });

  it("persists a normalized email with an idempotent database statement", async () => {
    const execute = async (statement: string, values: unknown[]) => {
      expect(statement).toContain("INSERT INTO trial_signups");
      expect(statement).toContain("ON DUPLICATE KEY UPDATE");
      expect(statement).toContain("consentedAt");
      expect(values).toEqual(["team@workflo.test", "landing_hero"]);
      return [{}] as any;
    };

    await expect(persistTrialSignup("TEAM@WORKFLO.TEST", true, { execute } as any)).resolves.toEqual({ email: "team@workflo.test" });
  });

  it("requires explicit consent before an email can be stored", () => {
    expect(() => requireTrialConsent(false)).toThrow("Please confirm consent");
  });
});
