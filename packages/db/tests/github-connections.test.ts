import { describe, expect, it } from "vitest";
import { appDb, makeTenantFixture } from "./helpers";
import { githubConnections } from "../src";

describe("github_connections: credential separation", () => {
  it("accepts a credential reference (vault://...)", async () => {
    const db = appDb();
    try {
      const t = await makeTenantFixture(db, "ghc-ok");
      await db.withTenant(t.ctx, async (s) => {
        const conn = await githubConnections.createGithubConnection(s, {
          installationId: "12345",
          credentialRef: "vault://workflo/prod/ghc_01",
          repositoryUrl: "https://github.com/org/repo",
          accountLogin: "org",
        });
        expect(conn.credential_ref).toBe("vault://workflo/prod/ghc_01");
        return null;
      });
    } finally {
      await db.close();
    }
  });

  it("rejects raw OAuth/PAT tokens stored as credential_ref", async () => {
    const db = appDb();
    try {
      const t = await makeTenantFixture(db, "ghc-raw");
      await db.withTenant(t.ctx, async (s) => {
        for (const raw of [
          "ghp_1234567890abcdef",
          "gho_deadbeef",
          "github_pat_11AAAAAA",
          "sk-live-token-value",
          "just-a-plain-token",
        ]) {
          await expect(
            githubConnections.createGithubConnection(s, {
              installationId: "12345",
              credentialRef: raw,
            }),
          ).rejects.toThrow(/CHECK|credential_ref/i);
        }
        return null;
      });
    } finally {
      await db.close();
    }
  });

  it("no plaintext token columns exist on the table", async () => {
    const db = appDb();
    try {
      await db.withTenant({ orgId: "00000000-0000-0000-0000-000000000000" }, async (s) => {
        const { rows } = await s.query<{ column_name: string }>(
          `SELECT column_name FROM information_schema.columns
           WHERE table_schema = 'public' AND table_name = 'github_connections'`,
        );
        const names = rows.map((r) => r.column_name);
        expect(names).toContain("credential_ref");
        expect(names.some((n) => /token|secret|password/i.test(n))).toBe(false);
        return null;
      });
    } finally {
      await db.close();
    }
  });
});
