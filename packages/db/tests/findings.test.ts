import { describe, expect, it } from "vitest";
import { appDb, makeTenantFixture, appendChainedEvent } from "./helpers";
import { findings } from "../src";

describe("findings: hypothesis -> judge judgment", () => {
  async function seed(db: ReturnType<typeof appDb>) {
    const t = await makeTenantFixture(db, "findings");
    return db.withTenant(t.ctx, async (s) => {
      const { rows } = await s.query<{ id: string }>(
        `INSERT INTO runs (organization_id, project_id, mission_id)
         VALUES ($1,$2,$3) RETURNING id`,
        [t.orgId, t.projectId, t.missionId],
      );
      return { ...t, runId: rows[0]!.id };
    });
  }

  it("propose → CONFIRMED via judge function, then immutable", async () => {
    const db = appDb();
    try {
      const t = await seed(db);
      await db.withTenant(t.ctx, async (s) => {
        const ev = await appendChainedEvent(s, t, t.runId, {
          kind: "OBSERVATION",
          role: "EXPLORER",
          summary: "401 on /api/admin without token",
        });

        const f = await findings.proposeFinding(s, {
          projectId: t.projectId,
          runId: t.runId,
          title: "Unauthenticated admin endpoint",
          severity: "high",
        });
        expect(f.status).toBe("PROPOSED");

        const judged = await findings.judgeFinding(
          s,
          f.id,
          "CONFIRMED",
          "high",
          [ev.id],
        );
        expect(judged.status).toBe("CONFIRMED");
        expect(judged.confidence).toBe("high");
        expect(judged.decided_at).not.toBeNull();

        // Judged finding: no more verdict flips, no content mutation.
        await expect(
          findings.judgeFinding(s, f.id, "UNCONFIRMED", "low", [ev.id]),
        ).rejects.toThrow(/already judged/);

        await expect(
          s.query(`UPDATE findings SET title = 'changed' WHERE id = $1`, [f.id]),
        ).rejects.toThrow(/immutable/);
        return null;
      });
    } finally {
      await db.close();
    }
  });

  it("judge cannot cite evidence from another run (ledger-scoped proof)", async () => {
    const db = appDb();
    try {
      const t = await seed(db);
      await db.withTenant(t.ctx, async (s) => {
        const { rows: otherRun } = await s.query<{ id: string }>(
          `INSERT INTO runs (organization_id, project_id, mission_id)
           VALUES ($1,$2,$3) RETURNING id`,
          [t.orgId, t.projectId, t.missionId],
        );
        const otherRunId = otherRun[0]!.id;

        const foreignEv = await appendChainedEvent(s, t, otherRunId, {
          kind: "OBSERVATION",
          role: "EXPLORER",
          summary: "event from a different run",
        });

        const f = await findings.proposeFinding(s, {
          projectId: t.projectId,
          runId: t.runId,
          title: "cross-run evidence attempt",
        });

        await expect(
          findings.judgeFinding(s, f.id, "CONFIRMED", "medium", [foreignEv.id]),
        ).rejects.toThrow(/ledger events of this run/);
        return null;
      });
    } finally {
      await db.close();
    }
  });

  it("no magical ai_says_confirmed column exists", async () => {
    const db = appDb();
    try {
      await db.withTenant({ orgId: "00000000-0000-0000-0000-000000000000" }, async (s) => {
        const { rows } = await s.query<{ column_name: string }>(
          `SELECT column_name FROM information_schema.columns
           WHERE table_schema = 'public' AND table_name = 'findings'`,
        );
        const names = rows.map((r) => r.column_name);
        expect(names.some((n) => /ai_|auto_confirm|model_says/i.test(n))).toBe(false);
        expect(names).toContain("status");
        expect(names).toContain("evidence_refs");
        expect(names).toContain("confidence");
        return null;
      });
    } finally {
      await db.close();
    }
  });
});
