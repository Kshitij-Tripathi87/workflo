import { describe, expect, it } from "vitest";
import { appDb, expectErr, makeTenantFixture } from "./helpers";
import { runs } from "../src";

describe("run lifecycle", () => {
  it("legal chain CREATED → ... → COMPLETED works; timestamps set", async () => {
    const db = appDb();
    try {
      const t = await makeTenantFixture(db, "lifecycle-ok");
      await db.withTenant(t.ctx, async (s) => {
        const run = await runs.createRun(s, {
          projectId: t.projectId,
          missionId: t.missionId,
        });
        expect(run.state).toBe("CREATED");
        expect(run.started_at).toBeNull();

        for (const state of [
          "INGESTING", "PROVISIONING", "EXECUTING",
          "EXPLORING", "JUDGING", "NOTARIZING", "COMPLETED",
        ] as const) {
          const next = await runs.transitionRun(s, run.id, state);
          expect(next.state).toBe(state);
        }

        const done = await runs.getRun(s, run.id);
        expect(done!.state).toBe("COMPLETED");
        expect(done!.started_at).not.toBeNull();
        expect(done!.finished_at).not.toBeNull();
        return null;
      });
    } finally {
      await db.close();
    }
  });

  it("rejects illegal transitions (skip, backward, terminal re-entry)", async () => {
    const db = appDb();
    try {
      const t = await makeTenantFixture(db, "lifecycle-illegal");
      await db.withTenant(t.ctx, async (s) => {
        const run = await runs.createRun(s, {
          projectId: t.projectId,
          missionId: t.missionId,
        });

        await expect(runs.transitionRun(s, run.id, "COMPLETED")).rejects.toThrow(
          /illegal run transition/,
        );
        await expect(runs.transitionRun(s, run.id, "JUDGING")).rejects.toThrow(
          /illegal run transition/,
        );

        await runs.transitionRun(s, run.id, "INGESTING");
        await expect(runs.transitionRun(s, run.id, "CREATED")).rejects.toThrow(
          /illegal run transition/,
        );

        await runs.transitionRun(s, run.id, "FAILED", { error: "boom" });
        const failed = await runs.getRun(s, run.id);
        expect(failed!.error).toBe("boom");
        expect(failed!.finished_at).not.toBeNull();

        await expect(runs.transitionRun(s, run.id, "INGESTING")).rejects.toThrow(
          /illegal run transition/,
        );
        return null;
      });
    } finally {
      await db.close();
    }
  });

  it("app role cannot UPDATE runs.state directly (must use the function)", async () => {
    const db = appDb();
    try {
      const t = await makeTenantFixture(db, "lifecycle-direct");
      await db.withTenant(t.ctx, async (s) => {
        const run = await runs.createRun(s, {
          projectId: t.projectId,
          missionId: t.missionId,
        });
        try {
          await s.query(`UPDATE runs SET state = 'COMPLETED' WHERE id = $1`, [
            run.id,
          ]);
          throw new Error("direct state update should have failed");
        } catch (error) {
          expectErr(error, /permission denied/i);
        }
        return null;
      });
    } finally {
      await db.close();
    }
  });

  it("transition function rejects cross-tenant run ids and missing context", async () => {
    const db = appDb();
    try {
      const a = await makeTenantFixture(db, "lifecycle-xt-a");
      const b = await makeTenantFixture(db, "lifecycle-xt-b");
      const bRun = await db.withTenant(b.ctx, (s) =>
        runs.createRun(s, { projectId: b.projectId, missionId: b.missionId }),
      );

      // A tries to transition B's run — function owner bypasses RLS, so the
      // explicit org check inside transition_run_state is the guard.
      await db.withTenant(a.ctx, async (s) => {
        await expect(
          runs.transitionRun(s, bRun.id, "INGESTING"),
        ).rejects.toThrow(/cross-tenant access denied/);
        return null;
      });

      // No tenant context at all.
      await expect(
        db.system((c) =>
          c.query(
            `SELECT transition_run_state($1, 'INGESTING'::run_state, '{}'::jsonb)`,
            [bRun.id],
          ),
        ),
      ).rejects.toThrow(/tenant context is required/);
    } finally {
      await db.close();
    }
  });
});
