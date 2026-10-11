import { describe, expect, it } from "vitest";
import { buildSandboxEnv, isAllowedEnvKey } from "../src/env-policy";

describe("sandbox environment policy", () => {
  it("allows base keys and WORKFLO_*", () => {
    expect(isAllowedEnvKey("PATH")).toBe(true);
    expect(isAllowedEnvKey("HOME")).toBe(true);
    expect(isAllowedEnvKey("WORKFLO_RUN_ID")).toBe(true);
    expect(isAllowedEnvKey("CI")).toBe(true);
  });

  it("denies cloud/secret credentials", () => {
    for (const k of [
      "AWS_SECRET_ACCESS_KEY", "AWS_ACCESS_KEY_ID", "GITHUB_TOKEN", "GH_TOKEN",
      "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "AZURE_CLIENT_SECRET",
      "DATABASE_URL", "PGPASSWORD", "SSH_AUTH_SOCK", "REDIS_PASSWORD",
      "MY_API_KEY", "APP_SECRET", "OAUTH_TOKEN", "STRIPE_SECRET_KEY",
    ]) {
      expect(isAllowedEnvKey(k), `${k} must be denied`).toBe(false);
    }
  });

  it("never inherits host process.env implicitly", () => {
    const env = buildSandboxEnv({
      base: {
        PATH: "C:\\Windows",
        GITHUB_TOKEN: "should-not-survive",
        AWS_SECRET_ACCESS_KEY: "nope",
        WORKFLO_RUN_ID: "run-1",
      },
    });
    expect(env.PATH).toBe("C:\\Windows");
    expect(env.WORKFLO_RUN_ID).toBe("run-1");
    expect(env.GITHUB_TOKEN).toBeUndefined();
    expect(env.AWS_SECRET_ACCESS_KEY).toBeUndefined();
  });

  it("deny-list wins over allow prefix", () => {
    const env = buildSandboxEnv({ extra: { WORKFLO_API_KEY: "hidden-value" } });
    expect(env.WORKFLO_API_KEY).toBeUndefined();
  });

  it("constructs defaults when absent", () => {
    const env = buildSandboxEnv({});
    expect(env.PATH).toContain("/usr/bin");
    expect(env.HOME).toBe("/tmp");
  });
});
